import sys, os
from urllib.parse import urlencode
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from io import StringIO
import datetime
from dateutil import parser

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from vault_service.models import Query, User, MyADS
from vault_service.views import utils
from vault_service.tests.base import TestCaseDatabase
import adsmutils

class TestServices(TestCaseDatabase):
    '''Tests that each route is an http response'''

    @httpretty.activate
    def test_query_storage(self):
        '''Tests the ability to store queries'''

        httpretty.register_uri(
            httpretty.GET, self.app.config.get('VAULT_SOLR_QUERY_ENDPOINT'),
            content_type='application/json',
            status=200,
            body="""{
            "responseHeader":{
            "status":0, "QTime":0,
            "params":{ "fl":"title,bibcode", "indent":"true", "wt":"json", "q":"*:*"}},
            "response":{"numFound":10456930,"start":0,"docs":[
              { "bibcode":"2005JGRC..110.4002G" },
              { "bibcode":"2005JGRC..110.4003N" },
              { "bibcode":"2005JGRC..110.4004Y" }]}}""")

        r = self.client.post(url_for('user.query'),
                headers={'Authorization': 'secret'},
                data=json.dumps({'q': 'foo:bar'}),
                content_type='application/json')

        self.assertStatus(r, 200)


        self.assertTrue(r.json['qid'], 'qid is missing')
        with self.app.session_scope() as session:
            q = session.query(Query).filter_by(qid=r.json['qid']).first()

            self.assertTrue(q.qid == r.json['qid'], 'query was not saved')
            self.assertTrue(q.query == json.dumps({"query": "q=foo%3Abar", "bigquery": ""}).encode('utf8'), 'query was not saved')
            session.expunge_all()


        # now test that the query gets executed
        #self.app.debug = True
        r = self.client.get(url_for('user.execute_query', queryid=q.qid),
                headers={'Authorization': 'secret'},
                data=json.dumps({'fl': 'title,abstract'}),
                content_type='application/json')

        self.assertStatus(r, 200)

    @httpretty.activate
    def test_bigquery_storage(self):
        '''Tests the ability to store bigqueries'''

        def callback(request, uri, headers):
            headers['Content-Type'] = 'application/json'
            out = """{
            "responseHeader":{
            "status":0, "QTime":0,
            "params":%s},
            "response":{"numFound":10456930,"start":0,"docs":[
              { "bibcode":"2005JGRC..110.4002G" },
              { "bibcode":"2005JGRC..110.4003N" },
              { "bibcode":"2005JGRC..110.4004Y" }]}}""" % (json.dumps(request.querystring),)
            return (200, headers, out)


        httpretty.register_uri(
            httpretty.POST, self.app.config.get('VAULT_SOLR_BIGQUERY_ENDPOINT'),
            content_type='big-query/csv',
            status=200,
            body=callback)

        r = self.client.post(url_for('user.query'),
                headers={'Authorization': 'secret'},
                data=json.dumps({'q': 'foo:bar', 'fq': '{!bitset}', 'bigquery': 'one\ntwo'}),
                content_type='application/json')

        self.assertStatus(r, 200)


        self.assertTrue(r.json['qid'], 'qid is missing')
        with self.app.session_scope() as session:
            q = session.query(Query).filter_by(qid=r.json['qid']).first()
            #q = self.app.db.session.query(Query).filter_by(qid=r.json['qid']).first()

            self.assertTrue(q.qid == r.json['qid'], 'query was not saved')
            self.assertTrue(q.query == json.dumps({"query": "fq=%7B%21bitset%7D&q=foo%3Abar", "bigquery": "one\ntwo"}).encode('utf8'), 'query was not saved')
            session.expunge_all()


        # now test that the query gets executed
        r = self.client.get(url_for('user.execute_query', queryid=q.qid),
                headers={'Authorization': 'secret'},
                query_string={'fl': 'title,abstract,foo', 'fq': 'author:foo'},
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assertListEqual(r.json['responseHeader']['params']['fq'], ['author:foo', '{!bitset}'])
        self.assertListEqual(r.json['responseHeader']['params']['q'], ['foo:bar'])

        # and parameters can be overriden
        r = self.client.get(url_for('user.execute_query', queryid=q.qid),
                headers={'Authorization': 'secret'},
                query_string={'fl': 'title,abstract,foo', 'q': 'author:foo'},
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assertListEqual(r.json['responseHeader']['params']['q'], ['author:foo'])

    def test_store_data(self):
        '''Tests the ability to store data'''

        # wrong request (missing user)
        r = self.client.get(url_for('user.store_data'),
                headers={'Authorization': 'secret'},
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')

        self.assertStatus(r, 400)

        # no data
        r = self.client.get(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json == {}, 'missing empty json response')

        # try to save something broken (it has to be json)
        r = self.client.post(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                data=json.dumps({'foo': 'bar'})[0:-2],
                content_type='application/json')

        self.assertStatus(r, 400)
        self.assertTrue(r.json['msg'], 'missing explanation')

        # save something
        r = self.client.post(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json['foo'] == 'bar', 'missing echo')

        # get it back
        r = self.client.get(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json == {'foo': 'bar'}, 'missing data ({})'.format(json.dumps(r.json)))

        # save something else
        r = self.client.post(url_for('user.store_data'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                             data=json.dumps({'db': 'testdb'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json['db'] == 'testdb', 'missing echo')

        # get it back
        r = self.client.get(url_for('user.store_data'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                            content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json == {'foo': 'bar', 'db': 'testdb'}, 'missing data ({})'.format(json.dumps(r.json)))

        # modify it
        r = self.client.post(url_for('user.store_data'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                             data=json.dumps({'db': 'testdb2'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json['db'] == 'testdb2', 'missing echo')

        # get everything back
        r = self.client.get(url_for('user.store_data'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '2'},
                            content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json == {'foo': 'bar', 'db': 'testdb2'}, 'missing data ({})'.format(json.dumps(r.json)))

    def test_myads_retrieval(self):
        '''Tests pipeline retrieval of myADS setup and users'''

        now = adsmutils.get_date()

        with self.app.session_scope() as session:
            q = session.query(Query).first()

            qid = q.qid

        # make sure no setups exist
        r = self.client.get(url_for('user.myads_notifications'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'})

        self.assertStatus(r, 204)

        # try saving a query with bad data
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'},
                             data=json.dumps({'name': 'Query 1', 'qid': qid, 'stateful': True,
                                              'frequency': 'bad data', 'type': 'query'}),
                             content_type='application/json')

        self.assertStatus(r, 400)

        # save the query correctly
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'},
                             data=json.dumps({'name': 'Query 1', 'qid': qid, 'stateful': True, 'frequency': 'daily', 'type': 'query'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertTrue(r.json['name'] == 'Query 1')
        self.assertTrue(r.json['active'])
        myads_id = r.json['id']

        # edit the query with bad data
        r = self.client.put(url_for('user.myads_notifications', myads_id=myads_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'},
                            data=json.dumps({'name': 'Query 1 - edited', 'stateful': 'bad data'}),
                            content_type='application/json')

        self.assertStatus(r, 400)

        # edit the query correctly
        r = self.client.put(url_for('user.myads_notifications', myads_id=myads_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'},
                            data=json.dumps({'name': 'Query 1 - edited'}),
                            content_type='application/json')

        self.assertStatus(r, 200)
        self.assertEqual(r.json['name'], 'Query 1 - edited')

        # get all myADS setups via the pipeline endpoint
        r = self.client.get(url_for('user.get_myads', user_id='3'),
                            headers={'Authorization': 'secret'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['name'], 'Query 1 - edited')
        self.assertEqual(r.json[0]['qid'], qid)
        self.assertTrue(r.json[0]['active'])
        self.assertTrue(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['frequency'], 'daily')
        self.assertEqual(r.json[0]['type'], 'query')

        # get all myADS setups via the BBB endpoint
        r = self.client.get(url_for('user.myads_notifications'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '3'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['name'], 'Query 1 - edited')
        self.assertTrue(r.json[0]['active'])
        self.assertEqual(r.json[0]['frequency'], 'daily')
        self.assertEqual(r.json[0]['type'], 'query')

        # fetch the active myADS users
        r = self.client.get(url_for('user.export', iso_datestring=now))

        self.assertStatus(r, 200)
        self.assertEqual(r.json, {'users': [3]})

    @httpretty.activate
    def test_template_query(self):
        '''Tests storage and retrieval of templated myADS queries'''
        httpretty.register_uri(
            httpretty.GET, self.app.config.get('VAULT_SOLR_QUERY_ENDPOINT'),
            content_type='application/json',
            status=200,
            body="""{
                    "responseHeader":{
                    "status":0, "QTime":0,
                    "params":{ "fl":"title,bibcode", "indent":"true", "wt":"json", "q":"*:*"}},
                    "response":{"numFound":10456930,"start":0,"docs":[
                      { "bibcode":"2005JGRC..110.4002G" },
                      { "bibcode":"2005JGRC..110.4003N" },
                      { "bibcode":"2005JGRC..110.4004Y" }]}}""")

        now = adsmutils.get_date().date()
        beg_pubyear = (now - datetime.timedelta(days=180)).year

        with self.app.session_scope() as session:
            r = session.query(User).filter_by(id=4).first()
            self.assertIsNone(r, True)

        # try to store a query with insufficient metadata
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'data': 'keyword1 OR keyword2'}),
                             content_type='application/json')

        self.assertStatus(r, 400)

        # try to store a query with data keyword of the wrong type (also insufficient metadata)
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'data': 123}),
                             content_type='application/json')

        self.assertStatus(r, 400)

        # try to store a query with the classes keyword of the wrong type
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template', 'template': 'arxiv', 'classes': 'astro-ph', 'data': 'keyword1 OR keyword2'}),
                             content_type='application/json')

        self.assertStatus(r, 400)

        # store a query correctly
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template', 'template': 'keyword', 'data': 'keyword1 OR keyword2'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        # test that the pipeline export works as expected
        r = self.client.get(url_for('user.get_myads', user_id='4'),
                            headers={'Authorization': 'secret'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'keyword1, etc.')
        self.assertTrue(r.json[0]['active'])
        self.assertFalse(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['frequency'], 'weekly')
        self.assertEqual(r.json[0]['type'], 'template')
        self.assertEqual(r.json[0]['template'], 'keyword')
        self.assertEqual(r.json[0]['data'], 'keyword1 OR keyword2')

        # try to retrieve a query without a user ID in the headers
        r = self.client.get(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret'})

        self.assertStatus(r, 400)

        # successfully retrieve a query setup
        r = self.client.get(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'keyword1, etc.')
        self.assertTrue(r.json[0]['active'])
        self.assertFalse(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['frequency'], 'weekly')
        self.assertEqual(r.json[0]['type'], 'template')

        # successfully delete the query setup
        r = self.client.delete(url_for('user.myads_notifications', myads_id=query_id),
                               headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 204)

        # ensure the query is really deleted
        with self.app.session_scope() as session:
            q = session.query(MyADS).filter_by(id=query_id).first()
            self.assertIsNone(q)

        # ensure the get returns the right status for a missing query
        r = self.client.get(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 404)

        # save an arxiv template query successfully
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'arxiv',
                                              'data': 'keyword1 OR keyword2',
                                              'classes': ['astro-ph']}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        # check the stored query via the pipeline export
        r = self.client.get(url_for('user.get_myads', user_id='4'),
                            headers={'Authorization': 'secret'})

        if adsmutils.get_date().weekday() == 0:
            start_date = (adsmutils.get_date() - datetime.timedelta(days=2)).date()
        else:
            start_date = adsmutils.get_date().date()

        end_date = adsmutils.get_date().date()

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'keyword1, etc. - Recent Papers')
        self.assertFalse(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['type'], 'template')
        self.assertTrue(r.json[0]['active'])
        self.assertEqual(r.json[0]['frequency'], 'daily')
        self.assertEqual(r.json[0]['template'], 'arxiv')
        self.assertEqual(r.json[0]['data'], 'keyword1 OR keyword2')
        self.assertEqual(r.json[0]['classes'], ['astro-ph'])
        self.assertTrue('entdate:["{0}Z00:00" TO "{1}Z23:59"]'.format(start_date, end_date) in r.json[0]['query'][0]['q'])

        # check the stored query via the pipeline export using the start date option
        # this should use the original start date, since the passed date is later
        start_iso = (adsmutils.get_date() + datetime.timedelta(days=5)).isoformat()
        r = self.client.get(url_for('user.get_myads', user_id='4', start_isodate=start_iso),
                            headers={'Authorization': 'secret'})

        self.assertTrue('entdate:["{0}Z00:00" TO "{1}Z23:59"]'.format(start_date, end_date) in r.json[0]['query'][0]['q'])

        # this should use the passed date, since it's before the default start date
        start_iso = (adsmutils.get_date() - datetime.timedelta(days=15)).isoformat()
        r = self.client.get(url_for('user.get_myads', user_id='4', start_isodate=start_iso),
                            headers={'Authorization': 'secret'})

        start_iso_date = parser.parse(start_iso).date()
        self.assertTrue(
            'entdate:["{0}Z00:00" TO "{1}Z23:59"]'.format(start_iso_date, end_date) in r.json[0]['query'][0]['q'])

        # edit the stored query
        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'data': 'keyword1 OR keyword2 OR keyword3',
                                             'classes': ['astro-ph']}),
                            content_type='application/json')

        self.assertStatus(r, 200)

        # check editing the query name
        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'name': 'keyword1, etc. - Recent Papers',
                                             'data': 'keyword2 OR keyword3',
                                             'classes': ['astro-ph']}),
                            content_type='application/json')

        self.assertStatus(r, 200)
        # name was provided, but it was constructed, so the name should be updated
        self.assertEqual(r.json['name'], 'keyword2, etc. - Recent Papers')

        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'name': 'test query',
                                             'data': 'keyword2 OR keyword3',
                                             'classes': ['astro-ph']}),
                            content_type='application/json')

        self.assertStatus(r, 200)
        # a non-constructed name was provided - use that
        self.assertEqual(r.json['name'], 'test query')

        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'data': 'keyword1 OR keyword2 OR keyword3',
                                             'classes': ['astro-ph']}),
                            content_type='application/json')

        self.assertStatus(r, 200)
        # no name is provided, so keep the old provided name
        self.assertEqual(r.json['name'], 'test query')

        # check the exported setup
        r = self.client.get(url_for('user.get_myads', user_id='4'),
                            headers={'Authorization': 'secret'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'test query')
        self.assertFalse(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['type'], 'template')
        self.assertTrue(r.json[0]['active'])
        self.assertEqual(r.json[0]['frequency'], 'daily')
        self.assertEqual(r.json[0]['template'], 'arxiv')
        self.assertEqual(r.json[0]['data'], 'keyword1 OR keyword2 OR keyword3')
        self.assertEqual(r.json[0]['classes'], ['astro-ph'])

        # add a second query
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'authors',
                                              'data': 'author:"Kurtz, M."'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertEqual(r.json['name'], 'Favorite Authors - Recent Papers')

        # get all queries back
        r = self.client.get(url_for('user.myads_notifications'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['name'], 'test query')
        self.assertEqual(r.json[1]['name'], 'Favorite Authors - Recent Papers')

        # save an arXiv query without keywords
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'arxiv',
                                              'classes': ['cs']}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertEqual(r.json['data'], None)

        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'data': '',
                                              'template': 'arxiv',
                                              'classes': ['hep-ex']}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assertEqual(r.json['data'], None)

        # test a blank arXiv query
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'arxiv',
                                              'classes': ['astro-ph']}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        # make sure it's editable
        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'active': False}),
                            content_type='application/json')

        self.assertStatus(r, 200)

        r = self.client.put(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                            data=json.dumps({'type': 'template',
                                             'template': 'arxiv',
                                             'data': 'keyword1',
                                             'classes': ['astro-ph']}),
                            content_type='application/json')

        self.assertStatus(r, 200)

        # test the citation query construction
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'citations',
                                              'data': 'author:"Kurtz, Michael"'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        r = self.client.get(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'author:"Kurtz, Michael" - Citations')
        self.assertTrue(r.json[0]['active'])
        self.assertTrue(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['frequency'], 'weekly')
        self.assertEqual(r.json[0]['type'], 'template')

        r = self.client.get(url_for('user.get_myads', user_id=4),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertTrue(r.json[4]['query'][0]['q'] == 'citations(author:"Kurtz, Michael")')

        # a passed start date shouldn't matter to citations queries
        r2 = self.client.get(url_for('user.get_myads', user_id=4, start_isodate=start_iso_date),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertTrue(r2.json[4]['query'][0]['q'] == r.json[4]['query'][0]['q'])

        # test the author query construction
        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'},
                             data=json.dumps({'type': 'template',
                                              'template': 'authors',
                                              'data': 'author:"Kurtz, Michael"'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        r = self.client.get(url_for('user.myads_notifications', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        self.assertStatus(r, 200)
        self.assertEqual(r.json[0]['id'], query_id)
        self.assertEqual(r.json[0]['name'], 'Favorite Authors - Recent Papers')
        self.assertTrue(r.json[0]['active'])
        self.assertTrue(r.json[0]['stateful'])
        self.assertEqual(r.json[0]['frequency'], 'weekly')
        self.assertEqual(r.json[0]['type'], 'template')

        # check start dates in constructed query - no start date should default to now - the weekly time range
        r = self.client.get(url_for('user.get_myads', user_id=4),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        start_date = (adsmutils.get_date() - datetime.timedelta(days=self.app.config.get('MYADS_WEEKLY_TIME_RANGE'))).date()
        self.assertTrue('author:"Kurtz, Michael" entdate:["{0}Z00:00" TO "{1}Z23:59"]'.format(start_date, end_date)
                        in r.json[5]['query'][0]['q'])

        # passing an earlier start date should respect that date
        start_iso = (adsmutils.get_date() - datetime.timedelta(days=40)).isoformat()
        r = self.client.get(url_for('user.get_myads', user_id=4, start_isodate=start_iso),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '4'})

        start_iso_date = parser.parse(start_iso).date()
        self.assertTrue('author:"Kurtz, Michael" entdate:["{0}Z00:00" TO "{1}Z23:59"]'.format(start_iso_date, end_date)
                        in r.json[5]['query'][0]['q'])

    @httpretty.activate
    def test_non_ascii_myads(self):

        httpretty.register_uri(
            httpretty.GET, self.app.config.get('VAULT_SOLR_QUERY_ENDPOINT'),
            content_type='application/json',
            status=200,
            body="""{
                            "responseHeader":{
                            "status":0, "QTime":0,
                            "params":{ "fl":"title,bibcode", "indent":"true", "wt":"json", "q":"*:*"}},
                            "response":{"numFound":10456930,"start":0,"docs":[
                              { "bibcode":"2005JGRC..110.4002G" },
                              { "bibcode":"2005JGRC..110.4003N" },
                              { "bibcode":"2005JGRC..110.4004Y" }]}}""")

        r = self.client.post(url_for('user.query'),
                             headers={'Authorization': 'secret'},
                             data=json.dumps({'q': b'author:"Galindo-Guil, Francisco Jos\xc3\xa9"'.decode('utf8')}),
                             content_type='application/json')
        with self.app.session_scope() as session:
            q = session.query(Query).filter_by(qid=r.json['qid']).first()

            self.assertStatus(r, 200)

        self.assertTrue(r.json['qid'], 'qid is missing')
        qid = r.json['qid']

        # some test data is unicode, some utf-8 because we use utf-8 encoding by default in bumblebee
        test_data = [{'type': 'template', 'template': 'keyword', 'data': 'author:"Galindo-Guil, Francisco Jos\xe9"'},
                     {'type': 'template', 'template': 'authors', 'data': b'author:"Galindo-Guil, Francisco Jos\xc3\xa9"'.decode('utf8')},
                     {'type': 'template', 'template': 'citations', 'data': b'author:"Galindo-Guil, Francisco Jos\xc3\xa9"'.decode('utf8')},
                     {'type': 'template', 'template': 'arxiv', 'data': 'author:"Galindo-Guil, Francisco José"', 'classes': ['astro-ph']},
                     {'type': 'query', 'name': 'Query 1', 'qid': qid, 'stateful': True, 'frequency': 'daily'}
                     ]

        for t in test_data:
            q = self.client.post(url_for('user.myads_notifications'),
                                 headers={'Authorization': 'secret', 'X-Adsws-Uid': '101'},
                                 data=json.dumps(t),
                                 content_type='application/json')

            self.assertStatus(q, 200)

            s = self.client.get(url_for('user.execute_myads_query', myads_id=q.json['id']),
                                headers={'Authorization': 'secret', 'X-Adsws-Uid': '101'})

            self.assertStatus(s, 200)
            self.assertIn(b'Galindo-Guil, Francisco Jos\xc3\xa9'.decode('utf8'), s.json[0]['q'])

    @httpretty.activate
    def test_myads_execute_notification(self):

        httpretty.register_uri(
            httpretty.GET, self.app.config.get('VAULT_SOLR_QUERY_ENDPOINT'),
            content_type='application/json',
            status=200,
            body="""{
                            "responseHeader":{
                            "status":0, "QTime":0,
                            "params":{ "fl":"title,bibcode", "indent":"true", "wt":"json", "q":"*:*"}},
                            "response":{"numFound":10456930,"start":0,"docs":[
                              { "bibcode":"2005JGRC..110.4002G" },
                              { "bibcode":"2005JGRC..110.4003N" },
                              { "bibcode":"2005JGRC..110.4004Y" }]}}""")

        now = adsmutils.get_date().date()
        beg_pubyear = (now - datetime.timedelta(days=180)).year

        # can't use as anonymous user
        user_id = self.app.config.get('BOOTSTRAP_USER_ID')
        r = self.client.get(url_for('user.execute_myads_query', myads_id=123),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id})

        self.assertStatus(r, 400)

        user_id = 6

        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id},
                             data=json.dumps({'type': 'template',
                                              'template': 'authors',
                                              'data': 'author:"Kurtz, Michael"'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        query_id = r.json['id']

        r = self.client.get(url_for('user.execute_myads_query', myads_id=query_id),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id})

        start_date = (adsmutils.get_date() - datetime.timedelta(days=self.app.config.get('MYADS_WEEKLY_TIME_RANGE'))).date()

        self.assertStatus(r, 200)
        self.assertEqual(r.json, [{'q': 'author:"Kurtz, Michael" entdate:["{0}Z00:00" TO "{1}Z23:59"] '
                                            'pubdate:[{2}-00 TO *]'.format(start_date, now, beg_pubyear),
                                       'sort': 'score desc, bibcode desc'}])

    @httpretty.activate
    def test_myads_import(self):
        # can't use as anonymous user
        user_id = self.app.config.get('BOOTSTRAP_USER_ID')
        r = self.client.get(url_for('user.import_myads'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id})

        self.assertStatus(r, 400)

        user_id = 5

        httpretty.register_uri(
            httpretty.GET,
            self.app.config.get('HARBOUR_MYADS_IMPORT_ENDPOINT') % user_id,
            content_type='application/json',
            status=200,
            body="""{"id": 123456, "firstname": "Michael", "lastname": "Kurtz"}"""
        )

        r = self.client.get(url_for('user.import_myads'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id})

        self.assertStatus(r, 200)
        self.assertEqual(len(r.json['new']), 1)
        self.assertEqual(len(r.json['existing']), 0)

if __name__ == '__main__':
    unittest.main()
