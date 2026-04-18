from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from app.models.enums import MedicationStatus


class DrugWeekStat(BaseModel):
    drug_id:      int
    drug_name:    str
    total_dose:   float
    dosage_unit:  str
    missed_count: int


class Stats7DaysOut(BaseModel):
    drugs: List[DrugWeekStat]


class DrugDoseStat(BaseModel):
    """28天内单种药物的剂量统计，用于发现多服/少服情况。"""
    drug_id:          int
    drug_name:        str
    dosage_unit:      str
    planned_dose:     float   # 按计划应服总剂量
    actual_dose:      float   # 实际服用总剂量（taken_dose 累加）
    taken_count:      int     # 实际服药次数
    missed_count:     int     # 漏服次数
    dose_diff:        float   # actual_dose - planned_dose，正数=多服，负数=少服


class Stats28DaysOut(BaseModel):
    # 需求原文为"总服用数量（统一剂量单位累加）"，但多药物单位不同无法跨药累加。
    # 改为按药物分别统计剂量，能发现多服/少服，对医生更有临床价值。
    total_drug_types: int
    total_taken_count: int          # 所有药物合计服药次数（依从性概览）
    drugs: List[DrugDoseStat]       # 每种药物的剂量明细


class DailyDrugRecord(BaseModel):
    date:        date
    drug_name:   str
    dose:        float
    dosage_unit: str
    status:      MedicationStatus   # taken / missed / pending，枚举约束


class Stats14DaysOut(BaseModel):
    records: List[DailyDrugRecord]


class LifetimeDrugOut(BaseModel):
    drug_id:     int
    drug_name:   str
    first_taken: Optional[date]
    last_taken:  Optional[date]


class StatsLifetimeOut(BaseModel):
    drugs: List[LifetimeDrugOut]
