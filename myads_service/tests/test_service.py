import sys, os
from urllib import urlencode
from flask.ext.testing import TestCase
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO

class TestServices(TestCase):
    '''Tests that each route is an http response'''

    def create_app(self):
        '''Start the wsgi application'''
        project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
        if project_home not in sys.path:
            sys.path.insert(0, project_home)
        from myads_service import app
        return app.create_app()


    def xtest_stored_query(self):
        '''Posts the bigquery to the solr microservice'''
        pass
    
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
                data=json.dumps({'foo': 'bar'}),
                content_type='application/json')
        
        self.assertStatus(r, 200)
        
        from myads_service.models import db, Query
        self.assert_(r.json['qid'], 'qid is missing')
        q = db.session.query(Query).filter_by(qid=r.json['qid']).first()
        
        self.assert_(q.qid == r.json['qid'], 'query was not saved')
        self.assert_(q.query == json.dumps({'foo': 'bar'}, 'query was not saved'))
        
        
if __name__ == '__main__':
    unittest.main()
