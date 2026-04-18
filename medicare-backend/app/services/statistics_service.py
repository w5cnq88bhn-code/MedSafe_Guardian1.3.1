"""
统计服务：7天/28天/14天/长期
所有查询统一加上 <= date.today() 上限，排除未来 pending 记录干扰统计结果。
"""
import logging
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.models.log import MedicationLog
from app.models.drug import Drug
from app.models.schedule import MedicationSchedule
from app.schemas.statistics import (
    Stats7DaysOut, DrugWeekStat,
    Stats28DaysOut, DrugDoseStat,
    Stats14DaysOut, DailyDrugRecord,
    StatsLifetimeOut, LifetimeDrugOut,
)

logger = logging.getLogger(__name__)

# 统计查询的最大天数上限，防止超大范围查询拖垮数据库
_MAX_STATS_DAYS = 365


def _date_range_filter(since: date):
    """返回统一的日期范围过滤条件：[since, today]，排除未来记录。"""
    today = date.today()
    # 防御：since 不能晚于 today
    if since > today:
        logger.warning(f"[Stats] since={since} 晚于 today={today}，重置为 today")
        since = today
    return [
        func.date(MedicationLog.scheduled_time) >= since,
        func.date(MedicationLog.scheduled_time) <= today,
    ]


def _safe_float(value, default: float = 0.0) -> float:
    """安全转换为 float，防止 None 或非数值类型引发异常。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"[Stats] 无法转换为 float: {value!r}，使用默认值 {default}")
        return default


def _safe_int(value, default: int = 0) -> int:
    """安全转换为 int，防止 None 或非数值类型引发异常。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(f"[Stats] 无法转换为 int: {value!r}，使用默认值 {default}")
        return default


def _safe_status(status_val) -> str:
    """安全提取 status 字符串，兼容枚举和字符串两种形式。"""
    if status_val is None:
        return "pending"
    if hasattr(status_val, "value"):
        return str(status_val.value)
    return str(status_val)


def get_7days_stats(patient_id: int, db: Session) -> Stats7DaysOut:
    """
    获取近7天服药统计。
    防御性处理：数据库异常时返回空列表而非崩溃。
    """
    if not isinstance(patient_id, int) or patient_id <= 0:
        logger.warning(f"[Stats] 无效 patient_id: {patient_id}")
        return Stats7DaysOut(drugs=[])

    since = date.today() - timedelta(days=7)
    try:
        rows = (
            db.query(
                MedicationLog.drug_id,
                Drug.generic_name,
                MedicationSchedule.dosage_unit,
                # taken_dose 可能为 NULL（用户未填写），COALESCE 确保 SUM 不为 NULL
                func.coalesce(
                    func.sum(MedicationLog.taken_dose).filter(MedicationLog.status == "taken"),
                    0
                ).label("total_dose"),
                func.count(MedicationLog.id).filter(
                    MedicationLog.status == "missed"
                ).label("missed_count"),
            )
            .join(Drug, Drug.id == MedicationLog.drug_id)
            .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
            .filter(
                MedicationLog.patient_id == patient_id,
                *_date_range_filter(since),
            )
            .group_by(MedicationLog.drug_id, Drug.generic_name, MedicationSchedule.dosage_unit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Stats] 7天统计查询失败: patient_id={patient_id}, error={e}")
        return Stats7DaysOut(drugs=[])

    result = []
    for r in rows:
        try:
            result.append(DrugWeekStat(
                drug_id=r.drug_id,
                drug_name=r.generic_name or "未知药物",
                total_dose=_safe_float(r.total_dose),
                dosage_unit=r.dosage_unit or "mg",
                missed_count=_safe_int(r.missed_count),
            ))
        except Exception as e:
            logger.warning(f"[Stats] 7天统计行数据异常，跳过: drug_id={getattr(r, 'drug_id', '?')}, error={e}")
            continue

    return Stats7DaysOut(drugs=result)


def get_28days_stats(patient_id: int, db: Session) -> Stats28DaysOut:
    """
    获取近28天服药统计（含剂量偏差分析）。
    防御性处理：数据库异常时返回空结果，单行数据异常时跳过该行。
    """
    if not isinstance(patient_id, int) or patient_id <= 0:
        logger.warning(f"[Stats] 无效 patient_id: {patient_id}")
        return Stats28DaysOut(total_drug_types=0, total_taken_count=0, drugs=[])

    since = date.today() - timedelta(days=28)
    try:
        rows = (
            db.query(
                MedicationLog.drug_id,
                Drug.generic_name,
                MedicationSchedule.dosage_unit,
                MedicationSchedule.dosage.label("planned_single_dose"),
                func.coalesce(
                    func.sum(MedicationLog.taken_dose).filter(MedicationLog.status == "taken"),
                    0
                ).label("actual_dose"),
                func.count(MedicationLog.id).filter(
                    MedicationLog.status == "taken"
                ).label("taken_count"),
                func.count(MedicationLog.id).filter(
                    MedicationLog.status == "missed"
                ).label("missed_count"),
                # 计划总次数：只统计已过时间点的记录（taken + missed），不含未来 pending
                func.count(MedicationLog.id).filter(
                    MedicationLog.status.in_(["taken", "missed"])
                ).label("planned_count"),
            )
            .join(Drug, Drug.id == MedicationLog.drug_id)
            .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
            .filter(
                MedicationLog.patient_id == patient_id,
                *_date_range_filter(since),
            )
            .group_by(
                MedicationLog.drug_id,
                Drug.generic_name,
                MedicationSchedule.dosage_unit,
                MedicationSchedule.dosage,
            )
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Stats] 28天统计查询失败: patient_id={patient_id}, error={e}")
        return Stats28DaysOut(total_drug_types=0, total_taken_count=0, drugs=[])

    drug_stats = []
    total_taken = 0
    for r in rows:
        try:
            taken_count  = _safe_int(r.taken_count)
            missed_count = _safe_int(r.missed_count)
            actual_dose  = _safe_float(r.actual_dose)
            planned_single = _safe_float(r.planned_single_dose)
            planned_count  = _safe_int(r.planned_count)
            planned_dose   = planned_single * planned_count
            total_taken   += taken_count
            drug_stats.append(DrugDoseStat(
                drug_id=r.drug_id,
                drug_name=r.generic_name or "未知药物",
                dosage_unit=r.dosage_unit or "mg",
                planned_dose=planned_dose,
                actual_dose=actual_dose,
                taken_count=taken_count,
                missed_count=missed_count,
                dose_diff=round(actual_dose - planned_dose, 2),
            ))
        except Exception as e:
            logger.warning(f"[Stats] 28天统计行数据异常，跳过: drug_id={getattr(r, 'drug_id', '?')}, error={e}")
            continue

    return Stats28DaysOut(
        total_drug_types=len(drug_stats),
        total_taken_count=total_taken,
        drugs=drug_stats,
    )


def get_14days_daily(patient_id: int, db: Session) -> Stats14DaysOut:
    """
    获取近14天每日服药明细。
    防御性处理：数据库异常时返回空列表，单行数据异常时跳过。
    """
    if not isinstance(patient_id, int) or patient_id <= 0:
        logger.warning(f"[Stats] 无效 patient_id: {patient_id}")
        return Stats14DaysOut(records=[])

    since = date.today() - timedelta(days=14)
    try:
        rows = (
            db.query(
                func.date(MedicationLog.scheduled_time).label("log_date"),
                Drug.generic_name,
                MedicationLog.taken_dose,
                MedicationSchedule.dosage_unit,
                MedicationLog.status,
            )
            .join(Drug, Drug.id == MedicationLog.drug_id)
            .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
            .filter(
                MedicationLog.patient_id == patient_id,
                *_date_range_filter(since),
            )
            .order_by("log_date", Drug.generic_name)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Stats] 14天明细查询失败: patient_id={patient_id}, error={e}")
        return Stats14DaysOut(records=[])

    records = []
    for r in rows:
        try:
            records.append(DailyDrugRecord(
                date=r.log_date,
                drug_name=r.generic_name or "未知药物",
                dose=_safe_float(r.taken_dose),
                dosage_unit=r.dosage_unit or "mg",
                status=_safe_status(r.status),
            ))
        except Exception as e:
            logger.warning(f"[Stats] 14天明细行数据异常，跳过: error={e}")
            continue

    return Stats14DaysOut(records=records)


def get_lifetime_stats(patient_id: int, db: Session) -> StatsLifetimeOut:
    """
    获取长期服药史（首次/最近服药日期）。
    防御性处理：数据库异常时返回空列表。
    """
    if not isinstance(patient_id, int) or patient_id <= 0:
        logger.warning(f"[Stats] 无效 patient_id: {patient_id}")
        return StatsLifetimeOut(drugs=[])

    try:
        rows = (
            db.query(
                MedicationLog.drug_id,
                Drug.generic_name,
                func.min(func.date(MedicationLog.scheduled_time)).label("first_taken"),
                func.max(func.date(MedicationLog.scheduled_time)).label("last_taken"),
            )
            .join(Drug, Drug.id == MedicationLog.drug_id)
            .filter(
                MedicationLog.patient_id == patient_id,
                MedicationLog.status == "taken",
            )
            .group_by(MedicationLog.drug_id, Drug.generic_name)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"[Stats] 长期统计查询失败: patient_id={patient_id}, error={e}")
        return StatsLifetimeOut(drugs=[])

    result = []
    for r in rows:
        try:
            result.append(LifetimeDrugOut(
                drug_id=r.drug_id,
                drug_name=r.generic_name or "未知药物",
                first_taken=r.first_taken,
                last_taken=r.last_taken,
            ))
        except Exception as e:
            logger.warning(f"[Stats] 长期统计行数据异常，跳过: drug_id={getattr(r, 'drug_id', '?')}, error={e}")
            continue

    return StatsLifetimeOut(drugs=result)
