"""initial schema

Revision ID: da8e484cb12d
Revises: 
Create Date: 2026-11-14 22:12:43.172744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'da8e484cb12d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Hand-added: Alembic can't detect extensions. The slots exclusion
    # constraint ("same doctor AND overlapping time") needs btree_gist so a
    # GiST index can compare plain integers (doctor_id) with "=".
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table('patients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('specialties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('referral_required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('doctors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('specialty_id', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_doctors_specialty_id'), 'doctors', ['specialty_id'], unique=False)
    op.create_table('referrals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('specialty_id', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_until', sa.Date(), nullable=False),
    sa.CheckConstraint('valid_until >= valid_from', name='ck_referrals_valid_range'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_referrals_patient_id'), 'referrals', ['patient_id'], unique=False)
    op.create_table('slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('doctor_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    postgresql.ExcludeConstraint((sa.column('doctor_id'), '='), (sa.text('tstzrange(start_time, end_time)'), '&&'), using='gist', name='ex_slots_no_overlap'),
    sa.CheckConstraint('end_time > start_time', name='ck_slots_end_after_start'),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('appointments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slot_id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('referral_id', sa.Integer(), nullable=True),
    sa.Column('specialty_id', sa.Integer(), nullable=False),
    sa.Column('appointment_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('active', 'cancelled', name='appointment_status'), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['referral_id'], ['referrals.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appointments_patient_id'), 'appointments', ['patient_id'], unique=False)
    op.create_index('uq_appointments_active_patient_specialty_day', 'appointments', ['patient_id', 'specialty_id', 'appointment_date'], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_index('uq_appointments_active_referral', 'appointments', ['referral_id'], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_index('uq_appointments_active_slot', 'appointments', ['slot_id'], unique=True, postgresql_where=sa.text("status = 'active'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_appointments_active_slot', table_name='appointments', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('uq_appointments_active_referral', table_name='appointments', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('uq_appointments_active_patient_specialty_day', table_name='appointments', postgresql_where=sa.text("status = 'active'"))
    op.drop_index(op.f('ix_appointments_patient_id'), table_name='appointments')
    op.drop_table('appointments')
    op.drop_table('slots')
    op.drop_index(op.f('ix_referrals_patient_id'), table_name='referrals')
    op.drop_table('referrals')
    op.drop_index(op.f('ix_doctors_specialty_id'), table_name='doctors')
    op.drop_table('doctors')
    op.drop_table('specialties')
    op.drop_table('patients')

    # Hand-added: dropping the table does NOT drop its enum type, and the
    # extension was created by this migration.
    op.execute("DROP TYPE appointment_status")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
