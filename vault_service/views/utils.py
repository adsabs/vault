import urllib.parse as urlparse
import urllib.request, urllib.parse, urllib.error
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
    if isinstance(query, str):
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
    if (isinstance(pointer, str)):
        pointer = urlparse.parse_qs(pointer)


    # clean up
    for k,v in list(pointer.items()):
        if k[0] == 'q':
            query[k] = v
        elif k[0:2] == 'fq' or k[0:4] == 'sort':
            query[k] = v

    # make sure the bigquery is just a string
    if isinstance(bigquery, list):
        bigquery = bigquery[0]
    if not isinstance(bigquery, str):
        raise Exception('The bigquery has to be a string, instead it was {0}'.format(type(bigquery)))

    if len(bigquery) > 0:
        found = False
        for k,v in list(query.items()):
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
    v = list(data.items())
    v = sorted(v, key=lambda x: x[0])
    return urllib.parse.urlencode(v, doseq=True)


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
    # by default, this service will always use the user's token -- the service token should be inserted here only on exceptional occassions
    access_token = request.headers.get('X-Forwarded-Authorization')
    if access_token in (None, '-'): # Make sure it is not just '-' (default value for other microservices)
        access_token = request.headers.get('Authorization', '-')
    new_headers['Authorization'] = access_token
    new_headers['X-Api-Uid'] = headers.get('X-Api-Uid', str(current_app.config['BOOTSTRAP_USER_ID'])) # User ID

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
    # u'daily_t1' --> keywords 1 (daily arxiv)
    # u'groups' --> arxiv classes (daily) - list
    # u'phy_t1' --> keywords 1 (physics)
    # u'phy_t2' --> keywords 2 (physics)
    # u'phy_aut' --> authors (physics)
    # u'pre_t1' --> keywords 1 (weekly arxiv)
    # u'pre_t2' --> keywords 2 (weekly arxiv)
    # u'pre_aut' --> authors (weekly arxiv)
    # u'ast_t1' --> keywords 1 (astronomy)
    # u'ast_t2' --> keywords 2 (astronomy)
    # u'ast_aut' --> authors (astronomy)
    # u'disabled' --> array w/ categories for which emails have been disabled (ast, phy, pre, daily)

    disabled = classic_setups.get('disabled', [])
    weekly_keys = ['ast', 'phy', 'pre']
    # if even one of the weekly keys is set active, leave active
    if set(disabled) == set(weekly_keys):
        weekly_active = False
    else:
        weekly_active = True

    if 'daily' in disabled:
        daily_active = False
    else:
        daily_active = True

    if len(classic_setups.get('lastname', '')) > 0:

        existing, new = _import_citations(classic_setups, user_id, active=weekly_active)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('daily_t1') or classic_setups.get('groups'):
        existing, new = _import_arxiv(classic_setups, user_id, active=daily_active)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('phy_aut') or classic_setups.get('pre_aut') or classic_setups.get('ast_aut'):
        existing, new = _import_authors(classic_setups, user_id, active=weekly_active)
        existing_setups += existing
        new_setups += new

    if classic_setups.get('phy_t1') or classic_setups.get('phy_t2') or classic_setups.get('ast_t1') or \
            classic_setups.get('ast_t2') or classic_setups.get('pre_t1') or classic_setups.get('pre_t2'):

        existing, new = _import_keywords(classic_setups, user_id, active=weekly_active)
        existing_setups += existing
        new_setups += new

    current_app.logger.info('MyADS import for user {0} produced {1} existing setups and {2} new setups'.
                            format(user_id, len(existing_setups), len(new_setups)))

    return existing_setups, new_setups


def _import_citations(classic_setups=None, user_id=None, active=True):
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
        except ormexc.MultipleResultsFound:
            q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data).all()
            current_app.logger.info('User {0} already has multiple myADS citations notifications '
                                    'setup with {1} {2}'.format(user_id,
                                                                classic_setups.get('firstname', ''),
                                                                classic_setups.get('lastname', '')))
            for qi in q:
                existing.append({'id': qi.id, 'template': 'citations', 'name': qi.name, 'frequency': qi.frequency})
        except ormexc.NoResultFound:
            setup = MyADS(user_id=user_id,
                          type='template',
                          template='citations',
                          name='{0} {1} - Citations'.format(classic_setups.get('firstname', ''),
                                                            classic_setups.get('lastname', '')),
                          active=active,
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


def _import_arxiv(classic_setups=None, user_id=None, active=True):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    # classic required groups to be set but did not require keywords to be set
    with current_app.session_scope() as session:
        if classic_setups.get('daily_t1'):
            data = adsparser.parse_classic_keywords(classic_setups.get('daily_t1'))
            name = '{0} - Recent Papers'.format(get_keyword_query_name(data))
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data) \
                    .filter(classic_setups.get('groups') == MyADS.classes) \
                    .filter_by(template='arxiv').one()
                current_app.logger.info('User {0} already has arxiv notifications '
                                        'with keywords {1}'.format(user_id, data))
                existing.append({'id': q.id, 'template': 'arxiv', 'name': q.name, 'frequency': q.frequency})
            except ormexc.MultipleResultsFound:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data) \
                    .filter(classic_setups.get('groups') == MyADS.classes) \
                    .filter_by(template='arxiv').all()
                current_app.logger.info('User {0} already has multiple arxiv notifications '
                                        'with keywords {1}'.format(user_id, data))
                for qi in q:
                    existing.append({'id': qi.id, 'template': 'arxiv', 'name': qi.name, 'frequency': qi.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='arxiv',
                              name=name,
                              active=active,
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
            except ormexc.MultipleResultsFound:
                q = session.query(MyADS).filter_by(user_id=user_id) \
                    .filter(MyADS.classes == classic_setups.get('groups')).all()
                current_app.logger.info('User {0} already has multiple arxiv notifications for arxiv classes {1} '
                                        'with no keywords specified'.format(user_id,
                                                                            classic_setups.get('groups')))
                for qi in q:
                    existing.append({'id': qi.id, 'template': 'arxiv', 'name': qi.name, 'frequency': qi.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='arxiv',
                              name=name,
                              active=active,
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


def _import_authors(classic_setups=None, user_id=None, active=True):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    # concatenate all authors
    data_all = ''
    if classic_setups.get('phy_aut'):
        author_list = classic_setups.get('phy_aut').split('\r\n')
        data = ' OR '.join(['author:"' + x + '"' for x in author_list if x])
        if data not in data_all:
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data
    if classic_setups.get('pre_aut'):
        author_list = classic_setups.get('pre_aut').split('\r\n')
        data = ' OR '.join(['author:"' + x + '"' for x in author_list if x])
        if data not in data_all:
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data
    if classic_setups.get('ast_aut'):
        author_list = classic_setups.get('ast_aut').split('\r\n')
        data = ' OR '.join(['author:"' + x + '"' for x in author_list if x])
        if data not in data_all:
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data

    with current_app.session_scope() as session:
        try:
            q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data_all).one()
            current_app.logger.info('User {0} already has author notifications set up for author query {1}'
                                    .format(user_id, data_all))
            existing.append({'id': q.id, 'template': 'authors', 'name': q.name, 'frequency': q.frequency})
        except ormexc.MultipleResultsFound:
            q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data_all).all()
            current_app.logger.info('User {0} already has multiple author notifications set up for author query {1}'
                                    .format(user_id, data_all))
            for qi in q:
                existing.append({'id': qi.id, 'template': 'authors', 'name': qi.name, 'frequency': qi.frequency})
        except ormexc.NoResultFound:
            setup = MyADS(user_id=user_id,
                          type='template',
                          template='authors',
                          name='Favorite Authors - Recent Papers',
                          active=active,
                          stateful=True,
                          frequency='weekly',
                          data=data_all)

            try:
                session.add(setup)
                session.flush()
                myads_id = setup.id
                session.commit()
                current_app.logger.info('Added myADS authors notifications for user {0} with keywords {1}'
                                        .format(user_id, data_all))
            except exc.IntegrityError as e:
                session.rollback()
                return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

            new.append({'id': myads_id, 'template': 'authors', 'name': setup.name, 'frequency': 'weekly'})

    return existing, new


def _import_keywords(classic_setups=None, user_id=None, active=True):
    existing = []
    new = []
    if not classic_setups or not user_id:
        current_app.logger.info('Classic setup and user ID must be supplied')
        return None, None

    data_1 = ''
    data_2 = ''
    if classic_setups.get('phy_t1'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('phy_t1'))
        if keywords not in data_1:
            if len(data_1) > 0:
                keywords = ' OR ' + keywords
            data_1 += keywords
    if classic_setups.get('pre_t1'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('pre_t1'))
        if keywords not in data_1:
            if len(data_1) > 0:
                keywords = ' OR ' + keywords
            data_1 += keywords
    if classic_setups.get('ast_t1'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('ast_t1'))
        if keywords not in data_1:
            if len(data_1) > 0:
                keywords = ' OR ' + keywords
            data_1 += keywords

    if classic_setups.get('phy_t2'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('phy_t2'))
        if keywords not in data_2:
            if len(data_2) > 0:
                keywords = ' OR ' + keywords
            data_2 += keywords
    if classic_setups.get('pre_t2'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('pre_t2'))
        if keywords not in data_2:
            if len(data_2) > 0:
                keywords = ' OR ' + keywords
            data_2 += keywords
    if classic_setups.get('ast_t2'):
        keywords = adsparser.parse_classic_keywords(classic_setups.get('ast_t2'))
        if keywords not in data_2:
            if len(data_2) > 0:
                keywords = ' OR ' + keywords
            data_2 += keywords

    data_list = []
    if data_1 != '':
        data_list.append(data_1)
    if data_2 != '':
        data_list.append(data_2)
    with current_app.session_scope() as session:
        for d in data_list:
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=d).filter_by(template='keyword').one()
                current_app.logger.info('User {0} already has keyword notifications set up for keywords {1}'
                                        .format(user_id, d))
                existing.append({'id': q.id, 'template': 'keyword', 'name': q.name, 'frequency': q.frequency})
            except ormexc.MultipleResultsFound:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=d).filter_by(template='keyword').all()
                current_app.logger.info('User {0} already has multiple keyword notifications set up for keywords {1}'
                                        .format(user_id, d))
                for qi in q:
                    existing.append({'id': qi.id, 'template': 'keyword', 'name': qi.name, 'frequency': qi.frequency})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='keyword',
                              name=get_keyword_query_name(d),
                              active=active,
                              stateful=False,
                              frequency='weekly',
                              data=d)
                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info('Added myADS keyword notifications for user {0} with keywords {1}'
                                            .format(user_id, d))
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

    keywords = keywords.strip()
    # This regular expression matches any first word not in quotes (e.g., star)
    # or group of one or more words in quotes (e.g., "star" or "gravitational waves")
    # and the whole keywords can be wrapped in parenthesis (they will be ignored)
    first_phrase_or_word_pattern = r'^[\(]*(?P<keyword>"([^"\(\)]*)"|[^ \(\)"]+)[\)]*'
    first = None
    matches = re.match(first_phrase_or_word_pattern, keywords)
    if matches:
        keyword = matches.groupdict().get('keyword')
        if keyword:
            first = keyword

    if not first or len(first) <= 2:
        # Safety control, just in case there is bad data such as '"star' that
        # does not match the previous regex, or the match is too small such as
        # '+(' from query like '+(star OR planets)', grab at least something:
        key_list = keywords.split(' ')
        first = key_list[0].strip('(').strip(')')

    # Make sure it is not an extremely long string
    first = first[:100]

    if first != keywords and len(first) > 0:
        first = first + ', etc.'

    # Make sure there is some result
    if len(first) == 0:
        first = "-"

    if database:
        if database == 'physics':
            first += ' (physics collection)'
        elif database == 'astronomy':
            first += ' (astronomy collection)'
        elif database == 'arxiv':
            first += ' (arXiv e-prints collection)'
        else:
            current_app.logger.warning('Database {} is invalid'.format(database))

    return first.strip('+')
