"""
药物-食物相互作用提示服务
根据患者今日服药计划，聚合生成饮食小贴士卡片数据。
"""
import logging
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import date

from app.models.schedule import MedicationSchedule
from app.models.drug import Drug
from app.services.drug_food_kb import get_rules_for_drug, FoodRule

logger = logging.getLogger(__name__)


def _deduplicate(items: List[str]) -> List[str]:
    """去重并保持顺序。"""
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_food_tips(patient_id: int, db: Session) -> List[dict]:
    """
    根据患者今日有效服药计划，返回饮食小贴士列表。

    返回格式（每条贴士对应一种药物）：
    [
      {
        "drug_name":     "华法林",
        "avoid_foods":   ["大量菠菜", "大量西兰花", "葡萄柚"],
        "caution_foods": ["菠菜", "西兰花", "卷心菜"],
        "timing_tips":   ["每天绿叶蔬菜摄入量保持稳定"],
        "reason":        "绿叶蔬菜富含维生素K...",
        "severity":      "high",
      },
      ...
    ]

    设计原则：
    - 同一药物的多条规则合并（avoid_foods/caution_foods/timing_tips 去重合并）
    - 按 severity 降序排列（high → medium → low）
    - 无匹配规则的药物不出现在结果中
    - 数据库异常时返回空列表，不影响主流程
    """
    today = date.today()

    try:
        schedules = (
            db.query(MedicationSchedule, Drug)
              .join(Drug, Drug.id == MedicationSchedule.drug_id)
              .filter(
                  MedicationSchedule.patient_id == patient_id,
                  MedicationSchedule.is_active == True,
                  MedicationSchedule.start_date <= today,
                  (MedicationSchedule.end_date == None) | (MedicationSchedule.end_date >= today),
              )
              .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[FoodTip] 查询今日计划失败: patient_id={patient_id}, error={e}")
        return []

    if not schedules:
        return []

    # 按药物去重（同一药物可能有多个时段计划）
    seen_drug_ids = set()
    tips = []

    _SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    for sched, drug in schedules:
        if drug.id in seen_drug_ids:
            continue
        seen_drug_ids.add(drug.id)

        drug_name = drug.generic_name or ""
        brand_name = drug.brand_name or ""

        # 用通用名和商品名分别匹配，合并结果
        rules: List[FoodRule] = []
        for name in [drug_name, brand_name]:
            if name:
                rules.extend(get_rules_for_drug(name))

        # 规则去重（同一规则对象可能被通用名和商品名各匹配一次）
        unique_rules = list({id(r): r for r in rules}.values())

        if not unique_rules:
            continue

        # 合并同一药物的所有规则
        merged_avoid: List[str] = []
        merged_caution: List[str] = []
        merged_timing: List[str] = []
        merged_reasons: List[str] = []
        max_severity = "low"

        for rule in unique_rules:
            merged_avoid.extend(rule.avoid_foods)
            merged_caution.extend(rule.caution_foods)
            merged_timing.extend(rule.timing_tips)
            if rule.reason and rule.reason not in merged_reasons:
                merged_reasons.append(rule.reason)
            if _SEVERITY_ORDER.get(rule.severity, 2) < _SEVERITY_ORDER.get(max_severity, 2):
                max_severity = rule.severity

        tips.append({
            "drug_name":     drug_name,
            "avoid_foods":   _deduplicate(merged_avoid),
            "caution_foods": _deduplicate(merged_caution),
            "timing_tips":   _deduplicate(merged_timing),
            "reason":        "；".join(merged_reasons),
            "severity":      max_severity,
        })

    # 按严重程度降序排列
    tips.sort(key=lambda t: _SEVERITY_ORDER.get(t["severity"], 2))

    logger.debug(f"[FoodTip] patient_id={patient_id} 生成贴士 {len(tips)} 条")
    return tips
