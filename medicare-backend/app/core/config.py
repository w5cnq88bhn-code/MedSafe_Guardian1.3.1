from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """MediCare 后端配置，优先从环境变量读取，其次从 .env 文件加载"""

    # 应用
    APP_NAME: str = "药安守护 API"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # 数据库 - 强制从环境变量获取，不设默认值
    DATABASE_URL: str = Field(..., description="PostgreSQL 连接串")

    # Redis
    REDIS_URL: str = Field("redis://localhost:6379/0")

    # JWT
    SECRET_KEY: str = Field(..., min_length=32, description="JWT 签名密钥，生产环境必须设置")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # 微信小程序
    WX_APP_ID: str = Field(default="")
    WX_APP_SECRET: str = Field(default="")
    WX_LOGIN_URL: str = "https://api.weixin.qq.com/sns/jscode2session"
    WX_TOKEN_URL: str = "https://api.weixin.qq.com/cgi-bin/token"
    WX_SUBSCRIBE_MSG_URL: str = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"

    # 微信订阅消息模板ID（需在微信公众平台申请）
    WX_TEMPLATE_REMINDER: str = ""   # 服药提醒模板
    WX_TEMPLATE_MISSED: str = ""     # 漏服提醒模板

    # ML 模型路径
    LSTM_MODEL_PATH: str = "/app/models/lstm_adherence.h5"

    # 漏服判定延迟（分钟）
    MISSED_THRESHOLD_MINUTES: int = 30

    # Celery
    CELERY_BROKER_URL: Optional[str] = None    # 若不设置则使用 REDIS_URL
    CELERY_RESULT_BACKEND: Optional[str] = None

    @field_validator("WX_APP_ID", "WX_APP_SECRET", mode="after")
    @classmethod
    def check_wechat_config(cls, v: str, info) -> str:
        if not info.data.get("DEBUG") and not v:
            raise ValueError(f"{info.field_name} must be set in production mode")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def check_secret_key(cls, v: str) -> str:
        if v in ("change-me-in-production-use-openssl-rand-hex-32", ""):
            raise ValueError(
                "SECRET_KEY is too weak or empty, please set a strong key in environment"
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # 忽略 .env 中多余的字段（如 POSTGRES_DB/USER/PASSWORD 供 docker-compose 使用）


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
