VAULT_APP_SECRET_KEY = 'fake'
VAULT_OAUTH_CLIENT_TOKEN = 'to be provided'
VAULT_VERSION = 'v0.1' # Arbitrary string identifying the service (will be returned in the headers)

SQLALCHEMY_DATABASE_URI = "sqlite:///"
SQLALCHEMY_ECHO = False

# location of the remote solr-microservice
VAULT_SOLR_QUERY_ENDPOINT = 'https://api.adsabs.harvard.edu/v1/search/query'
VAULT_SOLR_BIGQUERY_ENDPOINT = 'https://api.adsabs.harvard.edu/v1/search/bigquery'

# alembic will
use_flask_db_url = True

# a json object holding whatever values we need for the bumblebee
# users; this typically is stored in consul and the microservice
# just exposes it to bbb
VAULT_BUMBLEBEE_OPTIONS = {}

VAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(levelname)s\t%(process)d '
                      '[%(asctime)s]:\t%(message)s',
            'datefmt': '%m/%d/%Y %H:%M:%S',
        }
    },
    'handlers': {
        'file': {
            'formatter': 'default',
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': '/tmp/vault_service_app.log',
        },
        'console': {
            'formatter': 'default',
            'level': 'INFO',
            'class': 'logging.StreamHandler'
        },
    },
    'loggers': {
        '': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
