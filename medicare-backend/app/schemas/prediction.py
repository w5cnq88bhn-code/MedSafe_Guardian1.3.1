from pydantic import BaseModel
from typing import List
from datetime import date
from app.models.enums import TimeSlot


class PredictionSlot(BaseModel):
    day_offset:       int       # 1/2/3
    time_slot:        TimeSlot  # morning/afternoon/evening，枚举约束
    miss_probability: float
    is_high_risk:     bool      # probability > 0.7


class PredictionOut(BaseModel):
    patient_id:      int
    prediction_date: date               # date 类型，比 str 更精确
    slots:           List[PredictionSlot]
    # probabilities 已移除：与 slots 冗余，前端如需扁平列表：
    # probabilities = slots.map(s => s.miss_probability)


class RuleOut(BaseModel):
    id:               int
    rule_description: str
    confidence:       float
    support:          float
    lift:             float
    suggestion:       str

    class Config:
        from_attributes = True
