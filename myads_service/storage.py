from flask import Blueprint
from flask import request

import json
import md5
import urlparse

from sqlalchemy import exc
from models import Query, db
from utils import check_request, cleanup_payload, make_solr_request


bp = Blueprint('storage', __name__)

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
    payload, headers = check_request(request)
    
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
    qid = md5.new(headers['User'] + query).hexdigest()
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


@bp.route('/execute_query/<queryid>', methods=['GET'])
def execute_query(queryid):
    '''Allows you to execute stored query'''
    
    q = db.session.query(Query).filter_by(qid=queryid).first()
    if not q:
        return json.dumps({msg: 'Query not found: ' + qid}), 404
    
    dataq = json.loads(q.query)
    payload, headers = check_request(request)
    query = urlparse.parse_qs(dataq['query'])
    
    # override parameters using supplied params
    if len(payload) > 0:
        query.update(payload)
    
    # always request json
    query['wt'] = json
    
    r = make_solr_request(query=query, bigquery=dataq['bigquery'], headers=headers)
    return r.text, r.status_code

