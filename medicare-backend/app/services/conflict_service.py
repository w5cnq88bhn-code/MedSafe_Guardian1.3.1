"""
药物冲突检测服务

两路检测：
  1. PostgreSQL drug_interactions 表（一阶冲突）
  2. Neo4j 知识图谱推理（二阶冲突 + 直接禁忌）

图谱不可用时自动降级为纯关系表模式。
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
from app.services import graph_service

logger = logging.getLogger(__name__)

_MAX_NEW_DRUG_IDS = 20
_MAX_EXISTING_DRUG_IDS = 50


def _allergy_match(allergen: str, drug_name: str) -> bool:
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


def _build_conflict_item(inter: DrugInteraction, drugs: dict) -> Optional[ConflictItem]:
    drug_a = drugs.get(inter.drug_a_id)
    drug_b = drugs.get(inter.drug_b_id)
    if drug_a is None:
        logger.warning(f"[Conflict] 不存在的 drug_id={inter.drug_a_id}")
        return None
    if drug_b is None:
        logger.warning(f"[Conflict] 不存在的 drug_id={inter.drug_b_id}")
        return None
    severity = inter.severity.value if hasattr(inter.severity, "value") else str(inter.severity)
    return ConflictItem(
        drug_a_id=inter.drug_a_id,
        drug_a_name=drug_a.generic_name or "",
        drug_b_id=inter.drug_b_id,
        drug_b_name=drug_b.generic_name or "",
        severity=severity,
        warning_text=inter.warning_text or "",
        advice=inter.advice or "",
        reasoning_path=None,
    )


def _check_conflicts_pg(all_drug_ids: List[int], db: Session) -> List[ConflictItem]:
    """PG 关系表查询（一阶冲突）。"""
    try:
        interactions = db.query(DrugInteraction).filter(
            DrugInteraction.drug_a_id.in_(all_drug_ids),
            DrugInteraction.drug_b_id.in_(all_drug_ids),
        ).all()
    except SQLAlchemyError as e:
        logger.error(f"[Conflict-PG] 查询失败: {e}")
        return []

    try:
        drugs = {d.id: d for d in db.query(Drug).filter(Drug.id.in_(all_drug_ids)).all()}
    except SQLAlchemyError as e:
        logger.error(f"[Conflict-PG] 批量查询药物失败: {e}")
        drugs = {}

    conflicts = []
    for inter in interactions:
        item = _build_conflict_item(inter, drugs)
        if item:
            conflicts.append(item)
    return conflicts


def _check_conflicts_graph(patient_id: int, new_drug_ids: List[int],
                            all_drug_ids: List[int]) -> List[ConflictItem]:
    """
    Neo4j 知识图谱推理：二阶冲突 + 直接禁忌。
    包含：
      1. 二阶推理：新药→症状→疾病→患者已有疾病
      2. 直接禁忌：新药对患者疾病的直接禁忌
    """
    if not graph_service.is_available():
        return []

    graph_conflicts = []

    # 二阶推理：新药 → 症状 → 疾病 → 患者
    try:
        second_order = graph_service.query_second_order_conflicts(patient_id, new_drug_ids)
        for r in second_order:
            graph_conflicts.append(ConflictItem(
                drug_a_id=r["drug_id"],
                drug_a_name=r["drug_name"],
                drug_b_id=0,   # 二阶推理无对立药物，用0表示
                drug_b_name=f"患者疾病：{r['disease_name']}",
                severity="medium",
                warning_text=(
                    f"【知识图谱二阶推理】{r['drug_name']} 会引发「{r['symptom_name']}」，"
                    f"该症状与您的疾病「{r['disease_name']}」相关，存在潜在风险。"
                ),
                advice="请告知医生您的疾病史，由医生评估是否适合使用此药。",
                reasoning_path=f"{r['drug_name']} → {r['symptom_name']} → {r['disease_name']}",
            ))
    except Exception as e:
        logger.warning(f"[Conflict-Graph] 二阶推理失败: {e}")

    # 直接禁忌推理
    try:
        contraindications = graph_service.query_direct_contraindications(patient_id, new_drug_ids)
        for r in contraindications:
            graph_conflicts.append(ConflictItem(
                drug_a_id=r["drug_id"],
                drug_a_name=r["drug_name"],
                drug_b_id=0,
                drug_b_name=f"禁忌疾病：{r['disease_name']}",
                severity="high",
                warning_text=(
                    f"【知识图谱推理】{r['drug_name']} 对您的疾病「{r['disease_name']}」"
                    f"存在禁忌：{r['reason']}。"
                ),
                advice="请在医生指导下谨慎使用，或考虑替代药物。",
                reasoning_path=f"{r['drug_name']} → 禁忌 → {r['disease_name']}",
            ))
    except Exception as e:
        logger.warning(f"[Conflict-Graph] 禁忌推理失败: {e}")

    return graph_conflicts


def check_conflicts(patient_id: int, new_drug_ids: List[int], db: Session) -> ConflictCheckResponse:
    """PG + 图谱双路冲突检测，图谱不可用时降级为纯 PG 模式。"""
    if not isinstance(new_drug_ids, list):
        new_drug_ids = []
    new_drug_ids = list({int(d) for d in new_drug_ids
                         if d and isinstance(d, (int, float)) and int(d) > 0})
    if not new_drug_ids:
        return ConflictCheckResponse(conflicts=[], allergy_warnings=[], has_high_risk=False)
    if len(new_drug_ids) > _MAX_NEW_DRUG_IDS:
        new_drug_ids = new_drug_ids[:_MAX_NEW_DRUG_IDS]

    # 获取患者现有药物
    try:
        existing_ids = [
            row.drug_id for row in
            db.query(MedicationSchedule.drug_id)
              .filter(MedicationSchedule.patient_id == patient_id,
                      MedicationSchedule.is_active == True)
              .distinct().all()
        ]
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 查询现有药物失败: {e}")
        existing_ids = []

    if len(existing_ids) > _MAX_EXISTING_DRUG_IDS:
        existing_ids = existing_ids[:_MAX_EXISTING_DRUG_IDS]

    all_drug_ids = list(set(existing_ids + new_drug_ids))

    # PG 关系表
    pg_conflicts = _check_conflicts_pg(all_drug_ids, db)

    # 图谱推理
    graph_conflicts = _check_conflicts_graph(patient_id, new_drug_ids, all_drug_ids)

    # 合并，去重（同一药物对只保留一条，PG 优先）
    seen_pairs = set()
    conflicts: List[ConflictItem] = []
    for item in pg_conflicts + graph_conflicts:
        key = (min(item.drug_a_id, item.drug_b_id), max(item.drug_a_id, item.drug_b_id))
        if key not in seen_pairs:
            seen_pairs.add(key)
            conflicts.append(item)

    # 过敏检测（不变）
    try:
        allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
        new_drugs = db.query(Drug).filter(Drug.id.in_(new_drug_ids)).all()
    except SQLAlchemyError as e:
        logger.error(f"[Conflict] 过敏查询失败: {e}")
        allergies, new_drugs = [], []

    allergy_warnings: List[AllergyWarning] = []
    for drug in new_drugs:
        if not drug:
            continue
        for allergy in allergies:
            if not allergy or not allergy.drug_id_or_ingredient:
                continue
            names = [n for n in [drug.generic_name, drug.brand_name] if n and n.strip()]
            if any(_allergy_match(allergy.drug_id_or_ingredient, name) for name in names):
                allergy_warnings.append(AllergyWarning(
                    drug_id=drug.id,
                    drug_name=drug.generic_name or "",
                    matched_allergen=allergy.drug_id_or_ingredient,
                ))
                break

    has_high_risk = (
        any(c.severity == "high" for c in conflicts)
        or len(allergy_warnings) > 0
    )

    graph_used = graph_service.is_available()
    logger.info(
        f"[Conflict] patient={patient_id} pg={len(pg_conflicts)} "
        f"graph={len(graph_conflicts)} allergy={len(allergy_warnings)} "
        f"graph_engine={'on' if graph_used else 'off(degraded)'}"
    )

    return ConflictCheckResponse(
        conflicts=conflicts,
        allergy_warnings=allergy_warnings,
        has_high_risk=has_high_risk,
        graph_reasoning_used=graph_used,
    )
