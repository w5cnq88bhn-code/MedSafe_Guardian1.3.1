import logging
import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.security import create_access_token
from app.models.patient import Patient

logger = logging.getLogger(__name__)

# 微信接口超时设置
WX_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# openid 最大长度限制，防止超长字符串写入数据库
_OPENID_MAX_LEN = 64
# code 最大长度限制，防止超长输入
_CODE_MAX_LEN = 512


def _validate_code(code: str) -> None:
    """校验 code 基本格式，防止超长或空值进入后续逻辑。"""
    if not code or not code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code 不能为空",
        )
    if len(code) > _CODE_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code 格式不合法",
        )


def _validate_openid(openid: str) -> str:
    """校验并清理 openid，防止空值或超长字符串写入数据库。"""
    if not openid or not openid.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取 openid",
        )
    openid = openid.strip()
    if len(openid) > _OPENID_MAX_LEN:
        logger.warning(f"[Auth] openid 超长，截断处理: len={len(openid)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="openid 格式不合法",
        )
    return openid


async def _fetch_openid_from_wechat(code: str) -> str:
    """
    调用微信接口换取 openid。
    独立封装便于单元测试 mock，同时集中处理网络异常。
    """
    if not settings.WX_APP_ID or not settings.WX_APP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="微信登录服务未配置，请联系管理员",
        )

    try:
        async with httpx.AsyncClient(timeout=WX_TIMEOUT) as client:
            resp = await client.get(settings.WX_LOGIN_URL, params={
                "appid":      settings.WX_APP_ID,
                "secret":     settings.WX_APP_SECRET,
                "js_code":    code,
                "grant_type": "authorization_code",
            })
    except httpx.TimeoutException:
        logger.error("[Auth] 微信接口请求超时")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="微信登录服务超时，请稍后重试",
        )
    except httpx.NetworkError as e:
        logger.error(f"[Auth] 微信接口网络错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信登录服务暂时不可用，请稍后重试",
        )
    except httpx.HTTPError as e:
        logger.error(f"[Auth] 微信接口请求异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信登录服务异常，请稍后重试",
        )

    # 防御性解析响应体
    try:
        wx_data = resp.json()
    except Exception:
        logger.error(f"[Auth] 微信接口响应解析失败: status={resp.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信登录服务响应异常",
        )

    if not isinstance(wx_data, dict):
        logger.error(f"[Auth] 微信接口响应格式异常: {wx_data!r}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信登录服务响应格式异常",
        )

    errcode = wx_data.get("errcode")
    if errcode is not None and errcode != 0:
        errmsg = wx_data.get("errmsg", "未知错误")
        logger.warning(f"[Auth] 微信登录失败: errcode={errcode}, errmsg={errmsg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"微信登录失败: {errmsg}",
        )

    openid = wx_data.get("openid")
    if not openid:
        logger.error(f"[Auth] 微信接口未返回 openid: {wx_data!r}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取 openid",
        )

    return openid


def _get_or_create_user(openid: str, db: Session) -> tuple[Patient, bool]:
    """
    查找或创建用户，处理并发竞争条件。
    返回 (user, is_new) 元组。
    """
    # 先尝试查找已有用户
    try:
        user = db.query(Patient).filter(Patient.openid == openid).first()
    except OperationalError as e:
        logger.error(f"[Auth] 数据库查询失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用，请稍后重试",
        )

    if user:
        return user, False

    # 用户不存在，尝试创建
    # 并发场景下两个请求可能同时通过上面的 first() 查询为空，
    # 都尝试插入时会触发 openid 唯一约束冲突，捕获后重新查询即可。
    try:
        user = Patient(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[Auth] 新用户注册: openid={openid[:8]}...")
        return user, True
    except IntegrityError:
        # 并发插入冲突，回滚后重新查询
        db.rollback()
        logger.info(f"[Auth] 并发注册冲突，重新查询: openid={openid[:8]}...")
        user = db.query(Patient).filter(Patient.openid == openid).first()
        if not user:
            # 理论上不会走到这里，保险起见
            logger.error(f"[Auth] 并发冲突后仍找不到用户: openid={openid[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="用户创建失败，请重试",
            )
        return user, False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[Auth] 用户创建数据库异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户创建失败，请重试",
        )


async def wechat_login(code: str, db: Session) -> dict:
    """
    用微信 code 换取 openid，自动注册新用户，返回 JWT token。
    调试模式（DEBUG=true 且 code 以 debug_ 或 demo_ 开头）：直接用 code 作为 openid，跳过微信接口。
    """
    # 基础输入校验
    _validate_code(code)

    # 调试模式：code 直接作为 openid，跳过微信接口
    if settings.DEBUG and (code.startswith("debug_") or code.startswith("demo_")):
        openid = code
        logger.debug(f"[Auth] 调试模式登录: openid={openid}")
    else:
        raw_openid = await _fetch_openid_from_wechat(code)
        openid = _validate_openid(raw_openid)

    user, is_new = _get_or_create_user(openid, db)

    try:
        token = create_access_token({"user_id": user.id, "openid": openid})
    except Exception as e:
        logger.error(f"[Auth] Token 生成失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败，请重试",
        )

    return {
        "token":       token,
        "openid":      openid,
        "user_id":     user.id,
        "is_new_user": is_new,
    }
