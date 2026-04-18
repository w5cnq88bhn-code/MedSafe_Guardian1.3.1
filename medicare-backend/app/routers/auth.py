from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas.auth import (
    WechatLoginRequest, WechatLoginResponse,
    PatientRegisterRequest, CaregiverBindRequest, PatientInfo
)
from app.schemas.common import Response
from app.services import auth_service
from app.models.patient import Patient
from app.models.caregiver import Caregiver

router = APIRouter()


@router.post("/auth/wechat-login", response_model=Response)
async def wechat_login(body: WechatLoginRequest, db: Session = Depends(get_db)):
    data = await auth_service.wechat_login(body.code, db)
    return Response.ok(data)


@router.post("/patients/register", response_model=Response)
def register_patient(
    body: PatientRegisterRequest,
    current_user: Patient = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.name              = body.name
    current_user.phone             = body.phone
    current_user.birth_year        = body.birth_year
    current_user.diagnosis_disease = body.diagnosis_disease
    db.commit()
    db.refresh(current_user)
    return Response.ok(PatientInfo.model_validate(current_user))


@router.post("/caregivers/bind", response_model=Response)
def bind_patient(
    body: CaregiverBindRequest,
    current_user: Patient = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.phone == body.patient_phone).first()
    if not patient:
        return Response.error(404, "未找到该手机号对应的患者")

    if current_user.id == patient.id:
        return Response.error(400, "不能绑定自己")

    existing = db.query(Caregiver).filter(
        Caregiver.caregiver_openid == current_user.openid,
        Caregiver.patient_id == patient.id,
    ).first()
    if existing:
        return Response.error(409, "已绑定该患者")

    binding = Caregiver(
        caregiver_openid=current_user.openid,
        patient_id=patient.id,
        relationship=body.relationship,
    )
    db.add(binding)
    db.commit()
    return Response.ok({"patient_id": patient.id, "patient_name": patient.name})


@router.get("/caregivers/patients", response_model=Response)
def get_bound_patients(
    current_user: Patient = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bindings = db.query(Caregiver).filter(
        Caregiver.caregiver_openid == current_user.openid
    ).all()
    patient_ids = [b.patient_id for b in bindings]
    patients = db.query(Patient).filter(Patient.id.in_(patient_ids)).all()
    return Response.ok([PatientInfo.model_validate(p) for p in patients])
