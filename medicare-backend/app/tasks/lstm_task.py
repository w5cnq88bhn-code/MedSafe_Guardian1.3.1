"""
LSTM 依从性预测任务：每日凌晨2点为所有活跃患者生成未来3天预测。

多维特征融合：
  - 依从性序列（行为特征）
  - 气压变化（环境特征，气压骤降影响血压/关节痛导致漏服）
  - 节假日/周末标记（社会特征，子女回家监督依从性变高）
  - 副作用标记（药物特征，如降糖药后低血糖导致后续漏服）
  - 时段独热编码（时间特征）
"""
import logging
from datetime import date, timedelta
import numpy as np
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.log import MedicationLog
from app.models.schedule import MedicationSchedule
from app.models.prediction import AdherencePrediction
from app.models.enums import MedicationStatus, TimeSlot
from app.ml.lstm_model import predict_adherence, FEATURE_DIM

logger = logging.getLogger(__name__)

TIME_SLOTS = [TimeSlot.MORNING, TimeSlot.AFTERNOON, TimeSlot.EVENING]
SEQUENCE_DAYS = 14   # 输入序列天数
SEQ_LEN       = SEQUENCE_DAYS * 3  # = 42

# 节假日列表（简化：仅列出固定节假日月日，实际可接入节假日API）
_FIXED_HOLIDAYS = {(1,1),(1,2),(1,3),(2,1),(2,2),(2,3),(2,4),(2,5),(2,6),(2,7),
                   (4,4),(4,5),(5,1),(5,2),(5,3),(6,1),(9,1),(10,1),(10,2),(10,3),
                   (10,4),(10,5),(10,6),(10,7)}


def _is_holiday(d: date) -> float:
    """判断是否节假日（法定节假日或周末）"""
    if d.weekday() >= 5:  # 周六=5, 周日=6
        return 1.0
    if (d.month, d.day) in _FIXED_HOLIDAYS:
        return 1.0
    return 0.0


def _get_multifeature_sequence(patient_id: int, db) -> list:
    """
    提取过去 SEQUENCE_DAYS 天的多维特征序列。
    返回：长度42的列表，每个元素为8维特征向量。

    特征维度：
      [0] adherence        : 当前时段是否按时服药（0/1）
      [1] weather_pressure : 气压变化（此处用伪随机模拟，生产环境可接入气象API）
      [2] is_holiday       : 是否节假日（0/1）
      [3] is_weekend       : 是否周末（0/1）
      [4] side_effect_flag : 前一时段副作用标记（0/1）
      [5] slot_morning     : 时段独热-早
      [6] slot_afternoon   : 时段独热-中
      [7] slot_evening     : 时段独热-晚
    """
    today = date.today()
    since = today - timedelta(days=SEQUENCE_DAYS - 1)

    rows = (
        db.query(MedicationLog, MedicationSchedule)
          .join(MedicationSchedule, MedicationSchedule.id == MedicationLog.schedule_id)
          .filter(
              MedicationLog.patient_id == patient_id,
              MedicationLog.scheduled_time >= since,
          )
          .all()
    )

    # 按 (date, time_of_day) 聚合依从性
    slot_map: dict = {}
    for log, sched in rows:
        key = (log.scheduled_time.date(), sched.time_of_day)
        if key not in slot_map:
            slot_map[key] = 0
        if log.status == MedicationStatus.TAKEN:
            slot_map[key] = 1

    sequence = []
    prev_side_effect = 0.0

    for day_offset in range(SEQUENCE_DAYS - 1, -1, -1):
        d = today - timedelta(days=day_offset)
        is_holiday = _is_holiday(d)
        is_weekend = 1.0 if d.weekday() >= 5 else 0.0
        # 气压变化：生产环境接入气象API；此处用日期哈希模拟确定性伪随机
        pressure = float(np.sin(d.toordinal() * 0.3) * 0.5)

        for slot_idx, slot in enumerate(TIME_SLOTS):
            adherence = float(slot_map.get((d, slot), 0))
            # 副作用标记：服药后有概率触发（此处用历史漏服模式推断）
            # 生产环境可接入药物副作用数据库，对特定药物（如降糖药）标记
            side_effect = prev_side_effect
            # 若本时段已服，副作用概率重置（简化模型）
            prev_side_effect = 0.05 if adherence == 1.0 else 0.0

            slot_morning   = 1.0 if slot_idx == 0 else 0.0
            slot_afternoon = 1.0 if slot_idx == 1 else 0.0
            slot_evening   = 1.0 if slot_idx == 2 else 0.0

            sequence.append([
                adherence,
                pressure,
                is_holiday,
                is_weekend,
                side_effect,
                slot_morning,
                slot_afternoon,
                slot_evening,
            ])

    return sequence  # 长度42，每元素8维


def _fallback_predict(sequence: list) -> list[float]:
    """
    LSTM 不可用时的 fallback：基于最近7天漏服率线性估算。
    兼容多维特征序列（取 dim-0 依从性）和旧格式一维序列。
    """
    if sequence and isinstance(sequence[0], (list, tuple, np.ndarray)):
        recent = [row[0] for row in sequence[-21:]]
    else:
        recent = sequence[-21:]
    miss_rate = 1 - (sum(recent) / len(recent)) if recent else 0.3
    slot_weights = [1.0, 1.1, 1.3]
    result = []
    for day_offset in range(1, 4):
        for weight in slot_weights:
            prob = min(miss_rate * weight * (1 + 0.03 * day_offset), 0.99)
            result.append(round(prob, 4))
    return result


@celery_app.task(
    name="app.tasks.lstm_task.run_lstm_predictions",
    max_retries=2,
    default_retry_delay=300,
)
def run_lstm_predictions():
    db = SessionLocal()
    try:
        today = date.today()
        active_since = today - timedelta(days=30)

        active_patient_ids = (
            db.query(MedicationLog.patient_id)
              .filter(MedicationLog.scheduled_time >= active_since)
              .distinct()
              .all()
        )

        processed = 0
        failed    = 0

        for (patient_id,) in active_patient_ids:
            try:
                sequence = _get_multifeature_sequence(patient_id, db)

                # 数据不足时左侧补零向量（假设历史无记录=漏服，其余特征为0）
                if len(sequence) < SEQ_LEN:
                    padding = [[0.0] * FEATURE_DIM] * (SEQ_LEN - len(sequence))
                    sequence = padding + sequence

                # LSTM 推理，失败时使用 fallback
                try:
                    probabilities = predict_adherence(sequence)
                    if len(probabilities) != 9:
                        raise ValueError(f"预测结果长度异常: {len(probabilities)}")
                except Exception as e:
                    logger.warning(f"[LSTM] patient_id={patient_id} 推理失败，使用 fallback: {e}")
                    probabilities = _fallback_predict(sequence)

                # 写入数据库（upsert）
                for i, (day_offset, slot) in enumerate(
                    [(d, s) for d in range(1, 4) for s in TIME_SLOTS]
                ):
                    prob = float(probabilities[i])

                    existing = db.query(AdherencePrediction).filter(
                        AdherencePrediction.patient_id        == patient_id,
                        AdherencePrediction.prediction_date   == today,
                        AdherencePrediction.target_day_offset == day_offset,
                        AdherencePrediction.target_time_slot  == slot,
                    ).first()

                    if existing:
                        existing.miss_probability = prob
                    else:
                        db.add(AdherencePrediction(
                            patient_id        = patient_id,
                            prediction_date   = today,
                            target_day_offset = day_offset,
                            target_time_slot  = slot,
                            miss_probability  = prob,
                        ))

                db.commit()
                processed += 1

            except Exception as e:
                db.rollback()
                logger.error(f"[LSTM] patient_id={patient_id} 处理失败: {e}")
                failed += 1
                continue  # 单个患者失败不影响其他患者

        logger.info(f"[LSTM] 预测完成: 成功={processed}, 失败={failed}")
        return {"processed": processed, "failed": failed}

    except Exception as e:
        logger.error(f"[LSTM] 任务整体失败: {e}")
        raise
    finally:
        db.close()
