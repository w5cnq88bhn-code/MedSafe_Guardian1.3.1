from sqlalchemy import Column, Integer, String, SmallInteger, Text, DateTime, text
from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id                = Column(Integer, primary_key=True, index=True)
    openid            = Column(String(64), unique=True, nullable=False)
    name              = Column(String(50))
    phone             = Column(String(20))
    birth_year        = Column(SmallInteger)
    diagnosis_disease = Column(Text)
    created_at        = Column(DateTime, nullable=False, server_default=text("NOW()"))
