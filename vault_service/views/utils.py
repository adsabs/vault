import urlparse
import urllib
import json

from flask import current_app
from ..models import User, MyADS

from sqlalchemy import exc
from sqlalchemy.orm import exc as ormexc
from sqlalchemy.sql.expression import all_
from lark import Lark, Transformer, v_args, Visitor

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
        data = 'citations(author:"{0}, {1}")'.format(classic_setups.get('lastname', ''), classic_setups.get('firstname', ''))
        with current_app.session_scope() as session:
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data).first()
                current_app.logger.info('User {0} already has myADS citations notifications '
                                        'setup with {1} {2}'.format(user_id,
                                                                    classic_setups.get('firstname', ''),
                                                                    classic_setups.get('lastname', '')))
                existing_setups.append({'id': q.id, 'template': 'citations', 'name': q.name})
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

                new_setups.append({'id': myads_id, 'template': 'citations', 'name': setup.name})

    if classic_setups.get('daily_t1,') or classic_setups.get('groups'):
        # classic required groups to be set but did not require daily_t1 to be set
        with current_app.session_scope() as session:
            if classic_setups.get('daily_t1,'):
                data = parse_classic_keywords(classic_setups.get('daily_t1,'))
                name = '{0} - Recent Papers'
                try:
                    q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data)\
                        .filter(classic_setups.get('groups') == all_(MyADS.classes))\
                        .filter_by(template='arxiv').first()
                    current_app.logger.info('User {0} already has daily arxiv notifications '
                                            'with keywords {1}'.format(user_id, data))
                    existing_setups.append({'id': q.id, 'template': 'arxiv', 'name': q.name})
                except ormexc.NoResultFound:
                    pass
            else:
                data = None
                name = 'arXiv - Recent Papers'
                try:
                    import pdb
                    pdb.set_trace()
                    q = session.query(MyADS).filter_by(user_id=user_id)\
                        .filter(classic_setups.get('groups') == all_(MyADS.classes)).first()
                    current_app.logger.info('User {0} already has daily arxiv notifications for arxiv classes {1} '
                                            'with no keywords specified'.format(user_id, classic_setups.get('groups')))
                    existing_setups.append({'id': q.id, 'template': 'arxiv', 'name': q.name})
                except ormexc.NoResultFound:
                    pass

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

            new_setups.append({'id': myads_id, 'template': 'arxiv', 'name': setup.name})

    if classic_setups.get('phy_aut,') or classic_setups.get('pre_aut,') or classic_setups.get('ast_aut,'):
        # concatenate all authors (should this be split by collection? then import behavior would differ from standard)
        data_all = ''
        if classic_setups.get('phy_aut,'):
            author_list = classic_setups.get('phy_aut,').split('\r\n')
            data = ' OR '.join(['author:"' + x + '"' for x in author_list])
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data
        if classic_setups.get('pre_aut,'):
            author_list = classic_setups.get('pre_aut,').split('\r\n')
            data = ' OR '.join(['author:"' + x + '"' for x in author_list])
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data
        if classic_setups.get('ast_aut,'):
            author_list = classic_setups.get('ast_aut,').split('\r\n')
            data = ' OR '.join(['author:"' + x + '"' for x in author_list])
            if len(data_all) > 0:
                data = ' OR ' + data
            data_all += data

        with current_app.session_scope() as session:
            try:
                q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=data_all).first()
                current_app.logger.info('User {0} already has author notifications set up for authors {1}'.
                                        format(user_id, data_all))
                existing_setups.append({'id': q.id, 'template': 'authors', 'name': q.name})
            except ormexc.NoResultFound:
                setup = MyADS(user_id=user_id,
                              type='template',
                              template='authors',
                              name='Favorite Authors - Recent Papers',
                              active=True,
                              stateful=True,
                              frequency='weekly',
                              data=data_all)

                try:
                    session.add(setup)
                    session.flush()
                    myads_id = setup.id
                    session.commit()
                    current_app.logger.info('Added myADS authors notifications for user {0} with keywords {1}'.
                                            format(user_id, data_all))
                except exc.IntegrityError as e:
                    session.rollback()
                    return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                new_setups.append({'id': myads_id, 'template': 'authors', 'name': setup.name})

    if classic_setups.get('phy_t1,') or classic_setups.get('phy_t2,') or classic_setups.get('pre_t1,') or \
       classic_setups.get('pre_t2,') or classic_setups.get('ast_t1,') or classic_setups.get('ast_t2,'):

        data_list = []
        if classic_setups.get('phy_t1,'):
            data = parse_classic_keywords(classic_setups.get('phy_t1,'))
            data = data + ' database:physics'
            data_list.append(data)
        if classic_setups.get('phy_t2,'):
            data = parse_classic_keywords(classic_setups.get('phy_t2,'))
            data = data + ' database:physics'
            data_list.append(data)
        if classic_setups.get('pre_t1,'):
            data = parse_classic_keywords(classic_setups.get('pre_t1,'))
            data = data + ' bibstem:arxiv'
            data_list.append(data)
        if classic_setups.get('pre_t2,'):
            data = parse_classic_keywords(classic_setups.get('pre_t2,'))
            data = data + ' bibstem:arxiv'
            data_list.append(data)
        if classic_setups.get('ast_t1,'):
            data = parse_classic_keywords(classic_setups.get('ast_t1,'))
            data = data + ' database:astronomy'
            data_list.append(data)
        if classic_setups.get('ast_t2,'):
            data = parse_classic_keywords(classic_setups.get('ast_t2,'))
            data = data + ' database:astronomy'
            data_list.append(data)

        with current_app.session_scope() as session:
            for d in data_list:
                try:
                    q = session.query(MyADS).filter_by(user_id=user_id).filter_by(data=d).\
                        filter_by(template='keyword').first()
                    current_app.logger.info('User {0} already has keyword notifications set up for keywords {1}'.
                                            format(user_id, d))
                    existing_setups.append({'id': q.id, 'template': 'keyword', 'name': q.name})
                except ormexc.NoResultFound:
                    setup = MyADS(user_id=user_id,
                                  type='template',
                                  template='keyword',
                                  name=d,
                                  active=True,
                                  stateful=False,
                                  frequency='weekly',
                                  data=d)
                    try:
                        session.add(setup)
                        session.flush()
                        myads_id = setup.id
                        session.commit()
                        current_app.logger.info('Added myADS keyword notifications for user {0} with keywords {1}'.
                                                format(user_id, d))
                    except exc.IntegrityError as e:
                        session.rollback()
                        return json.dumps({'msg': 'New myADS setup was not saved, error: {0}'.format(e)}), 500

                    new_setups.append({'id': myads_id, 'template': 'keyword', 'name': setup.name})

    current_app.logger.info('MyADS import for user {0} produced {1} existing setups and {2} new setups'.
                            format(user_id, len(existing_setups), len(new_setups)))

    return existing_setups, new_setups


# class ParseToDict(Transformer):
#     @v_args(inline=True)
#     def data_item(self, name, *numbers):
#         return name.value, [n.value for n in numbers]
#
#     start = dict
#
#
# class EvalExpressions(Transformer):
#     def expr(self, args):
#             return eval(args[0])


def parse_classic_keywords(data):
    # write a parser (using lark?) to convert Classic-style keyword setups to BBB-style (e.g. Classic uses default
    # OR, which has to be explicit in BBB (it uses default AND)

    # grammar1 = Lark(r"""
    #
    #         start: clause
    #
    #         clause.2: ("(" clause ")" query*)*
    #             | query
    #             | clause
    #
    #         query: (qterm | phrase | first_author | operator | prepend)+
    #
    #         prepend: /=/ | /\+/ | /\-/
    #
    #         first_author: "^" WORD
    #
    #         phrase: DOUBLE_QUOTED_STRING | SINGLE_QUOTED_STRING
    #
    #         DOUBLE_QUOTED_STRING  : /"[^"]*"/
    #         SINGLE_QUOTED_STRING  : /'[^']*'/
    #
    #         operator: OPERATOR
    #
    #         OPERATOR.2: "and" | "AND" | "or" | "OR" | "not" | "NOT"
    #
    #         qterm: WORD -> qterm
    #
    #         %import common.WS
    #         %import common.WORD
    #
    #         %ignore WS
    #         %ignore /[\],\*]+/
    #
    #     """, parser="lalr")

    grammar = Lark(r"""

    
    start: clause+ (operator clause)*
    
    clause: ("(" clause (operator? clause)* ")") 
        | query+

    query: qterm
    
    qterm: anyterm -> qterm | phrase | prepend
    
    prepend.2: /=\w/
        
    phrase: DOUBLE_QUOTED_STRING | SINGLE_QUOTED_STRING

    DOUBLE_QUOTED_STRING.3  : /"[^"]*"/ | /\+"[^"]*"/ | /\-"[^"]*"/
    SINGLE_QUOTED_STRING.3  : /'[^']*'/ | /\+'[^']*'/ | /\-'[^']*'/
    
    anyterm: /[^)^\] \(^\n^\r]+/
    
    operator: OPERATOR | NEWLINE

    OPERATOR.2: "and" | "AND" | "or" | "OR" | "not" | "NOT" | "AND NOT" | "and not" | /,/ | /\+/ | /\-/

    %import common.LETTER
    %import common.ESCAPED_STRING
    %import common.FLOAT
    %import common.DIGIT
    %import common.WS_INLINE
    %import common.NEWLINE
    
    %ignore WS_INLINE
    
    """, parser="lalr")

    tree = grammar.parse(data)
    # for i in tree.iter_subtrees_topdown():
    #     print 'i: ' + i + ' data: ' + i.data + ' children: ' + i.children

    #res = ParseToDict().transform(tree)

    return tree

class TreeVisitor(Visitor):
    def start(self, node):
        out = []
        for x in node.children:
            if hasattr(x, 'output'):
                out.append(getattr(x, 'output'))
            else:
                pass
        tmp = ' '.join(out)

        node.output = tmp

    def clause(self, node):
        out = []
        ops = ['and', 'AND', 'or', 'OR', 'not', 'NOT', 'and not', 'AND NOT']
        for x in node.children:
            if hasattr(x, 'output'):
                out.append(getattr(x, 'output'))
        output = []
        i = 0
        for o in out:
            if i == 0:
                output.append(o)
            else:
                if output[i-1] in ops:
                    output.append(o)
                elif o in ops:
                    output.append(o)
                else:
                    output.append('OR ' + o)
            i += 1

        node.output = "({0})".format(' '.join(output))

    def query(self, node):
        node.output = node.children[0].output

    def qterm(self, node):
        node.output = node.children[0].output

    def anyterm(self, node):
        node.output = '{0}'.format(node.children[0].value.replace("'", "\'").replace('"', '\"').strip())
        #print 'anyterm: ', node.output

    def phrase(self, node):
        node.output = node.children[0].value.strip()
        #print 'phrase: ', node.output

    def prepend(self, node):
        node.output = node.children[0].value.strip()
        #print 'prepend: ', node.output

    def operator(self, node):
        v = node.children[0].value
        if v not in ['and', 'AND', 'or', 'OR', 'not', 'NOT', 'and not', 'AND NOT']:
            v = 'OR'
        else:
            v = v

        node.output = v
        #print 'operator: ', node.output

