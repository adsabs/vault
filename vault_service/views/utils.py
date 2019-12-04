import urlparse
import urllib
import json
import re

import adsparser
from flask import current_app
from ..models import User, MyADS

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from sqlalchemy.sql.expression import all_


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
    new_headers['X-Adsws-Uid'] = headers.get('X-Adsws-Uid', str(current_app.config['BOOTSTRAP_USER_ID'])) # User ID

    return (payload, new_headers)


def upsert_myads(classic_setups, user_id):
    # check to see if user has a myADS setup already
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

    new_setups = []
    existing_setups = []
    # painstakingly step through all the keys in the Classic setup
    # u'id' --> user ID - int
    # u'email' --> user email
    # u'firstname' --> user first name (for citations)
    # u'lastname' --> user last name (for citations)
    # u'daily_t1,' --> keywords 1 (daily arxiv)
    # u'groups' --> arxiv classes (daily) - list
    # u'phy_t1,' --> keywords 1 (physics)
    # u'phy_t2,' --> keywords 2 (physics)
    # u'phy_aut,' --> authors (physics)
    # u'pre_t1,' --> keywords 1 (weekly arxiv)
    # u'pre_t2,' --> keywords 2 (weekly arxiv)
    # u'pre_aut,' --> authors (weekly arxiv)
    # u'ast_t1,' --> keywords 1 (astronomy)
    # u'ast_t2,' --> keywords 2 (astronomy)
    # u'ast_aut,' --> authors (astronomy)

    if len(classic_setups.get('lastname', '')) > 0:
        existing, new = _import_citations(classic_setups, user_id)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('daily_t1,') or classic_setups.get('groups'):
        existing, new = _import_arxiv(classic_setups, user_id)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('phy_aut,') or classic_setups.get('pre_aut,') or classic_setups.get('ast_aut,'):
        existing, new = _import_authors(classic_setups, user_id)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('phy_t1,') or classic_setups.get('phy_t2,') or classic_setups.get('ast_t1,') or \
            classic_setups.get('ast_t2,') or classic_setups.get('pre_t1,') or classic_setups.get('pre_t2,'):

        existing, new = _import_keywords(classic_setups, user_id)
        existing_setups += existing
        new_setups += new

    current_app.logger.info('MyADS import for user {0} produced {1} existing setups and {2} new setups'.
                            format(user_id, len(existing_setups), len(new_setups)))

    return existing_setups, new_setups


def _import_citations(classic_setups=None, user_id=None):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    data = 'author:"{0}, {1}"'.format(classic_setups.get('lastname', ''),
                                       classic_setups.get('firstname', ''))
    with current_app.session_scope() as session:
        try:
            q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data).one()
            current_app.logger.info('User {0} already has myADS citations notifications '
                                    'setup with {1} {2}'.format(user_id,
                                                                classic_setups.get('firstname', ''),
                                                                classic_setups.get('lastname', '')))
            existing.append({'id': q.id, 'template': 'citations', 'name': q.name, 'frequency': q.frequency})
        except ormexc.NoResultFound:
            setup = MyADS(user_id=user_id,
                          type='template',
                          template='citations',
                          name='{0} {1} - Citations'.format(classic_setups.get('firstname', ''),
                                                            classic_setups.get('lastname', '')),
                          active=True,
                          stateful=True,
                          frequency='weekly',
                          data=data)
            try:
                session.add(setup)
                session.flush()
                myads_id = setup.id
                session.commit()
                current_app.logger.info('Added myADS citations notifications '
                                        'for {0} {1}'.format(classic_setups.get('firstname', ''),
                                                             classic_setups.get('lastname', '')))
            except exc.IntegrityError as e:
                session.rollback()
                return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

            new.append({'id': myads_id, 'template': 'citations', 'name': setup.name, 'frequency': 'weekly'})

    return existing, new


def _import_arxiv(classic_setups=None, user_id=None):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    # classic required groups to be set but did not require keywords to be set
    with current_app.session_scope() as session:
        if classic_setups.get('daily_t1,'):
            data = adsparser.parse_classic_keywords(classic_setups.get('daily_t1,'))
            name = '{0} - Recent Papers'.format(get_keyword_query_name(data))
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data) \
                    .filter(classic_setups.get('groups') == MyADS.classes) \
                    .filter_by(template='arxiv').one()
                current_app.logger.info('User {0} already has arxiv notifications '
                                        'with keywords {1}'.format(user_id, data))
                existing.append({'id': q.id, 'template': 'arxiv', 'name': q.name, 'frequency': q.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='arxiv',
                              name=name,
                              active=True,
                              stateful=False,
                              frequency='daily',
                              data=data,
                              classes=classic_setups.get('groups'))

                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info(
                        'Added myADS arxiv notifications for user {0} with keywords {1} and classes'
                        '{2}'.format(user_id, data, classic_setups.get('groups')))
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                new.append({'id': myads_id, 'template': 'arxiv', 'name': setup.name, 'frequency': 'daily'})
        else:
            data = None
            name = 'arXiv - Recent Papers'
            try:
                q = session.query(MyADS).filter_by(user_id=user_id) \
                    .filter(MyADS.classes == classic_setups.get('groups')).one()
                current_app.logger.info('User {0} already has arxiv notifications for arxiv classes {1} '
                                        'with no keywords specified'.format(user_id,
                                                                            classic_setups.get('groups')))
                existing.append({'id': q.id, 'template': 'arxiv', 'name': q.name, 'frequency': q.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='arxiv',
                              name=name,
                              active=True,
                              stateful=False,
                              frequency='daily',
                              data=data,
                              classes=classic_setups.get('groups'))

                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info('Added myADS arxiv notifications for user {0} with keywords {1} and classes'
                                            '{2}'.format(user_id, data, classic_setups.get('groups')))
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                new.append({'id': myads_id, 'template': 'arxiv', 'name': setup.name, 'frequency': 'daily'})

    return existing, new


def _import_authors(classic_setups=None, user_id=None):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    # concatenate all authors (should this be split by collection? then import behavior would differ from standard)
    data_list = []
    classes_list = []
    names_list = []
    if classic_setups.get('phy_aut,'):
        author_list = classic_setups.get('phy_aut,').split('\r\n')
        data = 'database:physics ({})'.format(' OR '.join(['author:"' + x + '"' for x in author_list]))
        data_list.append(data)
        classes_list.append(None)
        names_list.append('Favorite Authors (physics collection) - Recent Papers')
    if classic_setups.get('pre_aut,'):
        author_list = classic_setups.get('pre_aut,').split('\r\n')
        data = 'bibstem:arxiv ({})'.format(' OR '.join(['author:"' + x + '"' for x in author_list]))
        data_list.append(data)
        classes_list.append(classic_setups.get('groups', None))
        names_list.append('Favorite Authors (arXiv e-prints collection) - Recent Papers')
    if classic_setups.get('ast_aut,'):
        author_list = classic_setups.get('ast_aut,').split('\r\n')
        data = 'database:astronomy ({})'.format(' OR '.join(['author:"' + x + '"' for x in author_list]))
        data_list.append(data)
        classes_list.append(None)
        names_list.append('Favorite Authors (astronomy collection) - Recent Papers')

    with current_app.session_scope() as session:
        for d, c, n in zip(data_list, classes_list, names_list):
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=d).filter_by(classes=c).one()
                current_app.logger.info('User {0} already has author notifications set up for author query {1} '
                                        'with classes {2}'.format(user_id, d, c))
                existing.append({'id': q.id, 'template': 'authors', 'name': q.name, 'frequency': q.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='authors',
                              name=n,
                              active=True,
                              stateful=True,
                              frequency='weekly',
                              data=d,
                              classes=c)

                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info('Added myADS authors notifications for user {0} with keywords {1} '
                                            'and classes {2}'.format(user_id, d, c))
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                new.append({'id': myads_id, 'template': 'authors', 'name': setup.name, 'frequency': 'weekly'})

    return existing, new


def _import_keywords(classic_setups=None, user_id=None):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    data_list = []
    classes_list = []
    name_list = []
    if classic_setups.get('phy_t1,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('phy_t1,'))
        data = 'database:physics ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(None)
        name_list.append(get_keyword_query_name(keywords, database='physics'))
    if classic_setups.get('phy_t2,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('phy_t2,'))
        data = 'database:physics ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(None)
        name_list.append(get_keyword_query_name(keywords, database='physics'))
    if classic_setups.get('pre_t1,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('pre_t1,'))
        data = 'bibstem:arxiv ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(classic_setups.get('groups', None))
        name_list.append(get_keyword_query_name(keywords, database='arxiv'))
    if classic_setups.get('pre_t2,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('pre_t2,'))
        data = 'bibstem:arxiv ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(classic_setups.get('groups', None))
        name_list.append(get_keyword_query_name(keywords, database='arxiv'))
    if classic_setups.get('ast_t1,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('ast_t1,'))
        data = 'database:astronomy ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(None)
        name_list.append(get_keyword_query_name(keywords, database='astronomy'))
    if classic_setups.get('ast_t2,'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('ast_t2,'))
        data = 'database:astronomy ({})'.format(keywords)
        data_list.append(data)
        classes_list.append(None)
        name_list.append(get_keyword_query_name(keywords, database='astronomy'))

    with current_app.session_scope() as session:
        for d, c, n in zip(data_list, classes_list, name_list):
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=d).filter_by(classes=c). \
                    filter_by(template='keyword').one()
                current_app.logger.info('User {0} already has keyword notifications set up for keywords {1} '
                                        'with classes {2}'.format(user_id, d, c))
                existing.append({'id': q.id, 'template': 'keyword', 'name': q.name, 'frequency': q.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='keyword',
                              name=n,
                              active=True,
                              stateful=False,
                              frequency='weekly',
                              data=d,
                              classes=c)
                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info('Added myADS keyword notifications for user {0} with keywords {1} '
                                            'and classes {2}'.format(user_id, d, c))
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                new.append({'id': myads_id, 'template': 'keyword', 'name': setup.name, 'frequency': 'weekly'})

    return existing, new


def get_keyword_query_name(keywords, database=None):
    """
    For a given keyword string, return the first word or phrase, to be used in the query name
    :param keywords: string of keywords
    :param database: database (physics, astronomy, arxiv) to be included in query name, if needed
    :return: first word or phrase
    """
    key_list = keywords.split(' ')
    first = key_list[0]

    if '"' in first and len(key_list) > 1:
        phrase = first
        i = 1
        while '"' not in key_list[i]:
            phrase = phrase + ' ' + key_list[i]
            i += 1
        first = phrase + ' ' + key_list[i]

    if first != keywords:
        first = first + ', etc.'

    if database:
        if database == 'physics':
            first += ' (physics collection)'
        elif database == 'astronomy':
            first += ' (astronomy collection)'
        elif database == 'arxiv':
            first += ' (arXiv e-prints collection)'
        else:
            current_app.logger.warning('Database {} is invalid'.format(database))

    return first.strip('(').strip('+')
