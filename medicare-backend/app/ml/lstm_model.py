"""
LSTM 依从性预测模型 —— 多源异构数据时序预测
==============================================
特征工程（多维输入，共 8 维）：
  dim-0  adherence        : 当前时段是否按时服药（0/1）
  dim-1  weather_pressure : 气压变化归一化值（气压骤降影响血压/关节痛，导致漏服）
  dim-2  is_holiday       : 是否节假日（子女回家监督，依从性提升）
  dim-3  is_weekend       : 是否周末（生活规律改变，漏服率略高）
  dim-4  side_effect_flag : 前一时段是否触发副作用标记（如降糖药后低血糖导致后续漏服）
  dim-5  time_slot_morning: 时段独热 - 早
  dim-6  time_slot_afternoon: 时段独热 - 中
  dim-7  time_slot_evening: 时段独热 - 晚

输入 shape : (batch, 42, 8)   # 14天 × 3时段，每时段8维特征
输出 shape : (batch, 9)       # 未来3天 × 3时段漏服概率

多源异构数据融合策略：
  - 行为序列（依从性0/1）：捕捉个体用药习惯的时序规律
  - 环境特征（气压/节假日/周末）：引入外部上下文，提升跨场景泛化
  - 药物副作用特征：建模"副作用→漏服"的因果链，实现医学可解释性
  - 时段独热编码：显式告知模型当前时段，避免位置信息隐式混淆

Fallback 机制：模型文件不存在或推理失败时，自动切换线性估算，系统不中断。
"""
import os
import numpy as np
from app.core.config import settings

# 特征维度常量
FEATURE_DIM = 8
SEQ_LEN = 42  # 14天 × 3时段

_model = None  # 全局模型缓存


def _load_model():
    global _model
    if _model is not None:
        return _model
    if not os.path.exists(settings.LSTM_MODEL_PATH):
        return None
    try:
        import tensorflow as tf
        _model = tf.keras.models.load_model(settings.LSTM_MODEL_PATH)
        return _model
    except Exception as e:
        print(f"[LSTM] 模型加载失败: {e}")
        return None


def _fallback_predict(sequence: list) -> list:
    """
    Fallback：基于最近7天漏服率线性估算。
    仅使用 dim-0（依从性）维度，与旧版兼容。
    """
    # 兼容一维列表（旧格式）和二维列表（新格式）
    if sequence and isinstance(sequence[0], (list, tuple, np.ndarray)):
        recent = [row[0] for row in sequence[-21:]]
    else:
        recent = sequence[-21:]

    miss_rate = 1 - (sum(recent) / len(recent)) if recent else 0.3
    slot_weights = [1.0, 1.1, 1.3]
    probabilities = []
    for day_offset in range(1, 4):
        for weight in slot_weights:
            prob = min(miss_rate * weight * (1 + 0.03 * day_offset), 0.99)
            probabilities.append(round(prob, 4))
    return probabilities


def predict_adherence(sequence: list) -> list:
    """
    主预测入口：优先使用多维 LSTM，失败则 fallback。

    sequence: 长度42的列表，每个元素为长度8的特征向量，
              或长度42的0/1列表（旧格式，自动升维）。
    返回: 9个漏服概率值（未来3天×3时段）
    """
    model = _load_model()
    if model is None:
        return _fallback_predict(sequence)

    try:
        # 兼容旧格式（一维0/1序列）
        if sequence and not isinstance(sequence[0], (list, tuple, np.ndarray)):
            # 旧格式升维：仅有依从性维度，其余特征填0
            seq_array = np.zeros((SEQ_LEN, FEATURE_DIM), dtype=np.float32)
            for i, v in enumerate(sequence[:SEQ_LEN]):
                seq_array[i, 0] = float(v)
        else:
            seq_array = np.array(sequence, dtype=np.float32)
            if seq_array.shape != (SEQ_LEN, FEATURE_DIM):
                seq_array = np.zeros((SEQ_LEN, FEATURE_DIM), dtype=np.float32)
                for i, row in enumerate(sequence[:SEQ_LEN]):
                    for j, v in enumerate(row[:FEATURE_DIM]):
                        seq_array[i, j] = float(v)

        x = seq_array.reshape(1, SEQ_LEN, FEATURE_DIM)
        preds = model.predict(x, verbose=0)[0]
        return [round(float(p), 4) for p in preds]
    except Exception as e:
        print(f"[LSTM] 推理失败，使用 fallback: {e}")
        return _fallback_predict(sequence)


def build_model():
    """
    构建多维特征融合 LSTM 模型结构。

    架构设计：
      - 双层 LSTM 捕捉短期（层1）和长期（层2）时序依赖
      - Dropout 防止过拟合（训练数据为模拟数据，正则化尤为重要）
      - Dense(9, sigmoid) 输出9个独立漏服概率（多标签二分类）
      - 输入维度从1扩展至8，融合行为/环境/药物副作用多源特征
    """
    import tensorflow as tf
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(SEQ_LEN, FEATURE_DIM)),
        tf.keras.layers.LSTM(64, return_sequences=True),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(9, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["mae"])
    return model
