from werkzeug.serving import run_simple
import os, sys
from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager

# for running things in wsgi container; use
# wsgi.py from the rootdir

def create_app():
    
    opath = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if opath not in sys.path:
        sys.path.insert(0, opath)
    
    app = Flask(__name__, static_folder=None)
    app.url_map.strict_slashes = False
    app.config.from_pyfile('config.py')
    try:
      app.config.from_pyfile('local_config.py')
    except IOError:
      pass
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    db = SQLAlchemy(app)
    
    ## pysqlite driver breaks transactions, we have to apply some hacks as per
    ## http://docs.sqlalchemy.org/en/rel_0_9/dialects/sqlite.html#pysqlite-serializable
    if 'sqlite:' in app.config.get('SQLALCHEMY_DATABASE_URI'):
        from sqlalchemy import event
        engine = db.get_engine(app)
        
        @event.listens_for(engine, "connect")
        def do_connect(dbapi_connection, connection_record):
            # disable pysqlite's emitting of the BEGIN statement entirely.
            # also stops it from emitting COMMIT before any DDL.
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def do_begin(conn):
            # emit our own BEGIN
            conn.execute("BEGIN EXCLUSIVE")
    
    @login_manager.request_loader
    def load_user_from_request(request):
    
        user = None
        
        # try to login using User header
        user_key = request.headers.get('User') or 'Anonymous'
        if user_key:
            user = User.query.filter_by(key=user_key).first()
            if user:
                return user
            else:
                # create a new user
                return User(key=user_key)
    
        # finally, return Anonymous
        return None
    
    from myads_service import views
    for blueprint in views.blueprints:
        app.register_blueprint(blueprint)
        
    return app

if __name__ == '__main__':
    run_simple('0.0.0.0', 5000, create_app(), use_reloader=False, use_debugger=False)