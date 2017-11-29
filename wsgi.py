from werkzeug.serving import run_simple
from vault_service import app

application = app.create_app()

if __name__ == "__main__":
    run_simple('0.0.0.0', 5000, application, use_reloader=False, use_debugger=False)
