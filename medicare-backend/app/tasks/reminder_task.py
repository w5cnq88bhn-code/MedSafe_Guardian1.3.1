"""
服药提醒任务：每5分钟检查未来10分钟内有服药计划的患者，发送订阅消息。

幂等性保证：
  用 Redis key "reminder:{schedule_id}:{date}" 记录已发送状态，TTL=2小时。
  同一计划同一天只发送一次，避免任务窗口重叠导致重复推送。

Redis 连接池：
  模块级单例，避免每次任务创建新连接。
"""
import logging
import httpx
import redis as redis_client
from datetime import datetime, timedelta, date
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.schedule import MedicationSchedule
from app.models.patient import Patient
from app.models.drug import Drug
from app.models.log import MedicationLog
from app.models.enums import MedicationStatus

logger = logging.getLogger(__name__)

WX_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# 模块级 Redis 连接池单例，避免每次任务重新建连
_redis: redis_client.Redis | None = None


def _get_redis() -> redis_client.Redis:
    global _redis
    if _redis is None:
        _redis = redis_client.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _reminder_key(schedule_id: int, day: date) -> str:
    """Redis 幂等锁 key，格式：reminder:{schedule_id}:{YYYY-MM-DD}"""
    return f"reminder:{schedule_id}:{day.isoformat()}"


def _is_already_sent(schedule_id: int, day: date) -> bool:
    """检查该计划今天是否已发送过提醒"""
    try:
        return bool(_get_redis().exists(_reminder_key(schedule_id, day)))
    except Exception as e:
        logger.warning(f"[Reminder] Redis 检查失败，默认允许发送: {e}")
        return False  # Redis 不可用时宁可重发，不漏发


def _mark_sent(schedule_id: int, day: date) -> None:
    """标记该计划今天已发送，TTL=2小时（覆盖当天所有可能的重复窗口）"""
    try:
        _get_redis().setex(_reminder_key(schedule_id, day), 7200, "1")
    except Exception as e:
        logger.warning(f"[Reminder] Redis 写入失败: {e}")


def _get_access_token_sync() -> str:
    """同步获取微信 access_token，优先读 Redis 缓存"""
    r = _get_redis()
    cached = r.get("wx:access_token")
    if cached:
        return cached

    resp = httpx.get(settings.WX_TOKEN_URL, params={
        "grant_type": "client_credential",
        "appid":      settings.WX_APP_ID,
        "secret":     settings.WX_APP_SECRET,
    }, timeout=WX_TIMEOUT)
    data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        raise RuntimeError(f"获取 access_token 失败: {data}")

    token = data.get("access_token", "")
    if not token:
        raise RuntimeError("微信接口未返回 access_token")

    r.setex("wx:access_token", data.get("expires_in", 7200) - 60, token)
    return token


def _send_reminder_sync(openid: str, drug_name: str, time_str: str) -> bool:
    """同步发送服药提醒，返回是否成功"""
    if not settings.WX_TEMPLATE_REMINDER:
        return False
    try:
        token = _get_access_token_sync()
        resp = httpx.post(
            settings.WX_SUBSCRIBE_MSG_URL,
            params={"access_token": token},
            json={
                "touser":      openid,
                "template_id": settings.WX_TEMPLATE_REMINDER,
                "page":        "pages/patient/today/index",
                "data": {
                    "thing1": {"value": drug_name[:20]},
                    "time2":  {"value": time_str},
                },
            },
            timeout=WX_TIMEOUT,
        )
        result = resp.json()
        if result.get("errcode", 0) != 0:
            logger.warning(f"[Reminder] 推送失败: {result}")
            return False
        return True
    except Exception as e:
        logger.error(f"[Reminder] 推送异常: {e}")
        return False


@celery_app.task(
    name="app.tasks.reminder_task.send_scheduled_reminders",
    max_retries=2,
    default_retry_delay=30,
)
def send_scheduled_reminders():
    db = SessionLocal()
    try:
        now        = datetime.utcnow()
        window_end = now + timedelta(minutes=10)
        today      = date.today()

        schedules = (
            db.query(MedicationSchedule, Patient, Drug)
              .join(Patient, Patient.id == MedicationSchedule.patient_id)
              .join(Drug, Drug.id == MedicationSchedule.drug_id)
              .filter(
                  MedicationSchedule.is_active == True,
                  MedicationSchedule.start_date <= today,
                  (MedicationSchedule.end_date == None) | (MedicationSchedule.end_date >= today),
              )
              .all()
        )

        sent = 0
        for sched, patient, drug in schedules:
            sched_dt = datetime.combine(today, sched.time_point)
            if not (now <= sched_dt <= window_end):
                continue

            # openid 为空则跳过（患者未绑定微信）
            if not patient.openid:
                continue

            # 幂等检查：今天已发送过则跳过
            if _is_already_sent(sched.id, today):
                continue

            # 已服则跳过
            existing_log = db.query(MedicationLog).filter(
                MedicationLog.schedule_id == sched.id,
                MedicationLog.scheduled_time == sched_dt,
            ).first()
            if existing_log and existing_log.status == MedicationStatus.TAKEN:
                continue

            if _send_reminder_sync(
                openid=patient.openid,
                drug_name=drug.generic_name,
                time_str=sched.time_point.strftime("%H:%M"),
            ):
                _mark_sent(sched.id, today)  # 发送成功后才标记，避免失败时漏发
                sent += 1

        logger.debug(f"[Reminder] 本轮发送: {sent} 条")
        return {"reminders_sent": sent}
    except Exception as e:
        logger.error(f"[Reminder] 任务失败: {e}")
        raise
    finally:
        db.close()
