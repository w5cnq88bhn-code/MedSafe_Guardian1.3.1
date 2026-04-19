from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint, text
from app.core.database import Base


class Caregiver(Base):
    __tablename__ = "caregivers"
    __table_args__ = (UniqueConstraint("caregiver_openid", "patient_id"),)

    id               = Column(Integer, primary_key=True, index=True)
    caregiver_openid = Column(String(64), nullable=False, index=True)
    patient_id       = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    relationship     = Column(String(20), default="family")
    created_at       = Column(DateTime, nullable=False, server_default=text("NOW()"))
