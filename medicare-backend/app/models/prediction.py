from sqlalchemy import Column, Integer, SmallInteger, String, Numeric, Date, DateTime, ForeignKey, UniqueConstraint, text
from app.core.database import Base


class AdherencePrediction(Base):
    __tablename__ = "adherence_predictions"
    __table_args__ = (
        UniqueConstraint("patient_id", "prediction_date", "target_day_offset", "target_time_slot",
                         name="uq_prediction"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    patient_id        = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    prediction_date   = Column(Date, nullable=False)
    target_day_offset = Column(SmallInteger, nullable=False)   # 1/2/3
    target_time_slot  = Column(String(20), nullable=False)     # morning/afternoon/evening
    miss_probability  = Column(Numeric(5, 4), nullable=False)
    model_version     = Column(String(20), nullable=False, default="v1.0")
    created_at        = Column(DateTime, nullable=False, server_default=text("NOW()"))
