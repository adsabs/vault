import sys, os
from urllib import urlencode
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from vault_service.models import Query
from vault_service.views import utils
from vault_service.tests.base import TestCaseDatabase

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


        self.assert_(r.json['qid'], 'qid is missing')
        with self.app.session_scope() as session:
            q = session.query(Query).filter_by(qid=r.json['qid']).first()

            self.assert_(q.qid == r.json['qid'], 'query was not saved')
            self.assert_(q.query == json.dumps({"query": "q=foo%3Abar", "bigquery": ""}, 'query was not saved'))
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


        self.assert_(r.json['qid'], 'qid is missing')
        with self.app.session_scope() as session:
            q = session.query(Query).filter_by(qid=r.json['qid']).first()
            #q = self.app.db.session.query(Query).filter_by(qid=r.json['qid']).first()

            self.assert_(q.qid == r.json['qid'], 'query was not saved')
            self.assert_(q.query == json.dumps({"query": "fq=%7B%21bitset%7D&q=foo%3Abar", "bigquery": "one\ntwo"}, 'query was not saved'))
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


    def test_query_utils(self):

        r = utils.cleanup_payload({'query': 'q=foo&fq=boo&foo=bar&boo=bar'})
        self.assert_(r == {'query': 'fq=boo&q=foo', 'bigquery': ""}, 'wrong output')

        r = utils.cleanup_payload({'query': {'q': 'foo', 'fq': 'boo', 'foo': 'bar', 'boo': 'bar'}})
        self.assert_(r == {'query': 'fq=boo&q=foo', 'bigquery': ""}, 'wrong output')

        def test_exc():
            utils.cleanup_payload({'query': {'q': 'foo', 'fq': 'boo', 'foo': 'bar', 'boo': 'bar'},
                                   'bigquery': 'foo\nbar'})

        self.assertRaises(Exception, test_exc)

        r = utils.cleanup_payload({'query': {'q': 'foo', 'fq': '{!bitset}', 'foo': 'bar', 'boo': 'bar'},
                                   'bigquery': 'foo\nbar'})
        self.assert_(r == {'query': 'fq=%7B%21bitset%7D&q=foo', 'bigquery': 'foo\nbar'})


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
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json == {}, 'missing empty json response')

        # try to save something broken (it has to be json)
        r = self.client.post(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                data=json.dumps({'foo': 'bar'})[0:-2],
                content_type='application/json')

        self.assertStatus(r, 400)
        self.assert_(r.json['msg'], 'missing explanation')

        # save something
        r = self.client.post(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json['foo'] == 'bar', 'missing echo')

        # get it back
        r = self.client.get(url_for('user.store_data'),
                headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json == {'foo': 'bar'}, 'missing data')

        # save something else
        r = self.client.post(url_for('user.store_data'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                             data=json.dumps({'db': 'testdb'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json['db'] == 'testdb', 'missing echo')

        # get it back
        r = self.client.get(url_for('user.store_data'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                            content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json == {'foo': 'bar', 'db': 'testdb'}, 'missing data')

        # modify it
        r = self.client.post(url_for('user.store_data'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                             data=json.dumps({'db': 'testdb2'}),
                             content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json['db'] == 'testdb2', 'missing echo')

        # get everything back
        r = self.client.get(url_for('user.store_data'),
                            headers={'Authorization': 'secret', 'X-Adsws-Uid': '1'},
                            content_type='application/json')

        self.assertStatus(r, 200)
        self.assert_(r.json == {'foo': 'bar', 'db': 'testdb2'}, 'missing data')


if __name__ == '__main__':
    unittest.main()
