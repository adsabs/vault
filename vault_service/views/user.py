from flask import Blueprint
from flask import current_app
from flask import request, url_for

import json
from hashlib import md5
import urllib.parse as urlparse
import datetime

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from ..models import Query, User, MyADS, Library
from .utils import check_request, cleanup_payload, make_solr_request, upsert_myads, get_keyword_query_name
from flask_discoverer import advertise
from dateutil import parser
from adsmutils import get_date

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
                'query': q.query.decode('utf8'), # bytes to string
                'numfound': q.numfound }), 200

    # get the query data
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': str(e)}), 400

    if len(list(payload.keys())) == 0:
        raise Exception('Query cannot be empty')

    payload = cleanup_payload(payload)


    # check we don't have this query already. If the query exist do not reissue query but return 
    # values previously stored in the database (infinite cache like behavior)
    query = json.dumps(payload).encode('utf8')
    # digest is made of a bytestream
    qid = md5((headers['X-Api-Uid'].encode('utf8') + query)).hexdigest()
    with current_app.session_scope() as session:
        q = session.query(Query).filter_by(qid=qid).first()
        if q:
            return json.dumps({'qid': qid, 'numFound': q.numfound}), 200

    # else, reissue new qid
    # first, check the query is valid
    solrq = payload['query'] + '&wt=json'
    r = make_solr_request(query=solrq, bigquery=payload['bigquery'], headers=headers)
    if r.status_code != 200:
        return json.dumps({'msg': 'Could not verify the query.', 'query': payload, 'reason': r.text}), 404

    # extract number of docs found, save that number of documents from when the qid was created
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

        return json.dumps({'qid': qid, 'numFound': num_found}), 200


@advertise(scopes=['execute-query'], rate_limit = [1000, 3600*24])
@bp.route('/execute_query/<queryid>', methods=['GET'])
def execute_query(queryid):
    '''Allows you to execute stored query. With this endpoint you can return parameters for the 
    previously asigned and stored query in the database (such as current number of documents in
    the database.
    '''

    with current_app.session_scope() as session:
        q = session.query(Query).filter_by(qid=queryid).first()
        if not q:
            return json.dumps({'msg': 'Query not found: ' + queryid}), 404
        q_query = q.query.decode('utf8')

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
            elif isinstance(fq, str):
                fq = [fq, '{!bitset}']
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
        return json.dumps({'msg': hasattr(e, 'message') and e.message or e.description}), 400

    user_id = int(headers['X-Api-Uid'])

    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': "Sorry, you can't use this service as an anonymous user"}), 400

    if request.method == 'GET':
        with current_app.session_scope() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return '{}', 200
            response_data = user.user_data.copy() if user.user_data else {}
            if user.library_id:
                library = session.query(Library).filter_by(id=user.library_id).first()
                if library:
                    response_data['link_server'] = library.libserver
            return json.dumps(response_data) or '{}', 200

    elif request.method == 'POST':
        # Remove link_server from payload if present
        library_server = payload.pop('link_server', None)
        library = None
        # limit both number of keys and length of value to keep db clean
        if len(max(list(payload.values()), key=len)) > current_app.config['MAX_ALLOWED_JSON_SIZE']:
            return json.dumps({'msg': 'You have exceeded the allowed storage limit (length of values), no data was saved'}), 400
        if len(list(payload.keys())) > current_app.config['MAX_ALLOWED_JSON_KEYS']:
            return json.dumps({'msg': 'You have exceeded the allowed storage limit (number of keys), no data was saved'}), 400

        with current_app.session_scope() as session:
            user = session.query(User).filter_by(id=user_id).with_for_update(of=User).first()
            if not user:
                data = payload.copy()
                user = User(id=user_id, user_data=data)
                session.add(user)
            else:
                try:
                    data = user.user_data or {}
                except TypeError:
                    data = {}
                data.update(payload)
                user.user_data = data

            # Handle library selection (set or clear)
            if library_server is not None:
                if library_server:
                    library = session.query(Library).filter_by(libserver=library_server).first()
                    user.library_id = library.id if library else None
                else:
                    user.library_id = None

            session.begin_nested()
            try:
                session.commit()
                # Prepare response data (do not mutate user.user_data in-place)
                response_data = data.copy()
                if user.library_id and library:
                    response_data['link_server'] = library.libserver
            except exc.IntegrityError:
                session.rollback()
                return json.dumps({'msg': 'We have hit a db error! The world is crumbling all around... (eh, btw, your data was not saved)'}), 500

        return json.dumps(response_data), 200


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

    user_id = int(headers['X-Api-Uid'])

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
    
    scix_ui_header = current_app.config['SCIXPLORER_HOST'] in request.headers.get('Host', '')

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
            return json.dumps({'msg': 'Bad data passed; at least one required keyword is missing'}), 400
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
                          scix_ui=scix_ui_header,
                          frequency=payload.get('frequency'))

    elif ntype == 'template':
        # handles both None values and empty strings
        if not payload.get('data'):
            payload['old_data'] = payload.get('data', None)
            payload['data'] = None

        if 'template' not in payload:
            return json.dumps({'msg': 'Bad data passed; at least one required keyword is missing'}), 400

        if not payload['template'] == 'arxiv' and not isinstance(payload.get('data'), str):
            return json.dumps({'msg': 'Bad data passed; data keyword should be a string'}), 400

        if payload['template'] == 'arxiv':
            if not isinstance(payload.get('classes'), list):
                return json.dumps({'msg': 'Bad data passed; classes keyword should be a list'}), 400
            if not set(payload.get('classes')).issubset(set(current_app.config['ALLOWED_ARXIV_CLASSES'])):
                return json.dumps({'msg': 'Bad data passed; verify arXiv classes are correct'}), 400

        if payload.get('data', None):
            # verify data/query
            solrq = 'q=' + payload.get('data') + '&wt=json'
            r = make_solr_request(query=solrq, headers=headers)
            if r.status_code != 200:
                return json.dumps({'msg': 'Could not verify the query: {0}; reason: {1}'.format(payload, r.text)}), 400
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
                      scix_ui=scix_ui_header,
                      data=data)
    else:
        return json.dumps({'msg': 'Bad data passed; type must be query or template'}), 400

    # update/store the template query data, get a qid back
    with current_app.session_scope() as session:
        try:
            session.add(setup)
            session.flush()
            # qid is an int in the myADS table
            myads_id = setup.id
            
            # If user is coming from scixplorer but existing notifications don't have scix_ui set to True, update them
            if scix_ui_header:
                # Check if there are any of user's notifications with scix_ui=False
                existing_notifications = session.query(MyADS).filter_by(user_id=user_id).filter_by(scix_ui=False).all()
                current_app.logger.info(f'Total notifications to update: {len(existing_notifications)}')
                if existing_notifications:
                    for notification in existing_notifications:
                        current_app.logger.info(f'Updating notification: {notification.id} for user: {user_id}')
                        notification.scix_ui = True
            
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

    # verify data/query
    if payload.get('data', None):
        solrq = 'q=' + payload['data'] + '&wt=json'
        r = make_solr_request(query=solrq, headers=headers)
        if r.status_code != 200:
            return json.dumps({'msg': 'Could not verify the query: {0}; reason: {1}'.format(payload, r.text)}), 400

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
                elif setup.data and setup.name == name_template.format(get_keyword_query_name(setup.data)):
                    setup_data = payload.get('data', setup.data)
                    if setup_data:
                        setup.name = name_template.format(get_keyword_query_name(setup_data))
                # if name wasn't provided and previous name wasn't templated, keep whatever was there
            elif payload.get('template', setup.template) == 'citations':
                name_template = '{0} - Citations'
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
                elif setup.data and setup.name == name_template.format(setup.data):
                    setup_data = payload.get('data', setup.data)
                    if setup_data:
                        setup.name = name_template.format(setup_data)
            elif payload.get('template', setup.template) == 'authors':
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
            elif payload.get('template', setup.template) == 'keyword':
                name_template = '{0}'
                if payload.get('name', None) and payload.get('name') != setup.name:
                    setup.name = payload.get('name')
                elif setup.data and setup.name == name_template.format(setup.data):
                    setup_data = payload.get('data', setup.data)
                    if setup_data:
                        setup.name = '{0}'.format(get_keyword_query_name(setup_data))
            else:
                return json.dumps({'msg': 'Wrong template type passed'}), 400
            if payload.get('data', None) and not isinstance(payload.get('data', setup.data), str):
                return json.dumps({'msg': 'Bad data passed; data keyword should be a string'}), 400
            if setup.data:
                setup.data = payload.get('data', setup.data)
            else:
                setup.data = payload.get('data')
            if payload.get('template', setup.template) == 'arxiv':
                if not isinstance(payload.get('classes', setup.classes), list):
                    return json.dumps({'msg': 'Bad data passed; classes keyword should be a list'}), 400
                if payload.get('classes') and not set(payload.get('classes')).issubset(set(current_app.config['ALLOWED_ARXIV_CLASSES'])):
                    return json.dumps({'msg': 'Bad data passed; verify arXiv classes are correct'}), 400
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


@advertise(scopes=[], rate_limit=[1000, 3600*24])
@bp.route('/notification_query/<myads_id>', methods=['GET'])
def execute_myads_query(myads_id):
    """
    Returns the constructed query for a single templated myADS notification, ready to execute
    :param myads_id: ID of a single notification
    :return: list of dicts; constructed query, dates are such that it's meant to be run today:
                    [{q: query params,
                     sort: sort string}]
    """

    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400

    user_id = int(headers['X-Api-Uid'])

    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    with current_app.session_scope() as session:
        setup = session.query(MyADS).filter_by(user_id=user_id).filter_by(id=myads_id).first()
        if setup is None:
            return '{}', 404

        data = setup.data
        if data is None and setup.query_id:
            data = _get_general_query_data(session, setup.query_id)
        query = _create_myads_query(setup.template, setup.frequency, data, classes=setup.classes)

    return json.dumps(query)

def _get_general_query_data(session, query_id):
    """
    Retrieve general myADS query stored in a qid and parse it to return a dict
    """
    data = {}
    q = session.query(Query).filter_by(id=query_id).one()
    if q and q.query:
        # query is bytes object, we turn it into string (unicode)
        query = json.loads(q.query.decode('utf8')).get('query')
        if query:
            # Parse url encoded query string such as:
            # u'fq=%7B%21type%3Daqp+v%3D%24fq_database%7D&fq_database=%28database%3Aastronomy%29&q=star&sort=citation_count+desc%2C+bibcode+desc'
            # if bytestring is passed (python3) bytes are returned, not strings
            data = urlparse.parse_qs(query)
    return data

def _create_myads_query(template_type, frequency, data, classes=None, start_isodate=None):
    """
    Creates a query based on the stored myADS setup (for templated queries only)
    :param frequency: daily or weekly
    :param data: keywords or other stored query template data
    :param classes: arXiv classes, only required for arXiv template queries
    :return: out: list of dicts; constructed query, dates are such that it's meant to be run today:
                    [{q: query params,
                     sort: sort string}]
    """

    out = []
    beg_pubyear = (get_date() - datetime.timedelta(days=180)).year
    end_date = get_date().date()
    weekly_time_range = current_app.config.get('MYADS_WEEKLY_TIME_RANGE', 6)
    if start_isodate:
        start_isodate = parser.parse(start_isodate).date()
    if template_type in ('arxiv', None):
        if frequency == 'daily':
            # on Mondays, deal with the weekend properly
            if get_date().weekday() == 0:
                time_range = current_app.config.get('MYADS_DAILY_TIME_RANGE', 2)
                start_date = (get_date() - datetime.timedelta(days=time_range)).date()
            else:
                start_date = get_date().date()
        elif frequency == 'weekly':
            start_date = (get_date() - datetime.timedelta(days=weekly_time_range)).date()

        # if the provided last sent date is prior to normal start date, use the earlier date
        if start_isodate and (start_isodate < start_date):
            start_date = start_isodate

    if template_type == 'arxiv':
        if not classes:
            raise Exception('Classes must be provided for an arXiv templated query')
        if type(classes) != list:
            tmp = [classes]
        else:
            tmp = classes
        classes = 'arxiv_class:(' + ' OR '.join([x + '.*' if '.' not in x else x for x in tmp]) + ')'
        keywords = data
        if frequency == 'daily':
            connector = [' ', ' NOT ']
            # keyword search should be sorted by score, "other recent" should be sorted by bibcode
            sort_w_keywords = ['score desc, date desc', 'date desc']
        elif frequency == 'weekly':
            connector = [' ']
            sort_w_keywords = ['score desc, date desc']
        if not keywords:
            q = 'bibstem:arxiv {0} entdate:["{1}Z00:00" TO "{2}Z23:59"] pubdate:[{3}-00 TO *]'.\
                     format(classes, start_date, end_date, beg_pubyear)
            sort = 'date desc'
            out.append({'q': q, 'sort': sort})
        else:
            for c, s in zip(connector, sort_w_keywords):
                q = 'bibstem:arxiv ({0}{1}({2})) entdate:["{3}Z00:00" TO "{4}Z23:59"] pubdate:[{5}-00 TO *]'.\
                    format(classes, c, keywords, start_date, end_date, beg_pubyear)
                sort = s
                
                out.append({'q': q, 'sort': sort})
    elif template_type == 'citations':
        keywords = data
        q = 'citations({0})'.format(keywords)
        sort = 'entry_date desc, date desc'
        out.append({'q': q, 'sort': sort})
    elif template_type == 'authors':
        keywords = data
        start_date = (get_date() - datetime.timedelta(days=weekly_time_range)).date()
        if start_isodate and (start_isodate < start_date):
            start_date = start_isodate
        q = '{0} entdate:["{1}Z00:00" TO "{2}Z23:59"] pubdate:[{3}-00 TO *]'.\
            format(keywords, start_date, end_date, beg_pubyear)
        sort = 'score desc, date desc'
        out.append({'q': q, 'sort': sort})
    elif template_type == 'keyword':
        keywords = data
        start_date = (get_date() - datetime.timedelta(days=weekly_time_range)).date()
        if start_isodate and (start_isodate < start_date):
            start_date = start_isodate
        # most recent
        q = '{0} entdate:["{1}Z00:00" TO "{2}Z23:59"] pubdate:[{3}-00 TO *]'.\
            format(keywords, start_date, end_date, beg_pubyear)
        sort = 'entry_date desc, date desc'
        out.append({'q': q, 'sort': sort})
        # most popular
        q = 'trending({0})'.format(keywords)
        sort = 'score desc, date desc'
        out.append({'q': q, 'sort': sort})
        # most cited
        q = 'useful({0})'.format(keywords)
        sort = 'score desc, date desc'
        out.append({'q': q, 'sort': sort})
    elif template_type is None and data:
        # General query - for consistency with the rest of templates,
        # remove lists such as:
        #   {u'fq': [u'{!type=aqp v=$fq_database}'],
        #    u'fq_database': [u'(database:astronomy)'],
        #    u'q': [u'star'],
        #    u'sort': [u'citation_count desc, bibcode desc']}
        # but only if there is only one element
        general = {k: v[0] if isinstance(v, (list, tuple)) and len(v) == 1 else v for k, v in list(data.items())}
        if 'q' in general:
            general['q'] = '{0} entdate:["{1}Z00:00" TO "{2}Z23:59"] pubdate:[{3}-00 TO *]'.\
                format(general['q'], start_date, end_date, beg_pubyear)
        out.append(general)

    return out

@advertise(scopes=['ads-consumer:myads'], rate_limit = [1000, 3600*24])
@bp.route('/get-myads/<user_id>', methods=['GET'])
@bp.route('/get-myads/<user_id>/<start_isodate>', methods=['GET'])
def get_myads(user_id, start_isodate=None):
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
                 'scix_ui': s.scix_ui,
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
                    query = None
                else:
                    data = _get_general_query_data(session, s.query_id)
                    query = _create_myads_query(s.template, s.frequency, data, classes=s.classes, start_isodate=start_isodate)
            else:
                qid = None
                data = s.data
                query = _create_myads_query(s.template, s.frequency, data, classes=s.classes, start_isodate=start_isodate)

            o['qid'] = qid
            o['query'] = query

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


@advertise(scopes=['ads-consumer:myads'], rate_limit = [1000, 3600*24])
@bp.route('/myads-status-update/<user_id>', methods=['PUT'])
def myads_status(user_id):
    """
    Enable/disable all myADS notifications for a given user

    payload: {'active': True/False}

    :param user_id: ID of user to update
    :return:
    """
    try:
        payload, headers = check_request(request)
    except Exception as e:
        return json.dumps({'msg': e.message or e.description}), 400


    if 'active' in payload:
        status = {'active': payload['active']}
    else:
        return 'Only status updates allowed', 400

    with current_app.session_scope() as session:
        all_setups = session.query(MyADS).filter_by(user_id=user_id).order_by(MyADS.id.asc()).all()
        if len(all_setups) == 0:
            return '{}', 204
        ids = [s.id for s in all_setups]

    for s in ids:
        msg, status_code = _edit_myads_notification(status, headers, user_id, s)
        if status_code != 200:
            outmsg = 'Error %s while updating status for setup %s for user %s. Error message: %s',\
                     status_code, s, user_id, msg
            return json.dumps({'msg': outmsg}), 500

    return '{}', 200


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

    # this header is always set by adsws, so we trust it
    user_id = int(headers['X-Api-Uid'])

    # use service token here; elevated operation
    if current_app.config.get('SERVICE_TOKEN', None):
        headers['Authorization'] = current_app.config['SERVICE_TOKEN']


    if user_id == current_app.config['BOOTSTRAP_USER_ID']:
        return json.dumps({'msg': 'Sorry, you can\'t use this service as an anonymous user'}), 400

    r = current_app.client.get(current_app.config['HARBOUR_MYADS_IMPORT_ENDPOINT'] % user_id, headers=headers)

    if r.status_code != 200:
        return json.dumps(r.json()), r.status_code

    # convert classic setup keys into new setups
    existing_setups, new_setups = upsert_myads(classic_setups=r.json(), user_id=user_id)
    setups = {'existing': existing_setups, 'new': new_setups}

    return json.dumps(setups), 200

