VAULT_APP_SECRET_KEY = 'fake'
VAULT_OAUTH_CLIENT_TOKEN = 'to be provided'
VAULT_VERSION = 'v0.1' # Arbitrary string identifying the service (will be returned in the headers)

SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@localhost:5432/test_vault"
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

# limits on the size of the JSON doc stored for user preferences
MAX_ALLOWED_JSON_SIZE = 1000
MAX_ALLOWED_JSON_KEYS = 100
