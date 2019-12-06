from flask import Blueprint
from flask import current_app
from flask import request, url_for

import json
import md5
import urlparse

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from ..models import Query, User, MyADS
from .utils import check_request, cleanup_payload, make_solr_request, upsert_myads, get_keyword_query_name
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

    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    if request.method == 'GET':
        with current_app.session_scope() as session:
            q = session.query(User).filter_by(id=user_id).first()
            if not q:
                return '{}', 200 # or return 404?
            return json.dumps(q.user_data) or '{}', 200
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
                    data = q.user_data
                except TypeError:
                    data = {}
            except ormexc.NoResultFound:
                data = payload
                u = User(id=user_id, user_data=data)
                try:
                    session.add(u)
                    session.commit()
                    return json.dumps(data), 200
                except exc.IntegrityError:
                    q = session.query(User).filter_by(id=user_id).with_for_update(of=User).one()
                    try:
                        data = q.user_data
                    except TypeError:
                        data = {}

            data.update(payload)
            q.user_data = data

            session.begin_nested()
            try:
                session.commit()
            except exc.IntegrityError:
                session.rollback()
                return json.dumps({'msg': 'We have hit a db error! The world is crumbling all around... (eh, btw, your data was not saved)'}), 500

        return json.dumps(data), 200


@advertise(scopes=[], rate_limit=[1000, 3600*24])
@bp.route('/notifications', methods=['GET', 'POST'])
@bp.route('/notifications/<myads_id>', methods=['GET', 'PUT', 'DELETE'])
def myads_notifications(myads_id=None):
    """
    Manipulate one or all myADS notifications set up for a given user
    :param myads_id: ID of a single notification, if only one is desired
    :return: list of json, details of one or all setups
    """
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    user_id = int(headers['X-Adsws-Uid'])

    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    if request.method == 'GET':
        # detail-level view for a single setup
        if myads_id:
            with current_app.session_scope() as session:
                setup = session.query(MyADS).filter_by(user_id=user_id).filter_by(id=myads_id).first()
                if setup is None:
                    return '{}', 404
                if setup.query_id is not None:
                    q = session.query(Query).filter_by(id=setup.query_id).first()
                    qid = q.qid
                else:
                    qid = None

                output = {'id': setup.id,
                          'name': setup.name,
                          'qid': qid,
                          'type': setup.type,
                          'active': setup.active,
                          'stateful': setup.stateful,
                          'frequency': setup.frequency,
                          'template': setup.template,
                          'classes': setup.classes,
                          'data': setup.data,
                          'created': setup.created.isoformat(),
                          'updated': setup.updated.isoformat()}

                return json.dumps([output]), 200

        # summary-level view of all setups (w/ condensed list of keywords returned)
        else:
            with current_app.session_scope() as session:
                all_setups = session.query(MyADS).filter_by(user_id=user_id).order_by(MyADS.id.asc()).all()
                if len(all_setups) == 0:
                    return '{}', 204

                output = []
                for s in all_setups:
                    o = {'id': s.id,
                         'name': s.name,
                         'type': s.type,
                         'active': s.active,
                         'frequency': s.frequency,
                         'template': s.template,
                         'data': s.data,
                         'created': s.created.isoformat(),
                         'updated': s.updated.isoformat()}
                    output.append(o)

                return json.dumps(output), 200
    elif request.method == 'POST':
        msg, status_code = _create_myads_notification(payload, headers, user_id)
    elif request.method == 'PUT':
        msg, status_code = _edit_myads_notification(payload, headers, user_id, myads_id)
    elif request.method == 'DELETE':
        msg, status_code = _delete_myads_notification(user_id, myads_id)

    return msg, status_code


def _create_myads_notification(payload=None, headers=None, user_id=None):
    """
    Create a new myADS notification
    :return: json, details of new setup
    """
    # check payload
    try:
        ntype = payload['type']
    except KeyError:
        return json.dumps({'msg': 'No notification type passed'}), 400

    with current_app.session_scope() as session:
        try:
            q = session.query(User).filter_by(id=user_id).one()
        except ormexc.NoResultFound:
            u = User(id=user_id)
            try:
                session.add(u)
                session.commit()
            except exc.IntegrityError as e:
                session.rollback()
                return json.dumps({'msg': 'User does not exist, so new myADS setup was not saved, error: {0}'.
                                  format(e)}), 500

    if ntype == 'query':
        if not all(k in payload for k in ('qid', 'name', 'stateful', 'frequency')):
            return json.dumps({'msg': 'Bad data passed'}), 400
        with current_app.session_scope() as session:
            qid = payload.get('qid')
            q = session.query(Query).filter_by(qid=qid).first()
            if not q:
                return json.dumps({'msg': 'Query does not exist'}), 404
            query_id = q.id
            setup = MyADS(user_id=user_id,
                          type='query',
                          query_id=query_id,
                          name=payload.get('name'),
                          active=True,
                          stateful=payload.get('stateful'),
                          frequency=payload.get('frequency'))

    elif ntype == 'template':
        # handles both None values and empty strings
        if not payload.get('data'):
            payload['old_data'] = payload.get('data', None)
            payload['data'] = None

        if 'template' not in payload:
            return json.dumps({'msg': 'Bad data passed'}), 400

        if not payload['template'] == 'arxiv' and not isinstance(payload.get('data'), basestring):
            return json.dumps({'msg': 'Bad data passed'}), 400

        if payload['template'] == 'arxiv':
            if not isinstance(payload.get('classes'), list):
                return json.dumps({'msg': 'Bad data passed'}), 400
            if not set(payload.get('classes')).issubset(set(current_app.config['ALLOWED_ARXIV_CLASSES'])):
                return json.dumps({'msg': 'Bad data passed'}), 400

        if payload.get('data', None):
            # verify data/query
            solrq = 'q=' + payload.get('data') + '&wt=json'
            r = make_solr_request(query=solrq, headers=headers)
            if r.status_code != 200:
                return json.dumps({'msg': 'Could not verify the query.', 'query': payload, 'reason': r.text}), 404

        # add metadata
        if payload['template'] == 'arxiv':
            template = 'arxiv'
            classes = payload['classes']
            data = payload.get('data', None)
            stateful = False
            frequency = payload.get('frequency', 'daily')
            if payload.get('data', None):
                name = '{0} - Recent Papers'.format(get_keyword_query_name(payload['data']))
            else:
                name = 'Recent Papers'
        elif payload['template'] == 'citations':
            template = 'citations'
            classes = None
            data = payload['data']
            stateful = True
            frequency = 'weekly'
            name = '{0} - Citations'.format(payload['data'])
        elif payload['template'] == 'authors':
            template = 'authors'
            classes = None
            data = payload['data']
            stateful = True
            frequency = 'weekly'
            name = 'Favorite Authors - Recent Papers'
        elif payload['template'] == 'keyword':
            template = 'keyword'
            classes = None
            data = payload['data']
            name = '{0}'.format(get_keyword_query_name(payload['data']))
            stateful = False
            frequency = 'weekly'
        else:
            return json.dumps({'msg': 'Wrong template type passed'}), 400

        setup = MyADS(user_id=user_id,
                      type='template',
                      name=name,
                      active=True,
                      stateful=stateful,
                      frequency=frequency,
                      template=template,
                      classes=classes,
                      data=data)
    else:
        return json.dumps({'msg': 'Bad data passed'}), 400

    # update/store the template query data, get a qid back
    with current_app.session_scope() as session:
        try:
            session.add(setup)
            session.flush()
            # qid is an int in the myADS table
            myads_id = setup.id
            session.commit()
        except exc.StatementError as e:
            session.rollback()
            return json.dumps({'msg': 'Invalid data type passed, new myADS setup was not saved. Error: {0}'.format(e)}), 400
        except exc.IntegrityError as e:
            session.rollback()
            return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

        output = {'id': myads_id,
                  'name': setup.name,
                  'qid': payload.get('qid', None),
                  'type': setup.type,
                  'active': setup.active,
                  'stateful': setup.stateful,
                  'frequency': setup.frequency,
                  'template': setup.template,
                  'classes': setup.classes,
                  'data': setup.data,
                  'created': setup.created.isoformat(),
                  'updated': setup.updated.isoformat()}

    return json.dumps(output), 200


def _delete_myads_notification(user_id=None, myads_id=None):
    """
    Delete a single myADS notification setup
    :param myads_id: ID of a single notification
    :return: none
    """
    with current_app.session_scope() as session:
        r = session.query(MyADS).filter_by(user_id=user_id).filter_by(id=myads_id).first()
        if not r:
            return '{}', 404
        try:
            session.delete(r)
            session.commit()
        except exc.IntegrityError as e:
            session.rollback()
            return json.dumps({'msg': 'Query was not deleted'}), 500
        return '{}', 204


def _edit_myads_notification(payload=None, headers=None, user_id=None, myads_id=None):
    """
    Edit a single myADS notification setup
    :param myads_id: ID of a single notification
    :return: json, details of edited setup
    """
    # handles both None values and empty strings
    if not payload.get('data'):
        payload['old_data'] = payload.get('data', None)
        payload['data'] = None

    # verify data/query
    if payload.get('data', None):
        solrq = 'q=' + payload['data'] + '&wt=json'
        r = make_solr_request(query=solrq, headers=headers)
        if r.status_code != 200:
            return json.dumps({'msg': 'Could not verify the query.', 'query': payload, 'reason': r.text}), 404

    with current_app.session_scope() as session:
        setup = session.query(MyADS).filter_by(user_id=user_id).filter_by(id=myads_id).first()
        if setup is None:
            return '{}', 404
        # type/template/qid shouldn't be edited as they're fundamental constraints - delete & re-add if needed
        if payload.get('type', setup.type) != setup.type:
            return json.dumps({'msg': 'Cannot edit notification type'}), 400
        if payload.get('type', setup.type) == 'template':
            if setup.template != payload.get('template', setup.template):
                return json.dumps({'msg': 'Cannot edit template type'}), 400
            # edit name to reflect potentially new data input
            if payload.get('template', setup.template) == 'arxiv':
                name_template = '{0} - Recent Papers'
                # if a name is provided that wasn't just the old name, keep the new provided name
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
                # if name wasn't provided, check saved name - update if templated name
                elif setup.name == name_template.format(get_keyword_query_name(setup.data)):
                    setup.name = name_template.format(get_keyword_query_name(payload.get('data', setup.data)))
                # if name wasn't provided and previous name wasn't templated, keep whatever was there
            elif payload.get('template', setup.template) == 'citations':
                name_template = '{0} - Citations'
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
                elif setup.name == name_template.format(setup.data):
                    setup.name = name_template.format(payload.get('data', setup.data))
            elif payload.get('template', setup.template) == 'authors':
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
            elif payload.get('template', setup.template) == 'keyword':
                name_template = '{0}'
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
                elif setup.name == name_template.format(setup.data):
                    setup.name = '{0}'.format(get_keyword_query_name(payload.get('data', setup.data)))
            else:
                return json.dumps({'msg': 'Wrong template type passed'}), 400
            if not isinstance(payload.get('data', setup.data), basestring):
                return json.dumps({'msg': 'Bad data passed'}), 400
            setup.data = payload.get('data', setup.data)
            if payload.get('template', setup.template) == 'arxiv':
                if not isinstance(payload.get('classes', setup.classes), list):
                    return json.dumps({'msg': 'Bad data passed'}), 400
                if payload.get('classes') and not set(payload.get('classes')).issubset(set(current_app.config['ALLOWED_ARXIV_CLASSES'])):
                    return json.dumps({'msg': 'Bad data passed'}), 400
                setup.classes = payload.get('classes', setup.classes)
            qid = None
        if payload.get('type', setup.type) == 'query':
            qid = payload.get('qid', None)
            if qid:
                q = session.query(Query).filter_by(qid=qid).first()
                if q.id != setup.query_id:
                    return json.dumps({'msg': 'Cannot edit the qid'}), 400
            else:
                q = session.query(Query).filter_by(id=setup.query_id).first()
                qid = q.qid
            # name can be edited in query-type setups
            setup.name = payload.get('name', setup.name)
        # edit setup as necessary from the payload
        setup.active = payload.get('active', setup.active)
        setup.stateful = payload.get('stateful', setup.stateful)
        setup.frequency = payload.get('frequency', setup.frequency)

        try:
            session.begin_nested()
        except exc.StatementError as e:
            session.rollback()
            return json.dumps({'msg': 'Invalid data type passed, new myADS setup was not saved. Error: {0}'.format(e)}), 400

        try:
            session.commit()
        except exc.StatementError as e:
            session.rollback()
            return json.dumps({'msg': 'Invalid data type passed, new myADS setup was not saved. Error: {0}'.format(e)}), 400
        except exc.IntegrityError:
            session.rollback()
            return json.dumps({'msg': 'There was an error saving the updated setup'}), 500

        output = {'id': setup.id,
                  'name': setup.name,
                  'qid': qid,
                  'type': setup.type,
                  'active': setup.active,
                  'stateful': setup.stateful,
                  'frequency': setup.frequency,
                  'template': setup.template,
                  'classes': setup.classes,
                  'data': setup.data,
                  'created': setup.created.isoformat(),
                  'updated': setup.updated.isoformat()}

    return json.dumps(output), 200


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

    output = []
    with current_app.session_scope() as session:
        setups = session.query(MyADS).filter_by(user_id=user_id).filter_by(active=True).order_by(MyADS.id.asc()).all()
        if not setups:
            return '{}', 404
        for s in setups:
            o = {'id': s.id,
                 'name': s.name,
                 'type': s.type,
                 'active': s.active,
                 'stateful': s.stateful,
                 'frequency': s.frequency,
                 'template': s.template,
                 'classes': s.classes,
                 'data': s.data,
                 'created': s.created.isoformat(),
                 'updated': s.updated.isoformat()}

            if s.type == 'query':
                try:
                    q = session.query(Query).filter_by(id=s.query_id).one()
                    qid = q.qid
                except ormexc.NoResultFound:
                    qid = None
            else:
                qid = None
            o['qid'] = qid

            output.append(o)

    return json.dumps(output), 200


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
        setups = session.query(MyADS).filter(MyADS.updated > latest).order_by(MyADS.updated.asc()).all()
        for s in setups:
            output.append(s.user_id)

    output = list(set(output))
    return json.dumps({'users': output}), 200


@advertise(scopes=[], rate_limit=[1000, 3600*24])
@bp.route('/myads-import', methods=['GET'])
def import_myads():
    '''

    :return:
    '''
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    user_id = int(headers['X-Adsws-Uid'])

    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    r = current_app.client.get(current_app.config['HARBOUR_MYADS_IMPORT_ENDPOINT'] % user_id)

    if r.status_code != 200:
        return r.json(), r.status_code

    # convert classic setup keys into new setups
    existing_setups, new_setups = upsert_myads(classic_setups=r.json(), user_id=user_id)
    setups = {'existing': existing_setups, 'new': new_setups}

    return setups, 200

