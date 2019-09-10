from flask import Blueprint
from flask import current_app
from flask import request, url_for

import json
import md5
import urlparse

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from ..models import Query, User, MyADS
from .utils import check_request, cleanup_payload, make_solr_request, check_data
from flask_discoverer import advertise
from dateutil import parser
import adsmutils

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
            return json.dumps({'msg': 'Query not found: ' + queryid}), 404
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


@advertise(scopes=['store-preferences'], rate_limit = [1200, 3600*24])
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
            return json.dumps(q.user_data) or '{}', 200
    elif request.method == 'POST':
        return_data = _save_user_data(user_id=user_id, payload=payload)
        if return_data[0] is not None:
            return return_data[0], 200
        else:
            return json.dumps({'msg': return_data[1]}), return_data[2]


def _save_user_data(user_id=None, payload=None):
    # limit both number of keys and length of value to keep db clean
    if len(max(payload.values(), key=len)) > current_app.config['MAX_ALLOWED_JSON_SIZE']:
        return None, 'You have exceeded the allowed storage limit (length of values), no data was saved', 400
    if len(payload.keys()) > current_app.config['MAX_ALLOWED_JSON_KEYS']:
        return None, 'You have exceeded the allowed storage limit (number of keys), no data was saved', 400
    payload_keys_lower = dict(zip(map(lambda x: x.lower(), payload.keys()), payload.keys()))
    if 'myads' in payload_keys_lower:
        vals = payload[payload_keys_lower['myads']]
        if not isinstance(vals, list):
            return None, 'myADS settings should be stored as a list of dicts, no data was saved', 400
        for v in vals:
            if not isinstance(v, dict):
                return None, 'myADS settings should be stored as a list of dicts, no data was saved', 400
            goodval = check_data(v, types=dict(name=basestring,
                                               qid=basestring,
                                               type=basestring,
                                               active=bool,
                                               stateful=bool,
                                               frequency=basestring))
            if goodval is False:
                return None, 'Invalid keys or values passed in myADS setup, no data was saved', 400
            if v['frequency'] not in ['daily', 'weekly']:
                return None, 'Invalid keys or values passed in myADS setup, no data was saved', 400
            if v['type'] not in ['template', 'query']:
                return None, 'Invalid keys or values passed in myADS setup, no data was saved', 400

    with current_app.session_scope() as session:
        try:
            q = session.query(User).filter_by(id=user_id).with_for_update(of=User).one()
            try:
                data = q.user_data
            except TypeError:
                data = {}
        except ormexc.NoResultFound:
            data = payload
            u = User(id=user_id, user_data=data, created=adsmutils.get_date(), updated=adsmutils.get_date())
            try:
                session.add(u)
                session.commit()
                return json.dumps(data), 'success', 200
            except exc.IntegrityError:
                q = session.query(User).filter_by(id=user_id).with_for_update(of=User).one()
                try:
                    data = q.user_data
                except TypeError:
                    data = {}

        data.update(payload)
        q.user_data = data
        q.updated = adsmutils.get_date()

        session.begin_nested()
        try:
            session.commit()
        except exc.IntegrityError:
            session.rollback()
            return None, 'We have hit a db error! The world is crumbling all around... (eh, btw, your data was not saved)', 500

    return json.dumps(data), 'success', 200


@advertise(scopes=['store-myads'], rate_limit=[1000, 3600*24])
@bp.route('/myads', methods=['POST'])
@bp.route('/myads/<queryid>', methods=['GET', 'DELETE'])
def store_myads(queryid=None):
    '''
    Stores templated myADS setup
    :return:
    '''

    # BBB provides (for templated queries):
    # arXiv: keywords, arXiv categories
    #   constructed: bibstem:arxiv ((arxiv_class:XXX OR arxiv_class:XXX) OR (keyword1 OR keyword2)) entdate:["NOW-1(or 2)DAYS" TO NOW]
    #   sorted: score desc bibcode desc
    #   payload structure: {'type': 'arxiv', 'classes': ['class1','class2'], 'data': 'keyword 1 OR keyword2'}
    # citations: author name or ORCID ID
    #   constructed: citations(author/orcid:XXX) (note: stateful=True)
    #   sorted: date desc bibcode desc
    #   payload structure: {'type': 'citations', 'data': 'author:XXX OR orcid:XXX'}
    # favorite authors: author names or ORCID IDs
    #   constructed: author:XXX OR orcid:XXX (note: stateful=True)
    #   sorted: score desc bibcode desc
    #   payload structure: {'type': 'authors', 'data': 'author:XXX OR orcid:XXX'}
    # keywords: keywords
    #   constructed:
    #       recent: keyword1 OR keyword2
    #       sorted: entdate desc bibcode desc
    #       most popular: trending(keyword1 OR keyword2)
    #       sorted: score desc bibcode desc
    #       most cited: useful(keyword1 OR keyword2)
    #       sorted: score desc bibcode desc
    #   payload structure: {'template': 'keyword', 'data': 'keyword1 OR keyword2', 'qid': (opt) 123} (types: citations, authors, keyword)
    #                      {'template': 'keyword', classes: 'astro-ph', 'data': 'keyword1 OR keyword2', 'qid': (opt) 123} (type: arxiv)

    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    user_id = int(headers['X-Adsws-Uid'])

    if user_id == 0:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    if request.method == 'GET':
        with current_app.session_scope() as session:
            r = session.query(User).filter_by(id=user_id).first()
            if not r:
                return '{}', 404
            user_data = r.user_data
        try:
            myADS_setup = user_data['myADS']
            setup = [i for i in myADS_setup if i['qid'] == queryid]
            return json.dumps(setup), 200
        except KeyError:
            return '{}', 404
    elif request.method == 'DELETE':
        with current_app.session_scope() as session:
            r = session.query(User).filter_by(id=user_id).first()
            if not r:
                return '{}', 404
            user_data = r.user_data
            try:
                myADS_setup = user_data['myADS']
            except KeyError:
                return '{}', 404

            # remove from metadata stores
            myADS_setup = [i for i in myADS_setup if i['qid'] != queryid]

            # save the edited metadata stores
            user_data.update({'myADS': myADS_setup})
        return_data, msg, status = _save_user_data(user_id, user_data)

        if status != 200:
            return json.dumps({'msg': 'Saving edited myADS setup failed, try again'}), 500

        # remove from myADS table
        with current_app.session_scope() as session:
            # qid is an int in the myADS table
            qid = int(queryid)
            q = session.query(MyADS).filter_by(id=qid).first()
            try:
                session.delete(q)
                session.commit()
            except exc.IntegrityError as e:
                session.rollback()
                return json.dumps({'msg': 'Query was not deleted'}), 500

        return '{}', 204
    elif request.method == 'POST':
        # check payload
        if 'template' not in payload:
            return json.dumps({'msg': 'Bad data passed'}), 400

        if 'data' not in payload:
            return json.dumps({'msg': 'Bad data passed'}), 400
        elif not isinstance(payload['data'], basestring):
            return json.dumps({'msg': 'Bad data passed'}), 400

        if payload['template'] == 'arxiv':
            if 'classes' not in payload:
                return json.dumps({'msg': 'Bad data passed'}), 400
            elif not isinstance(payload['classes'], list):
                return json.dumps({'msg': 'Bad data passed'}), 400

        # add metadata
        if payload['template'] == 'arxiv':
            template = 'arxiv'
            data = {'classes': payload['classes'], 'data': payload['data']}
            stateful = False
            frequency = 'daily'
            name = '{0} - Recent Papers'.format(payload['data'])
        elif payload['template'] == 'citations':
            template = 'citations'
            data = {'data': payload['data']}
            stateful = True
            frequency = 'weekly'
            name = '{0} - Citations'.format(payload['data'])
        elif payload['template'] == 'authors':
            template = 'authors'
            data = {'data': payload['data']}
            stateful = True
            frequency = 'weekly'
            name = 'Favorite Authors - Recent Papers'
        elif payload['template'] == 'keyword':
            template = 'keyword'
            data = {'data': payload['data']}
            name = '{0}'.format(payload['data'])
            stateful = False
            frequency = 'weekly'
        else:
            return json.dumps({'msg': 'Wrong template type passed'}), 400

        # update/store the template query data, get a qid back
        with current_app.session_scope() as session:
            # update existing
            if 'qid' in payload:
                # qid is an int in the myADS table
                qid = int(payload['qid'])
                q = session.query(MyADS).filter_by(id=qid).first()
                q.data = data
                q.updated = adsmutils.get_date()

                session.begin_nested()
                try:
                    session.commit()
                except exc.IntegrityError:
                    session.rollback()
                    return json.dumps({'msg': 'Existing myADS setup was not updated'}), 500
            # add new
            else:
                q = MyADS(template=template, data=data, created=adsmutils.get_date(), updated=adsmutils.get_date())
                try:
                    session.add(q)
                    session.flush()
                    # qid is an int in the myADS table
                    qid = q.id
                    session.commit()
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved'}), 500

        # add the new setup to myADS metadata in user-data
        with current_app.session_scope() as session:
            r = session.query(User).filter_by(id=user_id).first()
            if not r:
                user_data = {}
            else:
                user_data = r.user_data

            try:
                myADS_setup = user_data['myADS']
            except KeyError:
                myADS_setup = []

            # remove setup if qid exists in existing myADS setup
            # qid is a string in the metadata
            qid = str(qid)
            myADS_setup = list(filter(lambda j: j['qid'] != qid, myADS_setup))

            # add new setup
            new_setup = {'name': name,
                         'qid': qid,
                         'type': 'template',
                         'active': True,
                         'stateful': stateful,
                         'frequency': frequency}

            # store new setups
            myADS_setup.append(new_setup)
            user_data.update({'myADS': myADS_setup})

        return_data, msg, status = _save_user_data(user_id, user_data)

        if status != 200:
            return json.dumps({'msg': 'Saving myADS setup failed, try again'}), 500

        return json.dumps(new_setup), 200


@advertise(scopes=['ads-consumer:myads'], rate_limit = [1000, 3600*24])
@bp.route('/get-myads/<user_id>', methods=['GET'])
def get_myads(user_id):
    '''
    Fetches a myADS profile for the pipeline for a given uid
    '''

    # takes a given uid, grabs the user_data field, checks for the myADS key - if present, grabs the appropriate
    # queries/data from the queries/myADS table. Finally, returns the appropriate info along w/ the rest
    # of the setup from the dict (e.g. active, frequency, etc.)

    # TODO check rate limit

    # structure in vault:
    # "myADS": [{"name": user-supplied name, "qid": QID from query table (type="query") or ID from myads table
    # (type="template"), "type":  "query" or "template", "active": true/false, "frequency": "daily" or "weekly",
    # "stateful": true/false}]

    with current_app.session_scope() as session:
        u = session.query(User).filter_by(id=user_id).first()
        if not u:
            return '{}', 404
        elif 'myADS' not in u.user_data:
            return '{}', 404
        else:
            user_data = u.user_data['myADS']

        myADS = []
        for i in user_data:
            if i['active']:
                if i['type'] == 'template':
                    t = session.query(MyADS).filter_by(id=i['qid']).first()
                    i['data'] = t.data
                    i['template'] = t.template
                myADS.append(i)

    return json.dumps(myADS), 200


@advertise(scopes=['ads-consumer:myads'], rate_limit = [1000, 3600*24])
@bp.route('/myads-users/<iso_datestring>', methods=['GET'])
def export(iso_datestring):
    '''
    Get the latest changes (as recorded in users table)
        The optional argument latest_point is RFC3339, ie. '2008-09-03T20:56:35.450686Z'
    '''
    # TODO check rate limit
    # TODO need to add a created/update field to users table

    # inspired by orcid-service endpoint of same endpoint, checks the users table for profiles w/ a myADS setup that
    # have been updated since a given date/time; returns these profiles to be added to the myADS processing

    latest = parser.parse(iso_datestring) # ISO 8601
    output = []
    with current_app.session_scope() as session:
        users = session.query(User).filter(User.updated >= latest) \
            .order_by(User.updated.asc()) \
            .all()

        for user in users:
            if user.user_data.has_key('myADS'):
                output.append(user.id)

    return json.dumps({'users': output}), 200
