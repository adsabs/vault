"""add myads table

Revision ID: c342556e5569
Revises: da24bbbb7407
Create Date: 2019-09-20 09:28:52.565804

"""

# revision identifiers, used by Alembic.
revision = 'c342556e5569'
down_revision = 'da24bbbb7407'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from adsmutils import UTCDateTime
                               


def upgrade():
    #with app.app_context() as c:
    #   db.session.add(Model())
    #   db.session.commit()

    op.create_table('myads',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('query_id', sa.Integer(), sa.ForeignKey('queries.id'), nullable=True),
                    sa.Column('type', postgresql.ENUM('template', 'query', name='myads_type'), nullable=False),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.Column('active', sa.Boolean(), nullable=False),
                    sa.Column('stateful', sa.Boolean(), nullable=False),
                    sa.Column('frequency', postgresql.ENUM('daily', 'weekly', name='myads_frequency'), nullable=False),
                    sa.Column('template', postgresql.ENUM('arxiv', 'citations', 'authors', 'keyword', name='myads_template'), nullable=False),
                    sa.Column('classes', postgresql.ARRAY(sa.Text()), nullable=True),
                    sa.Column('data', sa.String(), nullable=True),
                    sa.Column('created', UTCDateTime),
                    sa.Column('updated', UTCDateTime),
                    sa.PrimaryKeyConstraint('id')
                    )


def downgrade():
    op.drop_table('myads')
    op.execute('DROP TYPE myads_type')
    op.execute('DROP TYPE myads_frequency')
    op.execute('DROP TYPE myads_template')
