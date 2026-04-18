"""
LSTM 依从性预测模型预训练脚本 —— 多源异构数据时序预测
=======================================================
运行方式：python -m app.ml.train_lstm

多维特征说明（8维）：
  [0] adherence        : 当前时段是否按时服药（0/1）
  [1] weather_pressure : 气压变化归一化值（-1~1）
                         气压骤降（<-0.3）模拟阴雨天气，影响血压/关节痛，漏服率+8%
  [2] is_holiday       : 是否法定节假日（0/1）
                         节假日子女回家监督，依从性提升，漏服率-10%
  [3] is_weekend       : 是否周末（0/1）
                         周末生活规律改变，漏服率+5%
  [4] side_effect_flag : 前一时段副作用标记（0/1）
                         模拟降糖药后低血糖等副作用导致后续时段漏服率+12%
  [5] slot_morning     : 时段独热 - 早（0/1）
  [6] slot_afternoon   : 时段独热 - 中（0/1）
  [7] slot_evening     : 时段独热 - 晚（0/1）

多源异构数据融合的学术意义：
  传统依从性预测仅使用行为序列（0/1），本模型引入：
  1. 环境数据（气压）：气象因素对慢病患者生理状态的影响已有临床文献支持
  2. 社会因素（节假日）：家庭监督对老年患者依从性的正向干预
  3. 药物副作用特征：建模"副作用→漏服"因果链，提升医学可解释性
  上述多源异构特征的引入，使模型从单一行为预测升级为多因素时序预测。
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
    """
    模拟气压变化序列（归一化到 -1~1）。
    使用随机游走模拟真实气压波动，每天3个时段气压相同。
    气压骤降（<-0.3）对应阴雨/低压天气，影响血压和关节痛。
    """
    daily_pressure = np.zeros(n_days)
    daily_pressure[0] = np.random.uniform(-0.3, 0.3)
    for i in range(1, n_days):
        delta = np.random.normal(0, 0.15)
        daily_pressure[i] = np.clip(daily_pressure[i-1] + delta, -1.0, 1.0)
    # 每天3个时段气压相同
    return np.repeat(daily_pressure, 3)


def _simulate_holidays(n_days: int) -> np.ndarray:
    """
    模拟节假日标记。
    简化模型：每7天中约有2天为周末，每年约有11天法定节假日（约3%概率）。
    节假日子女回家监督，依从性提升。
    """
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
    生成多维特征模拟服药依从性数据。

    漏服模式（多因素叠加）：
      - 基础漏服率 12%
      - 晚间漏服率更高（+12%）：夜间忘记服药
      - 午间漏服率略高（+8%）：外出就餐时忘记
      - 连续漏服惯性（+15%）：前一时段漏服则当前漏服概率增加
      - 周末漏服率略高（+5%）：生活规律改变
      - 气压骤降（+8%）：天气影响生理状态
      - 节假日漏服率降低（-10%）：子女监督
      - 副作用触发后漏服率升高（+12%）：如低血糖后不敢继续服药
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
        f"[Train] 多维特征融合 LSTM 训练启动\n"
        f"  患者数={N_PATIENTS}, 天数={N_DAYS}, 随机种子={RANDOM_SEED}\n"
        f"  特征维度={FEATURE_DIM} (依从性+气压+节假日+周末+副作用+时段独热×3)\n"
        f"  输入shape=(batch, {SEQ_LEN}, {FEATURE_DIM}), 输出shape=(batch, {OUTPUT_LEN})"
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
