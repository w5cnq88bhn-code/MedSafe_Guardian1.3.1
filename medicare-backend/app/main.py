import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import engine, SessionLocal
from app.routers import auth, drugs, logs, statistics, predictions, reports

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时同步图谱数据
    try:
        from app.services.graph_sync import sync_all
        db = SessionLocal()
        try:
            sync_all(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[Startup] 图谱同步失败（不影响主服务）: {e}")
    yield
    try:
        from app.services.graph_service import close_driver
        close_driver()
    except Exception:
        pass
    try:
        engine.dispose()
    except Exception as e:
        logger.warning(f"[Shutdown] 释放数据库连接池时出错: {e}")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    # 生产环境关闭 Swagger UI 和 ReDoc，避免暴露接口文档
    docs_url  = "/docs"   if settings.DEBUG else None,
    redoc_url = "/redoc"  if settings.DEBUG else None,
    lifespan  = lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # DEBUG 模式返回详细错误信息，生产环境返回通用消息，避免泄露敏感信息
    if settings.DEBUG:
        message = str(exc)
    else:
        message = "服务器内部错误"
        logger.error(
            f"[500] {request.method} {request.url.path} - {type(exc).__name__}: {exc}",
            exc_info=True,
        )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": message, "data": None},
    )


PREFIX = "/api/v1"
for router_module in [auth, drugs, logs, statistics, predictions, reports]:
    app.include_router(router_module.router, prefix=PREFIX)


@app.get("/health")
def health():
    return {"status": "ok"}
