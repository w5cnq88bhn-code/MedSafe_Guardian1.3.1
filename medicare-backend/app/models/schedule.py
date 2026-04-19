from sqlalchemy import Column, Integer, String, SmallInteger, Numeric, Time, Date, Boolean, ForeignKey, DateTime, text
from sqlalchemy import Enum as SAEnum
from app.core.database import Base
from app.models.enums import TimeSlot


class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"

    id          = Column(Integer, primary_key=True, index=True)
    patient_id  = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    drug_id     = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    dosage      = Column(Numeric(8, 2), nullable=False)
    dosage_unit = Column(String(20), nullable=False, default="mg")
    frequency   = Column(SmallInteger, nullable=False, default=1)
    time_of_day = Column(
        SAEnum(TimeSlot, name="time_slot", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    time_point  = Column(Time, nullable=False)
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date)
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime, nullable=False, server_default=text("NOW()"))
