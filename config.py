LOG_STDOUT = True
VAULT_APP_SECRET_KEY = 'fake'
VAULT_OAUTH_CLIENT_TOKEN = 'to be provided'
VAULT_VERSION = 'v0.1' # Arbitrary string identifying the service (will be returned in the headers)

SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@localhost:5432/test_vault"
SQLALCHEMY_ECHO = False

API_ENDPOINT = 'https://api.adsabs.harvard.edu'

# location of the remote solr-microservice
VAULT_SOLR_QUERY_ENDPOINT = API_ENDPOINT + '/v1/search/query'
VAULT_SOLR_BIGQUERY_ENDPOINT = API_ENDPOINT + '/v1/search/bigquery'

USER_EMAIL_ADSWS_API_URL = API_ENDPOINT + '/v1/user/%s'

# alembic will
use_flask_db_url = True

# a json object holding whatever values we need for the bumblebee
# users; this typically is stored in consul and the microservice
# just exposes it to bbb
VAULT_BUMBLEBEE_OPTIONS = {}

# limits on the size of the JSON doc stored for user preferences
MAX_ALLOWED_JSON_SIZE = 1000
MAX_ALLOWED_JSON_KEYS = 100

# user_id for anonymous users - fix in deployment config
BOOTSTRAP_USER_ID = 0

# import endpoints
HARBOUR_MYADS_IMPORT_ENDPOINT = 'https://api.adsabs.harvard.edu/v1/harbour/myads/classic/%s'

# arXiv categories and sub-categories
ALLOWED_ARXIV_CLASSES = ['astro-ph',
                         'astro-ph.GA', 'astro-ph.CO', 'astro-ph.EP', 'astro-ph.HE', 'astro-ph.IM', 'astro-ph.SR',
                         'cond-mat',
                         'cond-mat.dis-nn', 'cond-mat.mtrl-sci', 'cond-mat.mes-hall', 'cond-mat.other',
                         'cond-mat.quant-gas', 'cond-mat.soft', 'cond-mat.stat-mech', 'cond-mat.str-el',
                         'cond-mat.supr-con',
                         'gr-qc',
                         'hep-ex',
                         'hep-lat',
                         'hep-ph',
                         'hep-th',
                         'math-ph',
                         'nlin',
                         'nlin.AO', 'nlin.CG', 'nlin.CD', 'nlin.SI', 'nlin.PS',
                         'nucl-ex',
                         'nucl-th',
                         'physics',
                         'physics.acc-ph', 'physics.app-ph', 'physics.ao-ph', 'physics.atm-clus', 'physics.atom-ph',
                         'physics.bio-ph', 'physics.chem-ph', 'physics.class-ph', 'physics.comp-ph', 'physics.data-an',
                         'physics.flu-dyn', 'physics.gen-ph', 'physics.geo-ph', 'physics.hist-ph', 'physics.ins-det',
                         'physics.med-ph', 'physics.optics', 'physics.soc-ph', 'physics.ed-ph', 'physics.plasm-ph',
                         'physics.pop-ph', 'physics.space-ph',
                         'quant-ph',
                         'math',
                         'math.AG', 'math.AT', 'math.AP', 'math.CT', 'math.CA', 'math.CO', 'math.AC', 'math.CV',
                         'math.DG', 'math.DS', 'math.FA', 'math.GM', 'math.GN', 'math.GT', 'math.GR', 'math.HO',
                         'math.IT', 'math.KT', 'math.LO', 'math.MP', 'math.MG', 'math.NT', 'math.NA', 'math.OA',
                         'math.OC', 'math.PR', 'math.QA', 'math.RT', 'math.RA', 'math.SP', 'math.ST', 'math.SG',
                         'cs',
                         'cs.AI', 'cs.CL', 'cs.CC', 'cs.CE', 'cs.CG', 'cs.GT', 'cs.CV', 'cs.CY', 'cs.CR', 'cs.DS',
                         'cs.DB', 'cs.DL', 'cs.DM', 'cs.DC', 'cs.ET', 'cs.FL', 'cs.GL', 'cs.GR', 'cs.AR', 'cs.HC',
                         'cs.IR', 'cs.IT', 'cs.LO', 'cs.LG', 'cs.MS', 'cs.MA', 'cs.MM', 'cs.NI', 'cs.NE', 'cs.NA',
                         'cs.OS', 'cs.OH', 'cs.PF', 'cs.PL', 'cs.RO', 'cs.SI', 'cs.SE', 'cs.SD', 'cs.SC', 'cs.SY',
                         'q-bio',
                         'q-bio.BM', 'q-bio.CB', 'q-bio.GN', 'q-bio.MN', 'q-bio.NC', 'q-bio.OT', 'q-bio.PE', 'q-bio.QM',
                         'q-bio.SC', 'q-bio.TO',
                         'q-fin',
                         'q-fin.CP', 'q-fin.EC', 'q-fin.GN', 'q-fin.MF', 'q-fin.PM', 'q-fin.PR', 'q-fin.RM', 'q-fin.ST',
                         'q-fin.TR',
                         'stat',
                         'stat.AP', 'stat.CO', 'stat.ML', 'stat.ME', 'stat.OT', 'stat.TH',
                         'eess',
                         'eess.AS', 'eess.IV', 'eess.SP', 'eess.SY',
                         'econ',
                         'econ.EM', 'econ.GN', 'econ.TH']

# harbour db connection for import script
POSTGRES_HARBOUR = {
        'port': 1234,
        'host': 'localhost',
        'user': 'harbour',
        'database': 'harbour',
        'password': 'fix-me'
    }
