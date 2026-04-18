import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.core.deps import get_current_user, verify_patient_access
from app.models.patient import Patient
from app.models.log import MedicationLog
from app.models.drug import Drug
from app.models.schedule import MedicationSchedule
from app.models.enums import MedicationStatus
from app.schemas.log import LogCreateRequest
from app.schemas.common import Response

router = APIRouter()
logger = logging.getLogger(__name__)

# 撤销时间窗口（分钟）
_UNDO_WINDOW_MINUTES = 5
# 今日状态查询最大返回条数，防止数据量过大
_MAX_TODAY_LOGS = 200


@router.post("/logs", response_model=Response)
def create_log(
    body: LogCreateRequest,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    登记服药记录。
    防御性处理：
    - 权限校验（患者与计划归属一致）
    - 计划存在性校验
    - 重复登记幂等处理（已服状态直接返回，避免重复提交）
    - 数据库异常捕获
    """
    # 权限校验
    verify_patient_access(body.patient_id, current_user, db)

    # 计划存在性校验
    try:
        sched = db.query(MedicationSchedule).filter(
            MedicationSchedule.id == body.schedule_id
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"[Logs] 查询服药计划失败: schedule_id={body.schedule_id}, error={e}")
        return Response.error(500, "服务器内部错误，请稍后重试")

    if not sched:
        return Response.error(404, "服药计划不存在")

    # 防止 patient_id 与 schedule.patient_id 不一致（防止越权登记）
    if sched.patient_id != body.patient_id:
        logger.warning(
            f"[Logs] 越权登记尝试: current_user={current_user.id}, "
            f"body.patient_id={body.patient_id}, sched.patient_id={sched.patient_id}"
        )
        return Response.error(400, "患者与计划不匹配")

    # 计划是否仍有效
    if not sched.is_active:
        return Response.error(400, "该服药计划已停用")

    # 防御：actual_time 不能是未来时间（允许1分钟误差）
    now_utc = datetime.utcnow()
    if body.actual_time > now_utc + timedelta(minutes=1):
        logger.warning(f"[Logs] actual_time 为未来时间: {body.actual_time}, now={now_utc}")
        return Response.error(400, "服药时间不能是未来时间")

    # 计算计划服药时间
    try:
        scheduled_dt = datetime.combine(body.actual_time.date(), sched.time_point)
    except Exception as e:
        logger.error(f"[Logs] 计算 scheduled_time 失败: {e}")
        return Response.error(500, "服务器内部错误，请稍后重试")

    # 检查是否已有记录（幂等处理）
    try:
        existing = db.query(MedicationLog).filter(
            MedicationLog.schedule_id    == body.schedule_id,
            MedicationLog.patient_id     == body.patient_id,
            MedicationLog.scheduled_time == scheduled_dt,
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"[Logs] 查询已有记录失败: {e}")
        return Response.error(500, "服务器内部错误，请稍后重试")

    if existing:
        if existing.status == MedicationStatus.TAKEN:
            # 幂等：已服状态直接返回成功，不报错
            logger.debug(f"[Logs] 重复登记，幂等返回: log_id={existing.id}")
            return Response.ok({"id": existing.id})
        # pending/missed 状态更新为 taken
        try:
            existing.status            = MedicationStatus.TAKEN
            existing.actual_taken_time = body.actual_time
            existing.taken_dose        = body.dose or float(sched.dosage)
            db.commit()
            return Response.ok({"id": existing.id})
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[Logs] 更新服药记录失败: log_id={existing.id}, error={e}")
            return Response.error(500, "登记失败，请稍后重试")

    # 创建新记录
    try:
        log = MedicationLog(
            patient_id        = body.patient_id,
            drug_id           = sched.drug_id,
            schedule_id       = body.schedule_id,
            scheduled_time    = scheduled_dt,
            actual_taken_time = body.actual_time,
            status            = MedicationStatus.TAKEN,
            taken_dose        = body.dose or float(sched.dosage),
            source            = body.source or "manual",
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        logger.info(f"[Logs] 服药登记成功: log_id={log.id}, patient_id={body.patient_id}")
        return Response.ok({"id": log.id})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Logs] 创建服药记录失败: {e}")
        return Response.error(500, "登记失败，请稍后重试")


@router.delete("/logs/{log_id}", response_model=Response)
def undo_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    撤销服药登记（5分钟内有效）。
    防御性处理：
    - 记录存在性校验
    - 权限校验
    - 状态校验（只能撤销 taken 状态）
    - 时间窗口校验
    - actual_taken_time 为 None 时的安全处理
    """
    try:
        log = db.query(MedicationLog).filter(MedicationLog.id == log_id).first()
    except SQLAlchemyError as e:
        logger.error(f"[Logs] 查询服药记录失败: log_id={log_id}, error={e}")
        return Response.error(500, "服务器内部错误，请稍后重试")

    if not log:
        return Response.error(404, "记录不存在")

    # 权限校验：通过记录所属患者验证
    verify_patient_access(log.patient_id, current_user, db)

    if log.status != MedicationStatus.TAKEN:
        return Response.error(400, "只能撤销已服状态的记录")

    # 时间窗口校验
    # actual_taken_time 为 None 时（理论上不应发生），允许撤销
    if log.actual_taken_time is not None:
        now = datetime.utcnow()
        elapsed = now - log.actual_taken_time
        if elapsed > timedelta(minutes=_UNDO_WINDOW_MINUTES):
            return Response.error(403, f"超过{_UNDO_WINDOW_MINUTES}分钟，无法撤销")
    else:
        logger.warning(f"[Logs] actual_taken_time 为 None，允许撤销: log_id={log_id}")

    try:
        log.status            = MedicationStatus.PENDING
        log.actual_taken_time = None
        log.taken_dose        = None
        db.commit()
        logger.info(f"[Logs] 服药记录撤销成功: log_id={log_id}")
        return Response.ok()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Logs] 撤销服药记录失败: log_id={log_id}, error={e}")
        return Response.error(500, "撤销失败，请稍后重试")


@router.get("/logs/status/today/{patient_id}", response_model=Response)
def get_today_status(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    子女端首页：今日服药状态汇总。
    防御性处理：
    - 权限校验
    - 数据库异常捕获
    - 数量上限保护
    - 字段 None 值安全处理
    """
    # 权限校验
    verify_patient_access(patient_id, current_user, db)

    today       = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end   = datetime.combine(today, datetime.max.time())

    try:
        logs = (
            db.query(MedicationLog, Drug)
              .join(Drug, Drug.id == MedicationLog.drug_id)
              .filter(
                  MedicationLog.patient_id == patient_id,
                  MedicationLog.scheduled_time.between(today_start, today_end),
              )
              .limit(_MAX_TODAY_LOGS)
              .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Logs] 今日状态查询失败: patient_id={patient_id}, error={e}")
        return Response.error(500, "查询失败，请稍后重试")

    total   = len(logs)
    taken   = sum(1 for l, _ in logs if l.status == MedicationStatus.TAKEN)
    missed  = sum(1 for l, _ in logs if l.status == MedicationStatus.MISSED)
    pending = sum(1 for l, _ in logs if l.status == MedicationStatus.PENDING)

    missed_list = []
    for l, d in logs:
        if l.status != MedicationStatus.MISSED:
            continue
        try:
            missed_list.append({
                "log_id":         l.id,
                "drug_name":      d.generic_name if d else "未知药物",
                "scheduled_time": l.scheduled_time.strftime("%H:%M") if l.scheduled_time else "--:--",
                "dosage":         float(l.taken_dose) if l.taken_dose is not None else 0.0,
            })
        except Exception as e:
            logger.warning(f"[Logs] 漏服列表行数据异常，跳过: log_id={l.id}, error={e}")
            continue

    return Response.ok({
        "total":       total,
        "taken":       taken,
        "missed":      missed,
        "pending":     pending,
        "missed_list": missed_list,
    })
