"""change datatype user table

Revision ID: 2630a610fb5b
Revises: 4c05e8316b26
Create Date: 2018-03-12 15:14:54.218935

"""

# revision identifiers, used by Alembic.
revision = '2630a610fb5b'
down_revision = '4c05e8316b26'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
                               


def upgrade():
    op.alter_column('users','user_data',
                    existing_type=sa.LargeBinary,
                    type_=postgresql.JSONB,
                    existing_nullable=True,
                    postgresql_using="convert_from(user_data,'utf-8')::jsonb")

def downgrade():
    op.alter_column('users', 'user_data',
                    existing_type=postgresql.JSONB,
                    type_=sa.LargeBinary,
                    existing_nullable=True,
                    postgresql_using="convert_to(user_data::text,'utf-8')")
