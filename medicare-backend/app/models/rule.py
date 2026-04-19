from sqlalchemy import Column, Integer, Numeric, Text, Date, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class AssociationRule(Base):
    __tablename__ = "association_rules"

    id               = Column(Integer, primary_key=True, index=True)
    patient_id       = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    antecedent       = Column(JSONB, nullable=False)   # 药物ID数组，如 [1, 3]
    consequent       = Column(JSONB, nullable=False)   # 药物ID数组，如 [5]
    support          = Column(Numeric(5, 4), nullable=False)
    confidence       = Column(Numeric(5, 4), nullable=False)
    lift             = Column(Numeric(8, 4), nullable=False)
    rule_description = Column(Text, nullable=False)
    generated_date   = Column(Date, nullable=False)
    created_at       = Column(DateTime, nullable=False, server_default=text("NOW()"))
