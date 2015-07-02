import sys, os
from urllib import urlencode
from flask.ext.testing import TestCase
from flask import url_for, request
import unittest
import json

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from myads_service import app            
from myads_service.models import db, Query

class TestSite(TestCase):
    '''Tests that each route is an http response'''
    
    def create_app(self):
        '''Start the wsgi application'''
        a = app.create_app(**{
               'SQLALCHEMY_BINDS': {'myads': 'sqlite:///'},
               'SQLALCHEMY_ECHO': True,
               'TESTING': True,
               'PROPAGATE_EXCEPTIONS': True,
               'TRAP_BAD_REQUEST_ERRORS': True,
               'MYADS_BUMBLEBEE_OPTIONS': {'foo': 'bar'}
            })
        db.create_all(app=a, bind=['myads'])
        return a


    def test_store_data(self):
        '''Tests the ability to query site config'''
        
        r = self.client.get(url_for('bumblebee.configuration'),
                content_type='application/json')
        self.assertStatus(r, 200)
        self.assert_(r.json == {'foo': 'bar'}, 'missing json response')
        
        r = self.client.get(url_for('bumblebee.configuration') + '/foo',
                content_type='application/json')
        self.assertStatus(r, 200)
        self.assert_(r.json == 'bar', 'missing json response')
        
        r = self.client.get(url_for('bumblebee.configuration') + '/foox',
                content_type='application/json')
        self.assertStatus(r, 404)
        
        
if __name__ == '__main__':
    unittest.main()
