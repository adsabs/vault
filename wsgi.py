from werkzeug.serving import run_simple
from myads_service import app
from myads_service.models import db

application = app.create_app()

@application.teardown_request
def shutdown_session(exception=None):
     db.session.remove()

if __name__ == "__main__":
    run_simple('0.0.0.0', 5000, application, use_reloader=False, use_debugger=False)
