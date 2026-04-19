from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time


class DrugOut(BaseModel):
    id: int
    generic_name: str
    brand_name: Optional[str]
    category: Optional[str]
    description: Optional[str]

    class Config:
        from_attributes = True


class ConflictItem(BaseModel):
    drug_a_id: int
    drug_a_name: str
    drug_b_id: int
    drug_b_name: str
    severity: str          # high/medium/low
    warning_text: str
    advice: Optional[str]
    reasoning_path: Optional[str] = None   # 图谱推理路径，如 "药物A → 症状B → 疾病C"


class AllergyWarning(BaseModel):
    drug_id: int
    drug_name: str
    matched_allergen: str


class ConflictCheckRequest(BaseModel):
    patient_id: int
    new_drug_ids: List[int]


class ConflictCheckResponse(BaseModel):
    conflicts: List[ConflictItem]
    allergy_warnings: List[AllergyWarning]
    has_high_risk: bool
    graph_reasoning_used: bool = False   # 是否启用了图谱推理引擎


class ScheduleCreateRequest(BaseModel):
    patient_id: int
    drug_id: int
    dosage: float
    dosage_unit: str = "mg"
    frequency: int = 1
    time_of_day: str          # morning/afternoon/evening
    time_point: time
    start_date: date
    end_date: Optional[date] = None


class ScheduleOut(BaseModel):
    id: int
    drug_id: int
    drug_name: str
    dosage: float
    dosage_unit: str
    time_of_day: str
    time_point: str
    status: Optional[str] = None   # today's status: pending/taken/missed

    class Config:
        from_attributes = True


class AllergyCreateRequest(BaseModel):
    patient_id: int
    drug_id_or_ingredient: str
    reaction_type: Optional[str] = None


class AllergyOut(BaseModel):
    id: int
    drug_id_or_ingredient: str
    reaction_type: Optional[str]
    added_date: date

    class Config:
        from_attributes = True
