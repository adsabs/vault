import argparse
import json
import os
import sys
import psycopg2
from itertools import islice
from sqlalchemy.orm import exc as ormexc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flask import current_app
from flask.ext.script import Manager, Command, Option
from adsmutils import setup_logging, load_config, ADSFlask
from vault_service.views.utils import upsert_myads
from vault_service import app
from vault_service.models import MyADS

app_ = app.create_app()
manager = Manager(app_)


@manager.option('-f', '--file', dest='filename', default=None)
@manager.option('-i', '--import', dest='do_import', default=False)
@manager.option('-e', '--email', dest='email_address', default=None)
@manager.option('-r', '--force', dest='force', default=False)
@manager.option('-v', '--verbose', dest='verbose', default=False)
@manager.option('-t', '--testing', dest='testing', default=False)
def import_from_classic(filename=None, do_import=False, email_address=None, force=False, verbose=False, testing=False):
    with open(filename) as json_file:
        data = json.load(json_file)

    if email_address:
        try:
            data = {email_address: data[email_address]}
        except KeyError:
            current_app.logger.warning('Supplied email address does not have a Classic myADS setup')
            return

    if testing:
        data = dict(islice(data.iteritems(), 10))

    matched_user = 0
    unmatched_user = 0
    existing_user = 0
    if do_import:
        upsert_success = 0
        upsert_failure = 0
    for k, v in data.items():
        force = force
        user_id = None
        r = current_app.client.get(current_app.config['USER_EMAIL_ADSWS_API_URL'] % k,
                                   headers={'Authorization': 'Bearer {0}'.format(current_app.config['VAULT_OAUTH_CLIENT_TOKEN'])})
        if r.status_code == 200:
            user_id = r.json()['id']
        # if not, check if k exists in harbour (and get user_id)
        if not user_id:
            try:
                conn = psycopg2.connect(host=current_app.config['POSTGRES_HARBOUR']['host'],
                                        database=current_app.config['POSTGRES_HARBOUR']['database'],
                                        port=current_app.config['POSTGRES_HARBOUR']['port'],
                                        user=current_app.config['POSTGRES_HARBOUR']['user'],
                                        password=current_app.config['POSTGRES_HARBOUR']['password'])
                cur = conn.cursor()
                cur.execute('select absolute_uid from users where classic_email=%s', (k,))
                row = cur.fetchone()
                user_id = row[0]
                cur.close()
            except (Exception, psycopg2.DatabaseError) as error:
                if verbose:
                    current_app.logger.info('Database error: {0}'.format(error))
            finally:
                if conn is not None:
                    conn.close()

        if user_id:
            matched_user += 1
            if do_import:
                with current_app.session_scope() as session:
                    try:
                        q = session.query(MyADS).filter_by(user_id=user_id).one()
                        existing_user += 1
                    except ormexc.NoResultFound:
                        force = True
                if force:
                    try:
                        existing_setups, new_setups = upsert_myads(v, user_id)
                        upsert_success += 1
                    except:
                        current_app.logger.info('Upsert for user {0} failed'.format(k))
                        upsert_failure += 1
        else:
            if verbose:
                current_app.logger.info('No user ID found for email {0}'.format(k))
            unmatched_user += 1

    if email_address:
        msg = 'Email address {0} was '.format(email_address)
        if matched_user > 0:
            msg += 'successfully found.'
        else:
            msg += 'not successfully found.'
    else:
        msg = 'User IDs for {0} users were successfully ({1} unsuccessfully) found.'.\
            format(matched_user, unmatched_user)

    if do_import:
        msg += ' There were {0} upsert successes ({1} failures) for the found user IDs.'.\
            format(upsert_success, upsert_failure)

        current_app.logger.info(msg)

if __name__ == '__main__':
    manager.run()
