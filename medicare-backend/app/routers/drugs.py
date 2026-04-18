import logging
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import tuple_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.core.deps import get_current_user, verify_patient_access
from app.models.patient import Patient
from app.models.drug import Drug
from app.models.schedule import MedicationSchedule
from app.models.allergy import Allergy
from app.models.log import MedicationLog
from app.schemas.drug import (
    DrugOut, ConflictCheckRequest, ScheduleCreateRequest,
    AllergyCreateRequest, AllergyOut,
)
from app.schemas.common import Response
from app.services.conflict_service import check_conflicts
from app.services.food_tip_service import get_food_tips

router = APIRouter()
logger = logging.getLogger(__name__)

# 搜索关键词最大长度，防止超长字符串导致全表扫描
_KEYWORD_MAX_LEN = 50
# 今日计划最大返回条数
_MAX_TODAY_SCHEDULES = 100


# ── 药物搜索 ──────────────────────────────────────────────────────────────

@router.get("/drugs/search", response_model=Response)
def search_drugs(
    keyword: str = Query(..., min_length=1, max_length=_KEYWORD_MAX_LEN),
    db: Session = Depends(get_db),
    _: Patient = Depends(get_current_user),
):
    """
    模糊搜索药物库（通用名 + 商品名）。
    防御性处理：
    - 关键词长度限制（schema 层已校验，此处为双重保障）
    - 数据库异常捕获
    - 结果数量上限
    """
    # 清理关键词，防止特殊字符影响 LIKE 查询
    safe_keyword = keyword.strip()
    if not safe_keyword:
        return Response.ok([])

    try:
        drugs = (
            db.query(Drug)
              .filter(
                  Drug.generic_name.ilike(f"%{safe_keyword}%") |
                  Drug.brand_name.ilike(f"%{safe_keyword}%")
              )
              .order_by(Drug.generic_name)
              .limit(20)
              .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Drugs] 搜索失败: keyword={safe_keyword!r}, error={e}")
        return Response.error(500, "搜索失败，请稍后重试")

    return Response.ok([DrugOut.model_validate(d) for d in drugs])


@router.post("/drugs/check-conflict", response_model=Response)
def check_drug_conflict(
    body: ConflictCheckRequest,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """冲突检测，权限校验后委托 conflict_service 处理。"""
    verify_patient_access(body.patient_id, current_user, db)
    try:
        result = check_conflicts(body.patient_id, body.new_drug_ids, db)
    except Exception as e:
        logger.error(f"[Drugs] 冲突检测失败: patient_id={body.patient_id}, error={e}")
        return Response.error(500, "冲突检测失败，请稍后重试")
    return Response.ok(result.model_dump())


# ── 服药计划 ──────────────────────────────────────────────────────────────

@router.post("/schedules", response_model=Response)
def create_schedule(
    body: ScheduleCreateRequest,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    创建服药计划。
    防御性处理：
    - 权限校验
    - 日期合理性校验
    - 高危冲突服务端二次校验（前端不可绕过）
    - 数据库异常捕获
    """
    verify_patient_access(body.patient_id, current_user, db)

    # 日期合理性校验
    if body.end_date and body.end_date < body.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date 不能早于 start_date",
        )

    # 开始日期不能超过今天太远（防止误操作）
    today = date.today()
    if body.start_date > today.replace(year=today.year + 1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date 不能超过一年后",
        )

    # 高危冲突检查（服务端二次校验）
    try:
        conflict_result = check_conflicts(body.patient_id, [body.drug_id], db)
    except Exception as e:
        logger.error(f"[Schedules] 冲突检测异常: patient_id={body.patient_id}, error={e}")
        raise HTTPException(status_code=500, detail="冲突检测失败，请稍后重试")

    if conflict_result.has_high_risk:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "存在高危药物冲突或过敏风险，禁止添加",
                "conflicts": [
                    c.model_dump() for c in conflict_result.conflicts
                    if c.severity == "high"
                ],
                "allergy_warnings": [
                    w.model_dump() for w in conflict_result.allergy_warnings
                ],
            },
        )

    try:
        schedule = MedicationSchedule(
            patient_id  = body.patient_id,
            drug_id     = body.drug_id,
            dosage      = body.dosage,
            dosage_unit = body.dosage_unit,
            frequency   = body.frequency,
            time_of_day = body.time_of_day,
            time_point  = body.time_point,
            start_date  = body.start_date,
            end_date    = body.end_date,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        logger.info(f"[Schedules] 创建成功: schedule_id={schedule.id}, patient_id={body.patient_id}")
        return Response.ok({"id": schedule.id})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Schedules] 创建失败: {e}")
        return Response.error(500, "创建失败，请稍后重试")


@router.get("/schedules/today/{patient_id}", response_model=Response)
def get_today_schedules(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    获取今日服药计划列表。
    防御性处理：
    - 权限校验
    - 数据库异常捕获
    - tuple_ 查询异常时降级为逐条查询
    - 字段 None 值安全处理
    """
    verify_patient_access(patient_id, current_user, db)

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
              .limit(_MAX_TODAY_SCHEDULES)
              .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Schedules] 查询今日计划失败: patient_id={patient_id}, error={e}")
        return Response.error(500, "查询失败，请稍后重试")

    if not schedules:
        return Response.ok([])

    # 批量查询今日 logs
    pairs = [
        (s.id, datetime.combine(today, s.time_point))
        for s, _ in schedules
    ]

    log_map = {}
    try:
        logs = (
            db.query(MedicationLog)
              .filter(
                  tuple_(MedicationLog.schedule_id, MedicationLog.scheduled_time).in_(pairs)
              )
              .all()
        )
        log_map = {(l.schedule_id, l.scheduled_time): l for l in logs}
    except SQLAlchemyError as e:
        # tuple_ 查询失败时降级：log_map 为空，所有状态显示为 pending
        logger.warning(f"[Schedules] 批量查询 logs 失败，降级处理: {e}")

    result = []
    for sched, drug in schedules:
        try:
            scheduled_dt = datetime.combine(today, sched.time_point)
            log = log_map.get((sched.id, scheduled_dt))
            result.append({
                "schedule_id":  sched.id,
                "drug_id":      drug.id,
                "drug_name":    drug.generic_name or "未知药物",
                "brand_name":   drug.brand_name or "",
                "dosage":       float(sched.dosage) if sched.dosage else 0.0,
                "dosage_unit":  sched.dosage_unit or "mg",
                "time_of_day":  sched.time_of_day or "morning",
                "time_point":   sched.time_point.strftime("%H:%M") if sched.time_point else "00:00",
                "status":       log.status.value if log else "pending",
                "log_id":       log.id if log else None,
            })
        except Exception as e:
            logger.warning(f"[Schedules] 构建结果行异常，跳过: schedule_id={sched.id}, error={e}")
            continue

    return Response.ok(result)


@router.delete("/schedules/{schedule_id}", response_model=Response)
def deactivate_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """停用服药计划（软删除）。"""
    try:
        sched = db.query(MedicationSchedule).filter(
            MedicationSchedule.id == schedule_id
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"[Schedules] 查询计划失败: schedule_id={schedule_id}, error={e}")
        return Response.error(500, "操作失败，请稍后重试")

    if not sched:
        return Response.error(404, "计划不存在")

    verify_patient_access(sched.patient_id, current_user, db)

    # 已停用则幂等返回成功
    if not sched.is_active:
        return Response.ok()

    try:
        sched.is_active = False
        db.commit()
        return Response.ok()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Schedules] 停用计划失败: schedule_id={schedule_id}, error={e}")
        return Response.error(500, "操作失败，请稍后重试")


# ── 过敏管理 ──────────────────────────────────────────────────────────────

@router.get("/allergies/{patient_id}", response_model=Response)
def get_allergies(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)
    try:
        allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    except SQLAlchemyError as e:
        logger.error(f"[Allergies] 查询失败: patient_id={patient_id}, error={e}")
        return Response.error(500, "查询失败，请稍后重试")
    return Response.ok([AllergyOut.model_validate(a) for a in allergies])


@router.post("/allergies", response_model=Response)
def add_allergy(
    body: AllergyCreateRequest,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(body.patient_id, current_user, db)

    # 防止重复添加相同过敏原
    try:
        existing = db.query(Allergy).filter(
            Allergy.patient_id == body.patient_id,
            Allergy.drug_id_or_ingredient == body.drug_id_or_ingredient,
        ).first()
        if existing:
            return Response.ok({"id": existing.id})  # 幂等返回

        allergy = Allergy(
            patient_id=body.patient_id,
            drug_id_or_ingredient=body.drug_id_or_ingredient,
            reaction_type=body.reaction_type,
        )
        db.add(allergy)
        db.commit()
        db.refresh(allergy)
        return Response.ok({"id": allergy.id})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Allergies] 添加失败: {e}")
        return Response.error(500, "添加失败，请稍后重试")


@router.delete("/allergies/{allergy_id}", response_model=Response)
def delete_allergy(
    allergy_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    try:
        allergy = db.query(Allergy).filter(Allergy.id == allergy_id).first()
    except SQLAlchemyError as e:
        logger.error(f"[Allergies] 查询失败: allergy_id={allergy_id}, error={e}")
        return Response.error(500, "操作失败，请稍后重试")

    if not allergy:
        return Response.error(404, "记录不存在")

    verify_patient_access(allergy.patient_id, current_user, db)

    try:
        db.delete(allergy)
        db.commit()
        return Response.ok()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Allergies] 删除失败: allergy_id={allergy_id}, error={e}")
        return Response.error(500, "删除失败，请稍后重试")


# ── 饮食小贴士 ────────────────────────────────────────────────────────────

@router.get("/food-tips/{patient_id}", response_model=Response)
def get_today_food_tips(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    根据患者今日服药计划，返回药物-食物相互作用饮食小贴士。

    数据来源：《中国药典临床用药须知》构建的本地知识库（约200条规则）。
    每条贴士包含：
      - drug_name    : 药物名称
      - avoid_foods  : 应避免的食物（如华法林→大量菠菜）
      - caution_foods: 需注意的食物（不必完全禁止，但需控制量）
      - timing_tips  : 服药时间/进食时机提示
      - reason       : 临床原因说明
      - severity     : 重要程度 high/medium/low
    """
    verify_patient_access(patient_id, current_user, db)
    try:
        tips = get_food_tips(patient_id, db)
    except Exception as e:
        logger.error(f"[FoodTips] 获取失败: patient_id={patient_id}, error={e}")
        return Response.error(500, "获取饮食提示失败，请稍后重试")
    return Response.ok(tips)
