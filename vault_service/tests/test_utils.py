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

from vault_service.models import Query, User, MyADS
from vault_service.views import utils
from vault_service.tests.base import TestCaseDatabase
import adsmutils


class TestServices(TestCaseDatabase):
    '''Tests that each route is an http response'''

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

    def test_upsert_myads(self):
        user_id = 5
        classic_setup = {"ast_aut,": "Lockwood, G.",
                         "ast_t1,": "photosphere\r\nchromosphere\r\n",
                         "ast_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
                         "email": "gwl@lowell.edi",
                         "firstname": "",
                         "groups": [
                            "astro-ph"
                         ],
                         "id": 2060288,
                         "lastname": "",
                         "phy_aut,": "Lockwood, G.",
                         "phy_t1,": "photosphere\r\nchromosphere\r\n",
                         "phy_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
                         "pre_aut,": "Lockwood, G.",
                         "pre_t1,": "photosphere\r\nchromosphere\r\n",
                         "pre_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\""
                         }

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        with self.app.session_scope() as session:
            q = session.query(MyADS).filter_by(user_id=user_id).all()
            self.assertEquals(len(q), 10)
        self.assertEquals(len(existing_setups), 0)
        self.assertEquals(len(new_setups), 10)
        self.assertEquals(new_setups[6], {'id': 7,
                                          'template': 'keyword',
                                          'name': u'photosphere, etc. (arXiv e-prints collection)',
                                          'frequency': 'weekly'})

        user_id = 6
        classic_setup = {"ast_t1,": "+accretion disks X-ray binaries \"ultra compact\" reflection monte carlo UCXB IMBH",
                         "daily_t1,": "X-ray binaries accretion disk reflection AGN spectroscopy IMBH ULX ultraluminous pulsar M-sigma",
                         "email": "fkoliopanos@irap.omp.eu",
                         "firstname": "Filippos",
                         "groups": [
                            "astro-ph"
                         ],
                         "id": 1085441,
                         "lastname": "Koliopanos"
                         }

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        with self.app.session_scope() as session:
            q = session.query(MyADS).filter_by(user_id=user_id).all()
            self.assertEquals(len(q), 3)

        self.assertEquals(len(existing_setups), 0)
        self.assertEquals(len(new_setups), 3)
        self.assertEquals(new_setups[2], {'id': 13,
                                          'template': 'keyword',
                                          'name': u'accretion, etc. (astronomy collection)',
                                          'frequency': 'weekly'})

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        self.assertEquals(len(existing_setups), 3)
        self.assertEquals(len(new_setups), 0)

    def test_keyword_query_name(self):
        for (test, expected) in [('one', 'one'),
                                 ('"one"', '"one"'),
                                 ('(one or two)', 'one, etc.'),
                                 ('one or two', 'one, etc.'),
                                 ('((foo and bar) or baz)', 'foo, etc.'),
                                 ('+EUV coronal waves', 'EUV, etc.'),
                                 ('\"shell galaxies\" OR \"shell galaxy\"', '"shell galaxies", etc.')]:

            name = utils.get_keyword_query_name(test)

            self.assertEquals(name, expected)

