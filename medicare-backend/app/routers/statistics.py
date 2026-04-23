from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, verify_patient_access
from app.models.patient import Patient
from app.schemas.common import Response
from app.services.statistics_service import (
    get_7days_stats, get_28days_stats, get_14days_daily, get_lifetime_stats
)

router = APIRouter()


@router.get("/statistics/7days/{patient_id}", response_model=Response)
def stats_7days(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)
    return Response.ok(get_7days_stats(patient_id, db).model_dump())


@router.get("/statistics/28days/{patient_id}", response_model=Response)
def stats_28days(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)
    return Response.ok(get_28days_stats(patient_id, db).model_dump())


@router.get("/statistics/14days/{patient_id}", response_model=Response)
def stats_14days(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)
    return Response.ok(get_14days_daily(patient_id, db).model_dump())


@router.get("/statistics/lifetime/{patient_id}", response_model=Response)
def stats_lifetime(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)
    return Response.ok(get_lifetime_stats(patient_id, db).model_dump())
