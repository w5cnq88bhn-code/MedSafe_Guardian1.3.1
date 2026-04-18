from pydantic import BaseModel, Field, field_validator
from typing import Optional
import datetime


class WechatLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, description="wx.login 返回的临时 code")


class WechatLoginResponse(BaseModel):
    token: str
    openid: str
    user_id: int
    is_new_user: bool


class PatientRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="患者姓名")
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="11位手机号")
    # birth_year 不用 Field(le=...) 静态上限，改用 validator 动态计算，避免跨年问题
    birth_year: int = Field(..., ge=1900, description="出生年份，不早于1900年")
    diagnosis_disease: Optional[str] = Field(None, max_length=500)

    @field_validator("birth_year")
    @classmethod
    def check_birth_year(cls, v: int) -> int:
        # 每次请求时动态获取当前年份，服务器长期运行跨年也能正确校验
        current_year = datetime.date.today().year
        if v > current_year:
            raise ValueError(f"出生年份不能超过当前年份 {current_year}")
        return v


class CaregiverBindRequest(BaseModel):
    patient_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="患者手机号")
    relationship: str = Field(default="child", max_length=20)

    @field_validator("relationship")
    @classmethod
    def check_relationship(cls, v: str) -> str:
        allowed = {"child", "spouse", "parent", "sibling", "other"}
        if v not in allowed:
            raise ValueError(f"relationship 必须是以下之一：{', '.join(sorted(allowed))}")
        return v


class PatientInfo(BaseModel):
    id: int
    name: Optional[str]
    phone: Optional[str]
    birth_year: Optional[int]
    diagnosis_disease: Optional[str]

    class Config:
        from_attributes = True
