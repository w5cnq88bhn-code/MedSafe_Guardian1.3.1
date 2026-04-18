from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models.patient import Patient
from app.models.caregiver import Caregiver

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Patient:
    payload = decode_token(credentials.credentials)
    user_id: int = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效")

    user = db.query(Patient).filter(Patient.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def verify_patient_access(
    patient_id: int,
    current_user: Patient = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> int:
    """
    验证当前用户对目标患者数据的访问权限。
    两种合法情况：
      1. 当前用户本身就是该患者（患者查看自己的数据）
      2. 当前用户是该患者的绑定子女（caregivers 表中存在记录）
    """
    # 情况1：患者访问自己的数据
    if current_user.id == patient_id:
        return patient_id

    # 情况2：子女访问绑定老人的数据
    binding = db.query(Caregiver).filter(
        Caregiver.caregiver_openid == current_user.openid,
        Caregiver.patient_id == patient_id,
    ).first()
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该患者数据",
        )
    return patient_id
