import urlparse
import urllib

from flask import current_app
from ..models import User

def make_solr_request(query, bigquery=None, headers=None):
    # I'm making a simplification here; sending just one content stream
    # it would be possible to save/send multiple content streams but
    # I decided that would only create confusion; so only one is allowed
    if isinstance(query, basestring):
        query = urlparse.parse_qs(query)

    if bigquery:
        headers = dict(headers)
        headers['content-type'] = 'big-query/csv'
        return current_app.client.post(current_app.config['VAULT_SOLR_BIGQUERY_ENDPOINT'], params=query, headers=headers, data=bigquery)
    else:
        return current_app.client.get(current_app.config['VAULT_SOLR_QUERY_ENDPOINT'], params=query, headers=headers)


def cleanup_payload(payload):
    bigquery = payload.get('bigquery', "")
    query = {}

    if 'query' in payload:
        pointer = payload.get('query')
    else:
        pointer = payload

    if (isinstance(pointer, list)):
        pointer = pointer[0]
    if (isinstance(pointer, basestring)):
        pointer = urlparse.parse_qs(pointer)


    # clean up
    for k,v in pointer.items():
        if k[0] == 'q' or k[0:2] == 'fq':
            query[k] = v

    # make sure the bigquery is just a string
    if isinstance(bigquery, list):
        bigquery = bigquery[0]
    if not isinstance(bigquery, basestring):
        raise Exception('The bigquery has to be a string, instead it was {0}'.format(type(bigquery)))

    if len(bigquery) > 0:
        found = False
        for k,v in query.items():
            if 'fq' in k:
                if isinstance(v, list):
                    for x in v:
                        if '!bitset' in x:
                            found = True
                elif '!bitset' in v:
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
        and 'application/json' in headers['Content-Type'] \
        and request.method in ('POST', 'PUT'):
        payload = request.json
    else:
        payload = dict(request.args)
        payload.update(dict(request.form))

    new_headers = {}
    if headers['Authorization']:
        new_headers['X-Forwarded-Authorization'] = headers['Authorization']
    new_headers['Authorization'] = 'Bearer:' + current_app.config['VAULT_OAUTH_CLIENT_TOKEN']
    new_headers['X-Adsws-Uid'] = headers.get('X-Adsws-Uid', '0') # User ID

    return (payload, new_headers)

