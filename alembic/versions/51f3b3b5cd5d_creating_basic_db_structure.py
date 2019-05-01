"""Creating basic DB structure

Revision ID: 51f3b3b5cd5d
Revises: None
Create Date: 2014-08-08 20:13:58.241566

"""

# revision identifiers, used by Alembic.
revision = '51f3b3b5cd5d'
down_revision = None

from alembic import op
import sqlalchemy as sa
import datetime




def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('user_data', sa.LargeBinary, nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('queries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('uid', sa.Integer(), nullable=True),
    sa.Column('qid', sa.String(length=32), nullable=True),
    sa.Column('created', sa.DateTime(), nullable=True, default=datetime.datetime.utcnow),
    sa.Column('updated', sa.DateTime(), nullable=True, default=datetime.datetime.utcnow),
    sa.Column('numfound', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=255), nullable=True),
    sa.Column('query', sa.LargeBinary, nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('qid')
    )
    

def downgrade():
    op.drop_table('queries')
    op.drop_table('users')