import sys, os
from urllib import urlencode
from flask_testing import TestCase
from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from vault_service import app
from vault_service.models import Query, Base

class TestServices(TestCase):
    '''Tests that each route is an http response'''

    def create_app(self):
        '''Start the wsgi application'''
        a = app.create_app(**{
               'SQLALCHEMY_DATABASE_URI': 'sqlite:///',
               'SQLALCHEMY_ECHO': False,
               'TESTING': True,
               'PROPAGATE_EXCEPTIONS': True,
               'TRAP_BAD_REQUEST_ERRORS': True
            })
        Base.query = a.db.session.query_property()
        Base.metadata.create_all(bind=a.db.engine)
        return a

    def setUp(self):
        self.app.db.create_all()


    def tearDown(self):
        self.app.db.session.remove()
        self.app.db.drop_all()


    def test_query_as_monument(self):
        '''Tests the ability to return queries as images'''

        # create a query
        q = Query(qid='ABCD', query=json.dumps({'query': 'q=foo', 'bigquery': ''}), numfound=789543)
        self.app.db.session.add(q)
        self.app.db.session.commit()

        r = self.client.get(url_for('queryalls.query2svg', queryid='ABCD'),
                headers={'Authorization': 'secret'})

        self.assert_('789543' in r.data, 'Image was not generated properly');
        self.assert_('<svg xmlns="http://www.w3.org/2000/svg" width="99" height="20">' in r.data, 'Image was not generated properly');
        self.assertStatus(r, 200)
        self.assert_(r.headers.get('Content-Type') == 'image/svg+xml')


        r = self.client.get(url_for('queryalls.query2svg', queryid='foo'),
                headers={'Authorization': 'secret'})
        self.assertStatus(r, 404)
        self.assert_(r.headers.get('Content-Type') == 'image/svg+xml')

if __name__ == '__main__':
    unittest.main()
