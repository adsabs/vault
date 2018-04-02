import sys, os
from urllib import urlencode

project_home = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from flask import url_for, request
import unittest
import json
import httpretty
import cgi
from StringIO import StringIO
from vault_service.tests.base import TestCaseDatabase

class TestServices(TestCaseDatabase):
    '''Tests that each route is an http response'''

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
