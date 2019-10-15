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

    # def test_upsert_myads(self):
    #     user_id = 5
    #     classic_setup = {"ast_aut,": "Lockwood, G.",
    #                      "ast_t1,": "photosphere\r\nchromosphere\r\n",
    #                      "ast_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
    #                      "email": "gwl@lowell.edi",
    #                      "firstname": "",
    #                      "groups": [
    #                         "astro-ph"
    #                      ],
    #                      "id": 2060288,
    #                      "lastname": "",
    #                      "phy_aut,": "Lockwood, G.",
    #                      "phy_t1,": "photosphere\r\nchromosphere\r\n",
    #                      "phy_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\"",
    #                      "pre_aut,": "Lockwood, G.",
    #                      "pre_t1,": "photosphere\r\nchromosphere\r\n",
    #                      "pre_t2,": "\"climate change\"\r\n\"global warming\"\r\n\"solar variation\""
    #                      }
    #
    #     utils.upsert_myads(classic_setups=classic_setup, user_id=user_id)
    #
    #     with self.app.session_scope() as session:
    #         q = session.query(MyADS).filter_by(user_id=user_id).all()
    #         import pdb
    #         pdb.set_trace()
    #
    #     self.assertEquals(user_id,5)

    # def test_parse_classic_keywords(self):
    #     test_input = "LISA \"gravitational wave\" AND \"gravity wave\""
    #
    #     tree = utils.parse_classic_keywords(test_input)
    #
    #     import pdb
    #     pdb.set_trace()
    #
    #     test_input = "+supernova -remnant -CBET"

    def test_parse(self):
        for (test, expected) in [('one two', ''),
                                 # ('one or two', ''),
                                 # ('one not three', ''),
                                 # ('(one)', ''),
                                 # ('(one two)', ''),
                                 # ('((one two))', ''),
                                 # ('(((one two)))', ''),
                                 # ('(one (two three))', ''),
                                 # ('(one (two or three))', ''),
                                 # ('(one (two or three and four))', ''),
                                 ('((foo and bar) or (baz) or a or b or c)', ''),
                                 ('LISA +\"gravitational wave\" AND \"gravity wave\"', ''),
                                 (
                                 "\"lattice green's function\",\"kepler's equation\",\"lattice green function\",\"kepler equation\",\"loop quantum gravity\",\"loop quantum cosmology\",\"random walk\",EJTP",
                                 ''),
                                 (
                                 "+EUV coronal waves \r\n +Dimmings\r\nDimming Mass Evacuation\r\n+Eruption prominence",
                                 ''),
                                 (
                                 '\"shell galaxies\" OR \"shell galaxy\" OR ((ripple OR ripples OR shells OR (tidal AND structure) OR (tidal AND structures) OR (tidal AND feature) OR (tidal AND features)) AND (galaxy OR galaxies))',
                                 ''),
                                 ]:
            print 'query:', test
            tree = utils.parse_classic_keywords(test)

            # self.assertEquals(output, expected)

            print tree.pretty(' ')

            v = utils.TreeVisitor()
            import pdb
            pdb.set_trace()
            print 'new query: ', v.visit(tree).output
