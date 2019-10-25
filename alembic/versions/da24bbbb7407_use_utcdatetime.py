"""use UTCDateTime

Revision ID: da24bbbb7407
Revises: 2630a610fb5b
Create Date: 2019-04-30 17:25:55.223236

"""

# revision identifiers, used by Alembic.
revision = 'da24bbbb7407'
down_revision = '2630a610fb5b'

from alembic import op
import sqlalchemy as sa
from adsmutils import UTCDateTime
                               


def upgrade():
    #with app.app_context() as c:
    #   db.session.add(Model())
    #   db.session.commit()

    op.alter_column('queries', 'created',
                    existing_type=sa.DateTime(),
                    type_=UTCDateTime,
                    existing_nullable=True)
    op.alter_column('queries', 'updated',
                    existing_type=sa.DateTime(),
                    type_=UTCDateTime,
                    existing_nullable=True)
    op.add_column('users', sa.Column('created', UTCDateTime))
    op.add_column('users', sa.Column('updated', UTCDateTime))



def downgrade():
    op.alter_column('queries', 'created',
                    existing_type=UTCDateTime,
                    type_=sa.DateTime(),
                    existing_nullable=True)
    op.alter_column('queries', 'updated',
                    existing_type=UTCDateTime,
                    type_=sa.DateTime(),
                    existing_nullable=True)
    op.drop_column('users', 'created')
    op.drop_column('users', 'updated')
