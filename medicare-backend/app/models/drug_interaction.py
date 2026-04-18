from sqlalchemy import Column, Integer, String, Text, ForeignKey, CheckConstraint
from sqlalchemy import Enum as SAEnum
from app.core.database import Base
from app.models.enums import SeverityLevel


class DrugInteraction(Base):
    __tablename__ = "drug_interactions"
    __table_args__ = (CheckConstraint("drug_a_id < drug_b_id"),)

    id           = Column(Integer, primary_key=True, index=True)
    drug_a_id    = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    drug_b_id    = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    # native_enum=False：用 VARCHAR+CHECK 存储而非 PostgreSQL 原生 ENUM 类型
    # 好处：枚举值可以随时扩展，迁移更简单，同时 Python 层仍有类型约束
    severity     = Column(
        SAEnum(SeverityLevel, name="severity_level", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    warning_text = Column(Text, nullable=False)
    advice       = Column(Text)
