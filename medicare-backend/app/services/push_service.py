"""
微信订阅消息推送服务
access_token 缓存于 Redis，有效期 2 小时。
注意：模板字段名（thing1/time2 等）需与微信公众平台申请的模板保持一致。
"""
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

ACCESS_TOKEN_KEY = "wx:access_token"
# 微信接口超时设置
WX_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
# openid 最大长度，防止超长字符串传入微信接口
_OPENID_MAX_LEN = 64
# 模板字段值最大长度（微信限制 20 字）
_TEMPLATE_VALUE_MAX_LEN = 20

# 延迟初始化 Redis 客户端，避免服务启动时 Redis 未就绪导致启动失败
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis as redis_client
        _redis = redis_client.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _validate_openid(openid: str) -> bool:
    """校验 openid 基本格式，防止空值或超长字符串传入微信接口。"""
    if not openid or not isinstance(openid, str):
        return False
    if len(openid.strip()) == 0:
        return False
    if len(openid) > _OPENID_MAX_LEN:
        logger.warning(f"[Push] openid 超长，拒绝推送: len={len(openid)}")
        return False
    return True


def _safe_template_value(value: str, max_len: int = _TEMPLATE_VALUE_MAX_LEN) -> str:
    """截断模板字段值，防止超出微信限制导致推送失败。"""
    if not value:
        return ""
    return str(value)[:max_len]


async def _get_access_token() -> str:
    """
    获取微信 access_token，优先从 Redis 缓存读取。
    若微信接口返回错误，抛出异常而不缓存无效 token，
    避免空 token 被缓存导致后续 2 小时内所有推送失败。
    """
    # 尝试读取缓存
    try:
        cached = _get_redis().get(ACCESS_TOKEN_KEY)
        if cached:
            return cached
    except Exception as e:
        logger.warning(f"[Push] Redis 读取失败，跳过缓存直接请求微信接口: {e}")

    # 校验微信配置
    if not settings.WX_APP_ID or not settings.WX_APP_SECRET:
        raise RuntimeError("微信 AppID 或 AppSecret 未配置，无法获取 access_token")

    # 请求微信接口
    try:
        async with httpx.AsyncClient(timeout=WX_TIMEOUT) as client:
            resp = await client.get(settings.WX_TOKEN_URL, params={
                "grant_type": "client_credential",
                "appid":      settings.WX_APP_ID,
                "secret":     settings.WX_APP_SECRET,
            })
    except httpx.TimeoutException:
        raise RuntimeError("获取微信 access_token 超时")
    except httpx.NetworkError as e:
        raise RuntimeError(f"获取微信 access_token 网络错误: {e}")

    # 解析响应
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"微信接口响应解析失败: status={resp.status_code}")

    if not isinstance(data, dict):
        raise RuntimeError(f"微信接口响应格式异常: {data!r}")

    # 微信接口返回错误时不缓存，直接抛出
    errcode = data.get("errcode")
    if errcode is not None and errcode != 0:
        raise RuntimeError(
            f"获取微信 access_token 失败: errcode={errcode}, errmsg={data.get('errmsg')}"
        )

    token = data.get("access_token", "")
    if not token:
        raise RuntimeError("微信接口未返回 access_token，请检查 AppID 和 AppSecret 配置")

    # 写入缓存，提前 60 秒过期避免边界问题
    expires_in = data.get("expires_in", 7200)
    if not isinstance(expires_in, int) or expires_in <= 60:
        expires_in = 7200
    try:
        _get_redis().setex(ACCESS_TOKEN_KEY, expires_in - 60, token)
    except Exception as e:
        logger.warning(f"[Push] Redis 写入失败，token 本次不缓存: {e}")

    return token


async def _send_subscribe_message(
    openid: str,
    template_id: str,
    data: dict,
    page: str = "",
) -> bool:
    """
    发送微信订阅消息，返回是否成功。
    防御性处理：
    - openid 格式校验
    - template_id 空值检查
    - access_token 获取失败时返回 False 而非抛出异常
    - 微信接口响应解析异常处理
    - errcode 43101（用户未订阅）单独处理，不记录为错误
    """
    # 基础校验
    if not _validate_openid(openid):
        logger.warning(f"[Push] openid 格式无效，跳过推送")
        return False

    if not template_id:
        logger.debug("[Push] 模板ID未配置，跳过推送")
        return False

    if not data or not isinstance(data, dict):
        logger.warning("[Push] 模板数据为空，跳过推送")
        return False

    # 获取 access_token
    try:
        token = await _get_access_token()
    except RuntimeError as e:
        logger.error(f"[Push] 获取 access_token 失败: {e}")
        return False

    payload = {
        "touser":      openid,
        "template_id": template_id,
        "page":        page or "",
        "data":        data,
    }

    # 发送推送
    try:
        async with httpx.AsyncClient(timeout=WX_TIMEOUT) as client:
            resp = await client.post(
                settings.WX_SUBSCRIBE_MSG_URL,
                params={"access_token": token},
                json=payload,
            )
    except httpx.TimeoutException:
        logger.error(f"[Push] 推送请求超时: openid={openid[:8]}...")
        return False
    except httpx.NetworkError as e:
        logger.error(f"[Push] 推送网络错误: {e}")
        return False

    # 解析响应
    try:
        result = resp.json()
    except Exception:
        logger.error(f"[Push] 推送响应解析失败: status={resp.status_code}")
        return False

    errcode = result.get("errcode", 0)
    if errcode == 0:
        logger.info(f"[Push] 订阅消息发送成功: openid={openid[:8]}...")
        return True

    # 43101: 用户未订阅该消息，属于正常情况，降级为 debug
    if errcode == 43101:
        logger.debug(f"[Push] 用户未订阅消息: openid={openid[:8]}...")
        return False

    # 40001/40003: access_token 失效，清除缓存让下次重新获取
    if errcode in (40001, 40003):
        logger.warning(f"[Push] access_token 失效，清除缓存: errcode={errcode}")
        try:
            _get_redis().delete(ACCESS_TOKEN_KEY)
        except Exception:
            pass
        return False

    logger.warning(
        f"[Push] 订阅消息发送失败: openid={openid[:8]}..., "
        f"errcode={errcode}, errmsg={result.get('errmsg')}"
    )
    return False


async def send_reminder(openid: str, drug_name: str, time_str: str, template_id: str = None) -> bool:
    """
    发送服药提醒订阅消息。
    模板字段说明（需与微信公众平台申请的模板字段名一致）：
      thing1 → 药品名称
      time2  → 服药时间
    """
    return await _send_subscribe_message(
        openid=openid,
        template_id=template_id or settings.WX_TEMPLATE_REMINDER,
        page="pages/patient/today/index",
        data={
            "thing1": {"value": _safe_template_value(drug_name)},
            "time2":  {"value": _safe_template_value(time_str, 10)},
        },
    )


async def send_missed_reminder(openid: str, drug_name: str, template_id: str = None) -> bool:
    """
    发送漏服提醒订阅消息。
    模板字段说明（需与微信公众平台申请的模板字段名一致）：
      thing1 → 药品名称
      thing2 → 提醒内容
    """
    return await _send_subscribe_message(
        openid=openid,
        template_id=template_id or settings.WX_TEMPLATE_MISSED,
        page="pages/patient/today/index",
        data={
            "thing1": {"value": _safe_template_value(drug_name)},
            "thing2": {"value": "您有药物尚未服用，请及时补服"},
        },
    )
