import sys, os
from urllib import urlencode
from flask.ext.testing import TestCase
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from myads_service import app            
from myads_service.models import db, Query

class TestServices(TestCase):
    '''Tests that each route is an http response'''
    
    def create_app(self):
        '''Start the wsgi application'''
        a = app.create_app(**{
               'SQLALCHEMY_DATABASE_URI': 'sqlite://',
               'SQLALCHEMY_ECHO': False,
               #'DEBUG': True,
               'TESTING': True,
               'PROPAGATE_EXCEPTIONS': True,
               #'PRESERVE_CONTEXT_ON_EXCEPTION': True,
               'TRAP_BAD_REQUEST_ERRORS': True
            })
        db.create_all(app=a)
        return a


    @httpretty.activate
    def test_query_storage(self):
        '''Tests the ability to store queries'''
        
        httpretty.register_uri(
            httpretty.POST, self.app.config.get('SOLR_QUERY_ENDPOINT'),
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

        r = self.client.post(url_for('storage.query'),
                headers={'Authorization': 'secret'},
                data=json.dumps({'q': 'foo:bar'}),
                content_type='application/json')
        
        self.assertStatus(r, 200)
        
        
        self.assert_(r.json['qid'], 'qid is missing')
        q = db.session.query(Query).filter_by(qid=r.json['qid']).first()
        
        self.assert_(q.qid == r.json['qid'], 'query was not saved')
        self.assert_(q.query == json.dumps({"query": "q=foo%3Abar", "bigquery": ""}, 'query was not saved'))
        
        
        # now test that the query gets executed
        #self.app.debug = True
        r = self.client.get(url_for('storage.execute_query', queryid=q.qid),
                headers={'Authorization': 'secret'},
                data=json.dumps({'fl': 'title,abstract'}),
                content_type='application/json')
        
        self.assertStatus(r, 200)
        
    @httpretty.activate
    def test_bigquery_storage(self):
        '''Tests the ability to store bigqueries'''
        
        httpretty.register_uri(
            httpretty.POST, self.app.config.get('SOLR_BIGQUERY_ENDPOINT'),
            content_type='big-query/csv',
            status=200,
            body="""{
            "responseHeader":{
            "status":0, "QTime":0,
            "params":{ "fl":"title,bibcode", "indent":"true", "wt":"json", "q":"*:*"}},
            "response":{"numFound":10456930,"start":0,"docs":[
              { "bibcode":"2005JGRC..110.4002G" },
              { "bibcode":"2005JGRC..110.4003N" },
              { "bibcode":"2005JGRC..110.4004Y" }]}}""")

        r = self.client.post(url_for('storage.query'),
                headers={'Authorization': 'secret'},
                data=json.dumps({'q': 'foo:bar', 'fq': '{!bitset}', 'bigquery': 'one\ntwo'}),
                content_type='application/json')
        
        self.assertStatus(r, 200)
        
        
        self.assert_(r.json['qid'], 'qid is missing')
        q = db.session.query(Query).filter_by(qid=r.json['qid']).first()
        
        self.assert_(q.qid == r.json['qid'], 'query was not saved')
        self.assert_(q.query == json.dumps({"query": "fq=%7B%21bitset%7D&q=foo%3Abar", "bigquery": "one\ntwo"}, 'query was not saved'))
        
        
        # now test that the query gets executed
        #self.app.debug = True
        r = self.client.get(url_for('storage.execute_query', queryid=q.qid),
                headers={'Authorization': 'secret'},
                data=json.dumps({'fl': 'title,abstract'}),
                content_type='application/json')
        
        self.assertStatus(r, 200)
        
    
    def test_query_utils(self):
        from myads_service import utils
        
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
        
if __name__ == '__main__':
    unittest.main()
