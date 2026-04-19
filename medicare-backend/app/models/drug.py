from sqlalchemy import Column, Integer, String, Text
from app.core.database import Base


class Drug(Base):
    __tablename__ = "drugs"

    id           = Column(Integer, primary_key=True, index=True)
    generic_name = Column(String(100), nullable=False)
    brand_name   = Column(String(100))
    category     = Column(String(50))
    description  = Column(Text)
