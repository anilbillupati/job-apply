"""apify key usage snapshot (account, monthly usage/limit, last check)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 18:40:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('apify_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('monthly_usage_usd', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('monthly_limit_usd', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('usage_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('apify_keys', schema=None) as batch_op:
        batch_op.drop_column('usage_checked_at')
        batch_op.drop_column('monthly_limit_usd')
        batch_op.drop_column('monthly_usage_usd')
        batch_op.drop_column('account')
