"""
药物冲突检测 + 过敏检测服务
逻辑：
1. 获取患者当前所有有效药物 ID（含新药）
2. 两两查询 drug_interactions 表
3. 查询患者过敏名单，对新药名称做匹配
"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.drug import Drug
from app.models.drug_interaction import DrugInteraction
from app.models.allergy import Allergy
from app.models.schedule import MedicationSchedule
from app.schemas.drug import ConflictItem, AllergyWarning, ConflictCheckResponse

logger = logging.getLogger(__name__)

# 单次冲突检测允许的最大新药数量，防止超大请求导致笛卡尔积爆炸
_MAX_NEW_DRUG_IDS = 20
# 单次检测允许的最大已有药物数量
_MAX_EXISTING_DRUG_IDS = 50


def _allergy_match(allergen: str, drug_name: str) -> bool:
    """
    判断药物名称是否与过敏原匹配。
    匹配策略（按优先级）：
      1. 精确匹配（大小写不敏感）
      2. 药物名是过敏原的子串（过敏原记录更详细，如"阿司匹林肠溶片"匹配药物"阿司匹林"）
      3. 过敏原是药物名的子串（如"头孢"匹配"头孢克肟"）
         — 仅当过敏原长度 >= 3 时启用，避免单字/双字过敏原误匹配
    """
    if not allergen or not drug_name:
        return False
    a = allergen.lower().strip()
    n = drug_name.lower().strip()
    if not a or not n:
        return False
    if a == n:
        return True
    if n in a:
        return True
    if len(a) >= 3 and a in n:
        return True
    return False


def _safe_drug_name(drug: Optional[Drug], fallback: str = "") -> str:
    """安全获取药物名称，防止 None 引发 AttributeError。"""
    if drug is None:
        return fallback
    return drug.generic_name or fallback


def _build_conflict_item(inter: DrugInteraction, drugs: dict) -> Optional[ConflictItem]:
    """
    构建冲突条目，防御性处理药物不存在的情况。
    若相互作用记录中的药物 ID 在药物表中找不到，记录警告并跳过。
    """
    drug_a = drugs.get(inter.drug_a_id)
    drug_b = drugs.get(inter.drug_b_id)

    if drug_a is None:
        logger.warning(f"[Conflict] drug_interactions 引用了不存在的 drug_id={inter.drug_a_id}")
        return None
    if drug_b is None:
        logger.warning(f"[Conflict] drug_interactions 引用了不存在的 drug_id={inter.drug_b_id}")
        return None

    return ConflictItem(
        drug_a_id=inter.drug_a_id,
        drug_a_name=drug_a.generic_name or "",
        drug_b_id=inter.drug_b_id,
        drug_b_name=drug_b.generic_name or "",
        severity=inter.severity or "low",
        warning_text=inter.warning_text or "",
        advice=inter.advice or "",
    )


def check_conflicts(patient_id: int, new_drug_ids: List[int], db: Session) -> ConflictCheckResponse:
    """
    检测新药与患者现有药物之间的冲突及过敏风险。

    防御性处理：
    - 输入参数校验（空列表、超大列表）
    - 数据库查询异常捕获
    - 药物记录缺失时跳过而非崩溃
    - 过敏匹配时防止 None 值
    """
    # 输入校验
    if not isinstance(new_drug_ids, list):
        logger.warning(f"[Conflict] new_drug_ids 类型异常: {type(new_drug_ids)}")
        new_drug_ids = []

    # 去重并过滤无效 ID
    new_drug_ids = list({int(d) for d in new_drug_ids if d and isinstance(d, (int, float)) and int(d) > 0})

    if not new_drug_ids:
        logger.debug(f"[Conflict] patient_id={patient_id} 无有效新药 ID，跳过检测")
        return ConflictCheckResponse(conflicts=[], allergy_warnings=[], has_high_risk=False)

    if len(new_drug_ids) > _MAX_NEW_DRUG_IDS:
        logger.warning(f"[Conflict] 新药数量超限: {len(new_drug_ids)} > {_MAX_NEW_DRUG_IDS}，截断处理")
        new_drug_ids = new_drug_ids[:_MAX_NEW_DRUG_IDS]

    # 1. 获取患者当前有效药物 ID
    try:
        existing_ids = [
            row.drug_id for row in
            db.query(MedicationSchedule.drug_id)
              .filter(
                  MedicationSchedule.patient_id == patient_id,
                  MedicationSchedule.is_active == True,
              )
              .distinct()
              .all()
        ]
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 查询现有药物失败: patient_id={patient_id}, error={e}")
        existing_ids = []

    # 防止已有药物列表过大
    if len(existing_ids) > _MAX_EXISTING_DRUG_IDS:
        logger.warning(f"[Conflict] 已有药物数量超限: {len(existing_ids)}，截断处理")
        existing_ids = existing_ids[:_MAX_EXISTING_DRUG_IDS]

    all_drug_ids = list(set(existing_ids + new_drug_ids))

    # 2. 查询所有涉及这些药物的相互作用
    try:
        interactions = db.query(DrugInteraction).filter(
            DrugInteraction.drug_a_id.in_(all_drug_ids),
            DrugInteraction.drug_b_id.in_(all_drug_ids),
        ).all()
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 查询药物相互作用失败: {e}")
        interactions = []

    # 批量加载药物信息，防止 N+1 查询
    try:
        drugs = {d.id: d for d in db.query(Drug).filter(Drug.id.in_(all_drug_ids)).all()}
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 批量查询药物信息失败: {e}")
        drugs = {}

    # 构建冲突列表，跳过无效记录
    conflicts: List[ConflictItem] = []
    for inter in interactions:
        item = _build_conflict_item(inter, drugs)
        if item is not None:
            conflicts.append(item)

    # 3. 过敏检测
    try:
        allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 查询过敏记录失败: patient_id={patient_id}, error={e}")
        allergies = []

    try:
        new_drugs = db.query(Drug).filter(Drug.id.in_(new_drug_ids)).all()
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 查询新药信息失败: {e}")
        new_drugs = []

    allergy_warnings: List[AllergyWarning] = []
    for drug in new_drugs:
        if drug is None:
            continue
        matched = False
        for allergy in allergies:
            if allergy is None or not allergy.drug_id_or_ingredient:
                continue
            allergen = allergy.drug_id_or_ingredient
            # 同时检查通用名和商品名
            names_to_check = [
                n for n in [drug.generic_name, drug.brand_name]
                if n and n.strip()
            ]
            if any(_allergy_match(allergen, name) for name in names_to_check):
                allergy_warnings.append(AllergyWarning(
                    drug_id=drug.id,
                    drug_name=drug.generic_name or "",
                    matched_allergen=allergen,
                ))
                matched = True
                break  # 同一药物只报一次

    has_high_risk = (
        any(c.severity == "high" for c in conflicts)
        or len(allergy_warnings) > 0
    )

    logger.debug(
        f"[Conflict] patient_id={patient_id} 检测完成: "
        f"conflicts={len(conflicts)}, allergy_warnings={len(allergy_warnings)}, "
        f"has_high_risk={has_high_risk}"
    )

    return ConflictCheckResponse(
        conflicts=conflicts,
        allergy_warnings=allergy_warnings,
        has_high_risk=has_high_risk,
    )
