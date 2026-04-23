from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # 每次从池中获取连接时检测存活
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,        # 1小时回收连接，防止数据库超时断开
    echo=settings.DEBUG,      # 仅在调试时打印 SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


def get_db():
    """
    FastAPI 依赖注入，提供数据库会话。
    commit 由业务层（router/service）显式调用，此处只负责异常回滚和关闭。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()   # 发生异常时回滚，避免脏数据
        raise           # 重新抛出，让上层处理
    finally:
        db.close()
