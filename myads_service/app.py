from werkzeug.serving import run_simple
import os, sys, inspect
from flask import Flask, Blueprint
from flask.ext.discoverer import Discoverer
from flask.ext.consulate import Consul, ConsulConnectionError
from myads_service.views import bumblebee, query_as_monument, user
from myads_service.models import db

# for running things in wsgi container; use
# wsgi.py from the rootdir


def create_app(**config):
    
    opath = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if opath not in sys.path:
        sys.path.insert(0, opath)
    
    app = Flask(__name__, static_folder=None)
    app.url_map.strict_slashes = False
    
    
    app.config.from_pyfile('config.py')
    
    # Load config from Consul
    Consul(app)  # load_config expects consul to be registered
    try:
        app.extensions['consul'].apply_remote_config()
    except ConsulConnectionError as error:
        app.logger.warning('Could not apply config from consul: {}'
                           .format(error))
    
    # and finally from the local_config.py
    try:
        app.config.from_pyfile('local_config.py')
    except IOError:
        pass
  
    if config:
        app.config.update(config)
    
    db.init_app(app)
    
    ## pysqlite driver breaks transactions, we have to apply some hacks as per
    ## http://docs.sqlalchemy.org/en/rel_0_9/dialects/sqlite.html#pysqlite-serializable
    
    if 'sqlite' in (app.config.get('SQLALCHEMY_BINDS') or {'myads':''})['myads']:
        from sqlalchemy import event
        
        binds = app.config.get('SQLALCHEMY_BINDS')
        if binds and 'myads' in binds:
            engine = db.get_engine(app, bind=(app.config.get('SQLALCHEMY_BINDS') and 'myads'))
        else:
            engine = db.get_engine(app)
        
        @event.listens_for(engine, "connect")
        def do_connect(dbapi_connection, connection_record):
            # disable pysqlite's emitting of the BEGIN statement entirely.
            # also stops it from emitting COMMIT before any DDL.
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def do_begin(conn):
            # emit our own BEGIN
            conn.execute("BEGIN")

    app.register_blueprint(bumblebee.bp)
    app.register_blueprint(query_as_monument.bp)
    app.register_blueprint(user.bp)

    Discoverer(app)
    return app


if __name__ == '__main__':
    run_simple('0.0.0.0', 5000, create_app(), use_reloader=False, use_debugger=False)