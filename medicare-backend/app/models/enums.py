"""
项目公共枚举定义
统一管理所有有限取值的字段，避免魔法字符串散落在各处
"""
import enum


class SeverityLevel(str, enum.Enum):
    """药物相互作用严重程度"""
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class TimeSlot(str, enum.Enum):
    """服药时段"""
    MORNING   = "morning"
    AFTERNOON = "afternoon"
    EVENING   = "evening"


class MedicationStatus(str, enum.Enum):
    """服药记录状态"""
    PENDING = "pending"
    TAKEN   = "taken"
    MISSED  = "missed"
