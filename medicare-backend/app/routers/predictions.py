from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from app.core.database import get_db
from app.core.deps import get_current_user, verify_patient_access
from app.models.patient import Patient
from app.models.prediction import AdherencePrediction
from app.models.rule import AssociationRule
from app.schemas.common import Response

router = APIRouter()

TIME_SLOTS = ["morning", "afternoon", "evening"]


@router.get("/predictions/{patient_id}", response_model=Response)
def get_predictions(
    patient_id: int,
    days: int = Query(default=3, ge=1, le=3),
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)

    today = date.today()
    preds = (
        db.query(AdherencePrediction)
          .filter(
              AdherencePrediction.patient_id == patient_id,
              AdherencePrediction.prediction_date == today,
              AdherencePrediction.target_day_offset <= days,
          )
          .order_by(AdherencePrediction.target_day_offset, AdherencePrediction.target_time_slot)
          .all()
    )

    pred_map = {
        (p.target_day_offset, p.target_time_slot): float(p.miss_probability)
        for p in preds
    }

    slots = []
    for day_offset in range(1, days + 1):
        for slot in TIME_SLOTS:
            prob = pred_map.get((day_offset, slot), 0.0)
            slots.append({
                "day_offset":       day_offset,
                "time_slot":        slot,
                "miss_probability": prob,
                "is_high_risk":     prob > 0.7,
            })

    return Response.ok({
        "patient_id":      patient_id,
        "prediction_date": today,
        "slots":           slots,
    })


@router.get("/rules/{patient_id}", response_model=Response)
def get_rules(
    patient_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    verify_patient_access(patient_id, current_user, db)

    rules = (
        db.query(AssociationRule)
          .filter(AssociationRule.patient_id == patient_id)
          .order_by(AssociationRule.confidence.desc())
          .limit(limit)
          .all()
    )
    return Response.ok([{
        "id":               r.id,
        "rule_description": r.rule_description,
        "confidence":       float(r.confidence),
        "support":          float(r.support),
        "lift":             float(r.lift),
        "suggestion":       "建议在服药后立即检查是否遗漏相关药物",
    } for r in rules])
