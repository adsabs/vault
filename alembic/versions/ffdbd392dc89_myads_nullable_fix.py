"""myads-nullable-fix

Revision ID: ffdbd392dc89
Revises: c342556e5569
Create Date: 2020-01-28 15:34:01.551677

"""

# revision identifiers, used by Alembic.
revision = 'ffdbd392dc89'
down_revision = 'c342556e5569'

from alembic import op
import sqlalchemy as sa

                               


def upgrade():
    #with app.app_context() as c:
    #   db.session.add(Model())
    #   db.session.commit()

    op.alter_column('myads', 'template', nullable=True)


def downgrade():
    op.alter_column('myads', 'template', nullable=False)
