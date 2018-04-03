from flask.ext.testing import TestCase
import testing.postgresql
from vault_service.models import Base

class TestCaseDatabase(TestCase):
    """
    Base test class for when databases are being used.
    """

    postgresql_url_dict = {
        'port': 1234,
        'host': '127.0.0.1',
        'user': 'postgres',
        'database': 'test'
    }
    postgresql_url = 'postgresql://{user}@{host}:{port}/{database}' \
        .format(
        user=postgresql_url_dict['user'],
        host=postgresql_url_dict['host'],
        port=postgresql_url_dict['port'],
        database=postgresql_url_dict['database']
    )

    def create_app(self):
        '''Start the wsgi application'''
        from vault_service import app
        a = app.create_app(**{
            'SQLALCHEMY_DATABASE_URI': self.postgresql_url,
            'SQLALCHEMY_ECHO': False,
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': True,
            'TRAP_BAD_REQUEST_ERRORS': True
        })
        return a

    @classmethod
    def setUpClass(cls):
        cls.postgresql = \
            testing.postgresql.Postgresql(**cls.postgresql_url_dict)

    @classmethod
    def tearDownClass(cls):
        cls.postgresql.stop()

    def setUp(self):
        Base.metadata.create_all(bind=self.app.db.engine)

    def tearDown(self):
        self.app.db.session.remove()
        self.app.db.drop_all()
