"""updated subscription table

Revision ID: bd908fbe392b
Revises: 3b194bc2bf10
Create Date: 2024-07-09 11:27:12.831106

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bd908fbe392b'
down_revision = '3b194bc2bf10'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('subscriptions', sa.Column('customer_id', sa.String(length=128), nullable=True))
    op.add_column('subscriptions', sa.Column('subscription_id', sa.String(length=128), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('subscriptions', 'subscription_id')
    op.drop_column('subscriptions', 'customer_id')
    # ### end Alembic commands ###
