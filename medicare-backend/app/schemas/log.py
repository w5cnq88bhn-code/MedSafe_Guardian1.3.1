from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class LogCreateRequest(BaseModel):
    patient_id:  int      = Field(..., gt=0)
    schedule_id: int      = Field(..., gt=0)
    actual_time: datetime
    dose:        Optional[float] = Field(None, gt=0)
    source:      str      = Field("manual", pattern=r"^(manual|bluetooth|simulate)$")


class LogOut(BaseModel):
    id:                int
    drug_id:           int
    drug_name:         str
    scheduled_time:    datetime
    actual_taken_time: Optional[datetime]
    status:            str
    taken_dose:        Optional[float]

    class Config:
        from_attributes = True


class MissedItem(BaseModel):
    """漏服列表中的单条记录，用于子女端监护首页。"""
    log_id:         int
    drug_name:      str
    scheduled_time: str    # HH:MM 格式，前端直接展示
    dosage:         float


class TodayStatusOut(BaseModel):
    total:       int
    taken:       int
    missed:      int
    pending:     int
    missed_list: List[MissedItem]


class RemindRequest(BaseModel):
    log_id: int = Field(..., gt=0, description="漏服记录ID")
