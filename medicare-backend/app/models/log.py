from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, text
from sqlalchemy import Enum as SAEnum
from app.core.database import Base
from app.models.enums import MedicationStatus


class MedicationLog(Base):
    __tablename__ = "medication_logs"

    id                = Column(Integer, primary_key=True, index=True)
    patient_id        = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    drug_id           = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    schedule_id       = Column(Integer, ForeignKey("medication_schedules.id", ondelete="SET NULL"))
    scheduled_time    = Column(DateTime, nullable=False)
    actual_taken_time = Column(DateTime)
    status            = Column(
        SAEnum(MedicationStatus, name="medication_status", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MedicationStatus.PENDING,
    )
    taken_dose        = Column(Numeric(8, 2))
    source            = Column(String(20), nullable=False, default="manual")
    created_at        = Column(DateTime, nullable=False, server_default=text("NOW()"))
