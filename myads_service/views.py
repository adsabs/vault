from flask import Blueprint
from flask import current_app, request

import requests
import uuid
import time
import json
import md5
import datetime
from sqlalchemy import exc
from models import Query, db

storage = Blueprint('storage', __name__)


@storage.route('/queryx', methods=['GET', 'POST'])
def query_history(operation):
    '''Access point for query operations'''
    return '{}', 200

@storage.route('/query', methods=['GET', 'POST'])
def query(qid=None):
    '''Stores/retrieves the montysolr query'''
    
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
    
    # check the query is valid
    data = dict(payload)
    data['wt'] = 'json'
    r = requests.post(current_app.config['SOLR_QUERY_ENDPOINT'], data=payload, headers=headers)
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


def serialize_dict(data):
    v = data.values()
    sort(v, key=lambda x: x[0])
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
