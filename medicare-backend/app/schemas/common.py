from typing import Any
from pydantic import BaseModel


class Response(BaseModel):
    """统一 API 响应格式，所有接口返回此结构。"""

    code: int = 200
    message: str = "success"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> "Response":
        """返回成功响应。"""
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> "Response":
        """返回错误响应，可附带额外错误详情（如字段验证失败的具体信息）。"""
        return cls(code=code, message=message, data=data)
