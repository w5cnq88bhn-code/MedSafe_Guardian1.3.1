from sqlalchemy import Column, Integer, String, Date, ForeignKey, text
from app.core.database import Base


class Allergy(Base):
    __tablename__ = "allergies"

    id                    = Column(Integer, primary_key=True, index=True)
    patient_id            = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    drug_id_or_ingredient = Column(String(100), nullable=False)
    reaction_type         = Column(String(100))
    added_date            = Column(Date, nullable=False, server_default=text("CURRENT_DATE"))
