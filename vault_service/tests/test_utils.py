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

    @httpretty.activate
    def test_upsert_myads(self):
        user_id = 5
        classic_setup = {"ast_aut": "Accomazzi, A.\r\nKurtz, M.",
                         "ast_t1": "photosphere\r\nchromosphere\r\n",
                         "ast_t2": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
                         "email": "gwl@lowell.edi",
                         "firstname": "",
                         "groups": [
                            "astro-ph"
                         ],
                         "id": 2060288,
                         "lastname": "",
                         "phy_aut": "Lockwood, G.\r\n",
                         "phy_t1": "photosphere\r\nchromosphere\r\n",
                         "phy_t2": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
                         "pre_aut": "Lockwood, G.",
                         "pre_t1": "photosphere\r\nchromosphere\r\n",
                         "pre_t2": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
                         "disabled": []
                         }

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        with self.app.session_scope() as session:
            q = session.query(MyADS).filter_by(user_id=user_id).all()
            self.assertEquals(len(q), 4)
            # make sure the blank author is removed
            self.assertEquals(q[1].data, 'author:"Lockwood, G." OR author:"Accomazzi, A." OR author:"Kurtz, M."')

        self.assertEquals(len(existing_setups), 0)
        self.assertEquals(len(new_setups), 4)
        self.assertEquals(new_setups[2], {'id': 3,
                                          'template': 'keyword',
                                          'name': u'photosphere, etc.',
                                          'frequency': 'weekly'})

        user_id = 6
        classic_setup = {"ast_t1": "+accretion disks X-ray binaries \"ultra compact\" reflection monte carlo UCXB IMBH",
                         "daily_t1": "X-ray binaries accretion disk reflection AGN spectroscopy IMBH ULX ultraluminous pulsar M-sigma",
                         "email": "fkoliopanos@irap.omp.eu",
                         "firstname": "Filippos",
                         "groups": [
                            "astro-ph"
                         ],
                         "id": 1085441,
                         "lastname": "Koliopanos",
                         "disabled": ["daily"]
                         }

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        with self.app.session_scope() as session:
            q = session.query(MyADS).filter_by(user_id=user_id).all()
            self.assertEquals(len(q), 3)
            self.assertTrue(q[0].active)
            self.assertFalse(q[1].active)
            self.assertTrue(q[2].active)

        self.assertEquals(len(existing_setups), 0)
        self.assertEquals(len(new_setups), 3)
        self.assertEquals(new_setups[2], {'id': 7,
                                          'template': 'keyword',
                                          'name': u'accretion, etc.',
                                          'frequency': 'weekly'})

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        self.assertEquals(len(existing_setups), 3)
        self.assertEquals(len(new_setups), 0)

        # test duplicate handling - manually adding a duplicate query shouldn't break the import
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

        r = self.client.post(url_for('user.myads_notifications'),
                             headers={'Authorization': 'secret', 'X-Adsws-Uid': user_id},
                             data=json.dumps({'type': 'template',
                                              'template': 'citations',
                                              'data': 'author:"Koliopanos, Filippos"'}),
                             content_type='application/json')

        self.assertStatus(r, 200)

        existing_setups, new_setups = utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)

        self.assertEquals(len(existing_setups), 4)
        self.assertEquals(len(new_setups), 0)

    def test_keyword_query_name(self):
        for (test, expected) in [('one', 'one'),
                                 ('"one"', '"one"'),
                                 ('', '-'),
                                 ('(())', '-'),
                                 (('a'*99)+'bccc OR star', ('a'*99)+'b, etc.'), # Extremely long term
                                 ('(one or two)', 'one, etc.'),
                                 ('(one or two or three or four or five)', 'one, etc.'),
                                 ('one or two', 'one, etc.'),
                                 ('one or two or three or four or five', 'one, etc.'),
                                 ('((foo and bar) or baz)', 'foo, etc.'),
                                 ('+EUV coronal waves', 'EUV, etc.'),
                                 ('\"shell galaxies\" OR \"shell galaxy\"', '"shell galaxies", etc.')]:

            name = utils.get_keyword_query_name(test)

            self.assertEquals(name, expected)

        name = utils.get_keyword_query_name('one', database='physics')
        self.assertEquals(name, 'one (physics collection)')

        name = utils.get_keyword_query_name('two', database='astronomy')
        self.assertEquals(name, 'two (astronomy collection)')

        name = utils.get_keyword_query_name('three', database='arxiv')
        self.assertEquals(name, 'three (arXiv e-prints collection)')

