"""
漏服检测任务：每30分钟扫描超时未登记的 pending 记录，标记为 missed。
时间统一使用 UTC naive datetime，与数据库存储保持一致。
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.log import MedicationLog
from app.models.enums import MedicationStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# 单次批量更新上限，防止一次性更新过多记录导致长事务
_BATCH_SIZE = 500


@celery_app.task(
    name="app.tasks.miss_detect_task.check_missed_medications",
    max_retries=3,
    default_retry_delay=60,
)
def check_missed_medications():
    """
    扫描超时未登记的 pending 记录，批量标记为 missed。
    防御性处理：
    - 分批处理，避免长事务锁表
    - 数据库异常时回滚并重试
    - 阈值配置化，便于调整
    """
    db = SessionLocal()
    total_marked = 0

    try:
        threshold = datetime.utcnow() - timedelta(minutes=settings.MISSED_THRESHOLD_MINUTES)

        # 分批处理，避免一次性加载过多记录到内存
        while True:
            try:
                missed_logs = (
                    db.query(MedicationLog)
                      .filter(
                          MedicationLog.status == MedicationStatus.PENDING,
                          MedicationLog.scheduled_time < threshold,
                      )
                      .limit(_BATCH_SIZE)
                      .all()
                )
            except SQLAlchemyError as e:
                logger.error(f"[MissDetect] 查询 pending 记录失败: {e}")
                db.rollback()
                raise

            if not missed_logs:
                break

            batch_count = len(missed_logs)
            try:
                for log in missed_logs:
                    log.status = MedicationStatus.MISSED
                db.commit()
                total_marked += batch_count
                logger.debug(f"[MissDetect] 本批标记: {batch_count} 条")
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"[MissDetect] 批量更新失败: {e}")
                raise

            # 如果本批不足 BATCH_SIZE，说明已处理完毕
            if batch_count < _BATCH_SIZE:
                break

        logger.info(f"[MissDetect] 任务完成，共标记漏服: {total_marked} 条")
        return {"marked_missed": total_marked}

    except SQLAlchemyError as e:
        logger.error(f"[MissDetect] 任务失败（数据库异常）: {e}")
        raise
    except Exception as e:
        logger.error(f"[MissDetect] 任务失败（未知异常）: {e}")
        raise
    finally:
        db.close()
