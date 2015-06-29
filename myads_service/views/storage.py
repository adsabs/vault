from flask import Blueprint
from flask import request

import json
import md5
import urlparse

from sqlalchemy import exc
from myads_service.models import Query, db, User
from myads_service.utils import check_request, cleanup_payload, make_solr_request
from flask.ext.discoverer import advertise

bp = Blueprint('storage', __name__)

# The database is storing data as BLOB so there is no (practical) limit
# But we may want to be careful... the size is byte length; if used
# database limits, the data could be inserted/truncated by the database
# and corrupted
MAX_ALLOWED_JSON_SIZE = 10000

@advertise(scopes=['ads:store-query'], rate_limit = [100, 3600*24])
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
        q = db.session.query(Query).filter_by(qid=queryid).first()
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
    
    # check the query is valid
    query = payload['query'] + '&wt=json'
    r = make_solr_request(query=query, bigquery=payload['bigquery'], headers=headers)
    if r.status_code != 200:
        return json.dumps({'msg': 'Could not verify the query.', 'query': payload, 'reason': r.text}), 404
    
    # extract number of docs found
    num_found = 0
    try:
        num_found = int(r.json()['response']['numFound'])
    except:
        pass 
    
    # save the query
    query = json.dumps(payload)
    qid = md5.new(headers['X-Adsws-Uid'] + query).hexdigest()
    q = Query(qid=qid, query=query, numfound=num_found)
    
    db.session.begin_nested()
    try:
        db.session.add(q)
        db.session.commit()
    except exc.IntegrityError:
        db.session.rollback()
        # TODO: update 
        #q = db.session.merge(q) # force re-sync from database
        #q.updated = datetime.datetime.utcnow()
        #db.session.commit()
    
    return json.dumps({'qid': qid}), 200


@advertise(scopes=['ads:execute-query'], rate_limit = [1000, 3600*24])
@bp.route('/execute_query/<queryid>', methods=['GET'])
def execute_query(queryid):
    '''Allows you to execute stored query'''
    
    q = db.session.query(Query).filter_by(qid=queryid).first()
    if not q:
        return json.dumps({msg: 'Query not found: ' + qid}), 404
    
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    dataq = json.loads(q.query)    
    query = urlparse.parse_qs(dataq['query'])
    
    # override parameters using supplied params
    if len(payload) > 0:
        query.update(payload)
    
    # always request json
    query['wt'] = json
    
    r = make_solr_request(query=query, bigquery=dataq['bigquery'], headers=headers)
    return r.text, r.status_code


@advertise(scopes=['ads:store-data'], rate_limit = [100, 3600*24])
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
        q = db.session.query(User).filter_by(id=user_id).first()
        if not q:
            return '{}', 200 # or return 404?
        return q.user_data or '{}', 200
    elif request.method == 'POST':
        d = json.dumps(payload)
        if len(d) > MAX_ALLOWED_JSON_SIZE:
            return json.dumps({'msg': 'You have exceeded the allowed storage limit, no data was saved'}), 400
        u = User(id=user_id, user_data=d)
    
        db.session.begin_nested()
        try:
            db.session.merge(u)
            db.session.commit()
        except exc.IntegrityError:
            db.session.rollback()
            return json.dumps({'msg': 'We have hit a db error! The world is crumbling all around... (eh, btw, your data was not saved)'}), 500
    
        return d, 200
