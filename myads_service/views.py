from flask import Blueprint
from flask import current_app, request

import requests
import uuid
import time
import json
import md5
import datetime
import urlparse
import urllib
from sqlalchemy import exc
from models import Query, db

storage = Blueprint('storage', __name__)


@storage.route('/query', methods=['GET', 'POST'])
def query(qid=None):
    '''Stores/retrieves the montysolr query; it can receive data in urlencoded
    format or as application/json encoded data. In the second case, you can 
    pass 'bigquery' together with the 'query' like so:
    
    {
        query: {foo: bar},
        bigquery: 'data\ndata\n....'
    }
    '''
    
    if request.method == 'GET' and qid:
        q = Query.first(qid=qid)
        if not q:
            return json.dumps({msg: 'Query not found: ' + qid}), 404
        return json.dumps({
            'qid': q.qid,
            'query': json.parse(q.query),
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
    q = Query(qid=qid, query=query)
    
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


@storage.route('/execute_query/<queryid>', methods=['GET'])
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



def make_solr_request(query, bigquery=None, headers=None):
    # I'm making a simplification here; sending just one content stream
    # it would be possible to save/send multiple content streams but
    # I decided that would only create confusion; so only one is allowed
    
    if bigquery:
        headers = dict(headers)
        headers['content-type'] = 'big-query/csv'
        return requests.post(current_app.config['SOLR_BIGQUERY_ENDPOINT'], params=query, headers=headers, data=bigquery)
    else:
        return requests.post(current_app.config['SOLR_QUERY_ENDPOINT'], data=query, headers=headers) 


def cleanup_payload(payload):
    bigquery = payload.get('bigquery', "")
    query = {}
    
    if 'query' in payload:
        pointer = payload.get('query')
    else:
        pointer = payload

    if (isinstance(pointer, basestring)):
        pointer = urlparse.parse_qs(pointer)
        
    # clean up
    for k,v in pointer.items():
        if k[0] == 'q' or k[0:2] == 'fq':
            query[k] = v
            
    if len(bigquery) > 0:
        found = False
        for k,v in query.items():
            if '!bitset' in v and 'fq' in k:
                found = True
                break
        if not found:
            raise Exception('When you pass bigquery data, you also need to tell us how to use it (in fq={!bitset} etc)')
    
    return {
        'query': serialize_dict(query),
        'bigquery': bigquery
    }
    

def serialize_dict(data):
    v = data.items()
    v = sorted(v, key=lambda x: x[0])
    return urllib.urlencode(v, doseq=True)

def check_request(request):
    headers = dict(request.headers)
    if 'Content-Type' in headers \
        and headers['Content-Type'] == 'application/json' \
        and request.method in ('POST', 'PUT'):
        payload = request.json
    else:
        payload = dict(request.args)
        payload.update(dict(request.form))
    
    if headers['Authorization']:
        headers['X-Forwarded-Authorization'] = headers['Authorization']
    headers['Authorization'] = 'Bearer:' + current_app.config['OAUTH_CLIENT_TOKEN']
    headers['User'] = headers.get('User', '0') # User ID
    
    return (payload, headers)

blueprints = [storage]
