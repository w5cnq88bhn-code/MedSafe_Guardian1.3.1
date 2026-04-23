"""
LSTM 依从性预测模型训练脚本
运行方式：python -m app.ml.train_lstm

特征说明（8维）：
  [0] adherence        当前时段是否按时服药（0/1）
  [1] weather_pressure 气压变化归一化值（-1~1）
  [2] is_holiday       是否法定节假日（0/1）
  [3] is_weekend       是否周末（0/1）
  [4] side_effect_flag 前一时段副作用标记（0/1）
  [5] slot_morning     时段独热 - 早
  [6] slot_afternoon   时段独热 - 中
  [7] slot_evening     时段独热 - 晚
"""
import os
import numpy as np
import tensorflow as tf
from app.ml.lstm_model import build_model, FEATURE_DIM, SEQ_LEN
from app.core.config import settings

# ── 随机种子（保证训练结果可复现）──
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
tf.random.set_seed(RANDOM_SEED)

# ── 超参数 ──
N_PATIENTS   = 500    # 模拟患者数
N_DAYS       = 180    # 每人历史天数
OUTPUT_LEN   = 9      # 输出长度（3天×3时段）
EPOCHS       = 30
BATCH_SIZE   = 64
MODEL_PATH   = settings.LSTM_MODEL_PATH


def _simulate_weather_pressure(n_days: int) -> np.ndarray:
    """随机游走模拟气压变化序列（归一化到 -1~1），每天3个时段气压相同。"""
    daily_pressure = np.zeros(n_days)
    daily_pressure[0] = np.random.uniform(-0.3, 0.3)
    for i in range(1, n_days):
        delta = np.random.normal(0, 0.15)
        daily_pressure[i] = np.clip(daily_pressure[i-1] + delta, -1.0, 1.0)
    # 每天3个时段气压相同
    return np.repeat(daily_pressure, 3)


def _simulate_holidays(n_days: int) -> np.ndarray:
    """模拟节假日标记：周末（每7天中的第6、7天）+ 约3%概率的法定节假日。"""
    holidays = np.zeros(n_days)
    for i in range(n_days):
        # 周末（每7天中的第6、7天）
        if i % 7 in (5, 6):
            holidays[i] = 1
        # 法定节假日（随机模拟，约3%概率）
        elif np.random.random() < 0.03:
            holidays[i] = 1
    return np.repeat(holidays, 3)


def generate_patient_data(n_patients: int, n_days: int):
    """
    生成多维特征模拟数据。

    漏服概率由多个因素叠加：
      基础 12%，晚间 +12%，午间 +8%，周末 +5%，
      气压骤降 +8%，节假日 -10%，连续漏服 +15%，副作用后 +12%
    """
    X_list, y_list = [], []

    for _ in range(n_patients):
        # 生成该患者的环境特征序列
        pressure_seq = _simulate_weather_pressure(n_days)   # 长度 n_days*3
        holiday_seq  = _simulate_holidays(n_days)            # 长度 n_days*3

        full_seq = []   # 每个元素为 FEATURE_DIM 维特征向量
        prev_missed = False
        prev_side_effect = False

        for day in range(n_days):
            is_weekend = (day % 7) in (5, 6)
            for slot_idx in range(3):  # 0=morning, 1=afternoon, 2=evening
                t = day * 3 + slot_idx
                pressure = float(pressure_seq[t])
                is_holiday = float(holiday_seq[t])

                # 计算漏服概率（多因素叠加）
                miss_rate = 0.12
                if slot_idx == 2:          miss_rate += 0.12   # 晚间
                if slot_idx == 1:          miss_rate += 0.08   # 午间
                if is_weekend:             miss_rate += 0.05   # 周末
                if pressure < -0.3:        miss_rate += 0.08   # 气压骤降
                if is_holiday:             miss_rate -= 0.10   # 节假日监督
                if prev_missed:            miss_rate += 0.15   # 连续漏服惯性
                if prev_side_effect:       miss_rate += 0.12   # 副作用后漏服
                miss_rate = np.clip(miss_rate, 0.02, 0.90)

                taken = 1 if np.random.random() > miss_rate else 0
                prev_missed = (taken == 0)

                # 副作用模拟：服药后有5%概率触发副作用（如降糖药低血糖）
                side_effect = 1 if (taken == 1 and np.random.random() < 0.05) else 0
                prev_side_effect = bool(side_effect)

                # 时段独热编码
                slot_morning   = 1.0 if slot_idx == 0 else 0.0
                slot_afternoon = 1.0 if slot_idx == 1 else 0.0
                slot_evening   = 1.0 if slot_idx == 2 else 0.0

                feature_vec = [
                    float(taken),          # dim-0: 依从性
                    pressure,              # dim-1: 气压变化
                    is_holiday,            # dim-2: 节假日
                    float(is_weekend),     # dim-3: 周末
                    float(side_effect),    # dim-4: 副作用标记
                    slot_morning,          # dim-5: 时段独热-早
                    slot_afternoon,        # dim-6: 时段独热-中
                    slot_evening,          # dim-7: 时段独热-晚
                ]
                full_seq.append(feature_vec)

        # 滑动窗口切分样本
        for start in range(len(full_seq) - SEQ_LEN - OUTPUT_LEN + 1):
            x = full_seq[start: start + SEQ_LEN]
            y_raw = full_seq[start + SEQ_LEN: start + SEQ_LEN + OUTPUT_LEN]
            # 标签：仅取 dim-0（依从性），转为漏服概率（0=按时服→标签0，1=漏服→标签1）
            y_miss = [1 - row[0] for row in y_raw]
            X_list.append(x)
            y_list.append(y_miss)

    X = np.array(X_list, dtype=np.float32)   # shape: (N, SEQ_LEN, FEATURE_DIM)
    y = np.array(y_list, dtype=np.float32)   # shape: (N, OUTPUT_LEN)
    return X, y


import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def train():
    logger.info(
        f"[Train] LSTM 训练启动: "
        f"患者数={N_PATIENTS}, 天数={N_DAYS}, 特征维度={FEATURE_DIM}, 随机种子={RANDOM_SEED}"
    )
    X, y = generate_patient_data(N_PATIENTS, N_DAYS)
    logger.info(f"[Train] 样本数：{len(X)}，X shape: {X.shape}，y shape: {y.shape}")

    split = int(len(X) * 0.85)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    model = build_model()
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=3),
    ]

    model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1,
    )

    model_dir = os.path.dirname(MODEL_PATH)
    if model_dir:
        os.makedirs(model_dir, exist_ok=True)
    model.save(MODEL_PATH)
    logger.info(f"[Train] 模型已保存至 {MODEL_PATH}")

    # 验证：构造一个有规律漏服的多维样本
    sample_seq = np.zeros((SEQ_LEN, FEATURE_DIM), dtype=np.float32)
    for i in range(SEQ_LEN):
        sample_seq[i, 0] = 1.0 if i < 35 else 0.0   # 最近7天有漏服
        sample_seq[i, 1] = -0.5 if i % 7 == 0 else 0.1  # 每周一气压骤降
        sample_seq[i, 2] = 0.0
        sample_seq[i, 3] = 1.0 if i % 7 in (5, 6) else 0.0
        sample_seq[i, 4] = 0.0
        slot = i % 3
        sample_seq[i, 5] = 1.0 if slot == 0 else 0.0
        sample_seq[i, 6] = 1.0 if slot == 1 else 0.0
        sample_seq[i, 7] = 1.0 if slot == 2 else 0.0

    x_test = sample_seq.reshape(1, SEQ_LEN, FEATURE_DIM)
    pred = model.predict(x_test, verbose=0)[0]
    logger.info(f"[Train] 示例预测（漏服概率）: {[round(float(p), 3) for p in pred]}")


if __name__ == "__main__":
    train()
