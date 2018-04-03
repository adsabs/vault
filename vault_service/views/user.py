from flask import Blueprint
from flask import current_app
from flask import request

import json
import md5
import urlparse

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from ..models import Query, User
from .utils import check_request, cleanup_payload, make_solr_request
from flask_discoverer import advertise

bp = Blueprint('user', __name__)

@advertise(scopes=['store-query'], rate_limit = [300, 3600*24])
@bp.route('/query', methods=['POST'])
@bp.route('/query/<queryid>', methods=['GET'])
def query(queryid=None):
    '''Stores/retrieves the montysolr query; it can receive data in urlencoded
    format or as application/json encoded data. In the second case, you can
    pass 'bigquery' together with the 'query' like so:

    {
        query: {foo: bar},
        bigquery: 'data\ndata\n....'
    }
    '''
    if request.method == 'GET' and queryid:
        with current_app.session_scope() as session:
            q = session.query(Query).filter_by(qid=queryid).first()
            if not q:
                return json.dumps({'msg': 'Query not found: ' + queryid}), 404
            return json.dumps({
                'qid': q.qid,
                'query': q.query,
                'numfound': q.numfound }), 200

    # get the query data
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    if len(payload.keys()) == 0:
        raise Exception('Query cannot be empty')

    payload = cleanup_payload(payload)

    # check we don't have this query already
    query = json.dumps(payload)
    qid = md5.new(headers['X-Adsws-Uid'] + query).hexdigest()
    with current_app.session_scope() as session:
        q = session.query(Query).filter_by(qid=qid).first()
        if q:
            return json.dumps({'qid': qid, 'numFound': q.numfound}), 200

    # check the query is valid
    solrq = payload['query'] + '&wt=json'
    r = make_solr_request(query=solrq, bigquery=payload['bigquery'], headers=headers)
    if r.status_code != 200:
        return json.dumps({'msg': 'Could not verify the query.', 'query': payload, 'reason': r.text}), 404

    # extract number of docs found
    num_found = 0
    try:
        num_found = int(r.json()['response']['numFound'])
    except:
        pass

    # save the query
    q = Query(qid=qid, query=query, numfound=num_found)
    with current_app.session_scope() as session:
        session.begin_nested()
        try:
            session.add(q)
            session.commit()
        except exc.IntegrityError as e:
            session.rollback()
            return json.dumps({'msg': e.message or e.description}), 400
            # TODO: update
            #q = session.merge(q) # force re-sync from database
            #q.updated = datetime.datetime.utcnow()
            #session.commit()

        return json.dumps({'qid': qid, 'numFound': num_found}), 200


@advertise(scopes=['execute-query'], rate_limit = [1000, 3600*24])
@bp.route('/execute_query/<queryid>', methods=['GET'])
def execute_query(queryid):
    '''Allows you to execute stored query'''

    with current_app.session_scope() as session:
        q = session.query(Query).filter_by(qid=queryid).first()
        if not q:
            return json.dumps({msg: 'Query not found: ' + qid}), 404
        q_query = q.query

    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    dataq = json.loads(q_query)
    query = urlparse.parse_qs(dataq['query'])

    # override parameters using supplied params
    if len(payload) > 0:
        query.update(payload)

    # make sure the {!bitset} is there (when bigquery is used)
    if dataq['bigquery']:
        fq = query.get('fq')
        if not fq:
            fq = ['{!bitset}']
        elif '!bitset' not in str(fq):
            if isinstance(fq, list):
                fq.append('{!bitset}')
            else:
                fq = ['{!bitset}']
        query['fq'] = fq

    # always request json
    query['wt'] = 'json'

    r = make_solr_request(query=query, bigquery=dataq['bigquery'], headers=headers)
    return r.text, r.status_code


@advertise(scopes=['store-preferences'], rate_limit = [100, 3600*24])
@bp.route('/user-data', methods=['GET', 'POST'])
def store_data():
    '''Allows you to store/retrieve JSON data on the server side.
    It is always associated with the user id (which is communicated
    to us by API) - so there is no endpoint allowing you to access
    other users' data (should there be?) /user-data/<uid>?'''

    # get the query data
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    user_id = int(headers['X-Adsws-Uid'])

    if user_id == 0:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    if request.method == 'GET':
        with current_app.session_scope() as session:
            q = session.query(User).filter_by(id=user_id).first()
            if not q:
                return '{}', 200 # or return 404?
            return q.user_data or '{}', 200
    elif request.method == 'POST':
        # limit both number of keys and length of value to keep db clean
        if len(max(payload.values(), key=len)) > current_app.config['MAX_ALLOWED_JSON_SIZE']:
            return json.dumps({'msg': 'You have exceeded the allowed storage limit (length of values), no data was saved'}), 400
        if len(payload.keys()) > current_app.config['MAX_ALLOWED_JSON_KEYS']:
            return json.dumps({'msg': 'You have exceeded the allowed storage limit (number of keys), no data was saved'}), 400

        with current_app.session_scope() as session:
            try:
                q = session.query(User).filter_by(id=user_id).with_for_update(of=User).one()
                try:
                    data = json.loads(q.user_data)
                except TypeError:
                    data = {}
            except ormexc.NoResultFound:
                d = json.dumps(payload)
                u = User(id=user_id, user_data=d)
                try:
                    session.add(u)
                    session.commit()
                    return d, 200
                except exc.IntegrityError:
                    q = session.query(User).filter_by(id=user_id).with_for_update(of=User).one()
                    try:
                        data = json.loads(q.user_data)
                    except TypeError:
                        data = {}

            data.update(payload)
            d = json.dumps(data)
            u = User(id=user_id, user_data=d)

            session.begin_nested()
            try:
                session.merge(u)
                session.commit()
            except exc.IntegrityError:
                session.rollback()
                return json.dumps({'msg': 'We have hit a db error! The world is crumbling all around... (eh, btw, your data was not saved)'}), 500

        return d, 200



