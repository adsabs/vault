import sys, os
from urllib import urlencode
import testing.postgresql

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from flask_testing import TestCase
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO
from vault_service.models import Base

class TestServices(TestCase):
    '''Tests that each route is an http response'''

    postgresql_url_dict = {
        'port': 1234,
        'host': '127.0.0.1',
        'user': 'postgres',
        'database': 'test'
    }
    postgresql_url = 'postgresql://{user}@{host}:{port}/{database}' \
        .format(
        user=postgresql_url_dict['user'],
        host=postgresql_url_dict['host'],
        port=postgresql_url_dict['port'],
        database=postgresql_url_dict['database']
    )

    def create_app(self):
        '''Start the wsgi application'''
        from vault_service import app
        a = app.create_app(**{
               'SQLALCHEMY_DATABASE_URI': self.postgresql_url,
               'SQLALCHEMY_ECHO': False,
               'TESTING': True,
               'PROPAGATE_EXCEPTIONS': True,
               'TRAP_BAD_REQUEST_ERRORS': True
            })
        Base.query = a.db.session.query_property()
        return a

    @classmethod
    def setUpClass(cls):
        cls.postgresql = \
            testing.postgresql.Postgresql(**cls.postgresql_url_dict)

    @classmethod
    def tearDownClass(cls):
        cls.postgresql.stop()

    def setUp(self):
        Base.metadata.create_all(bind=self.app.db.engine)


    def tearDown(self):
        self.app.db.session.remove()
        self.app.db.drop_all()



    def test_ResourcesRoute(self):
        '''Tests for the existence of a /resources route, and that it returns properly formatted JSON data'''
        r = self.client.get('/resources')
        self.assertEqual(r.status_code,200)
        [self.assertIsInstance(k, basestring) for k in r.json] #Assert each key is a string-type

        for expected_field, _type in {'scopes':list,'methods':list,'description':basestring,'rate_limit':list}.iteritems():
          [self.assertIn(expected_field,v) for v in r.json.values()] #Assert each resource is described has the expected_field
          [self.assertIsInstance(v[expected_field],_type) for v in r.json.values()] #Assert every expected_field has the proper type




if __name__ == '__main__':
  unittest.main()
