"""added product catalog

Revision ID: 7ce923cb5e62
Revises: bda2d62b7958
Create Date: 2024-07-23 16:18:18.170131

"""
from alembic import op
import sqlalchemy as sa
import lib

# revision identifiers, used by Alembic.
revision = '7ce923cb5e62'
down_revision = 'bda2d62b7958'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('product_catalog',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tier', sa.String(length=30), nullable=False),
    sa.Column('rate_limit_seconds', sa.Integer(), nullable=False),
    sa.Column('created_on', lib.util_sqlalchemy.AwareDateTime(), nullable=True),
    sa.Column('updated_on', lib.util_sqlalchemy.AwareDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('product_catalog')
    # ### end Alembic commands ###
