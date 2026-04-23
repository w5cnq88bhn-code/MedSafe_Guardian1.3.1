import logging
from fastapi import APIRouter, Depends
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, verify_patient_access
from app.models.patient import Patient
from app.models.log import MedicationLog
from app.models.drug import Drug
from app.services.pdf_service import generate_report, generate_fhir_bundle
from app.services.push_service import send_missed_reminder
from app.schemas.log import RemindRequest
from app.schemas.common import Response

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/reports/{patient_id}")
def download_report(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    生成并下载就诊报告 PDF。
    同步函数：FastAPI 自动在线程池中执行，不阻塞事件循环。
    """
    verify_patient_access(patient_id, current_user, db)

    try:
        pdf_bytes = generate_report(patient_id, db)
    except ValueError as e:
        return FastAPIResponse(
            content=str(e).encode(),
            status_code=404,
            media_type="text/plain",
        )
    except Exception as e:
        logger.error(f"[Report] PDF 生成失败 patient_id={patient_id}: {e}")
        return FastAPIResponse(
            content=b"Report generation failed",
            status_code=500,
            media_type="text/plain",
        )

    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=yaoan_report_{patient_id}.pdf"
        },
    )


@router.get("/reports/{patient_id}/fhir", response_model=Response)
def download_fhir_bundle(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """
    导出 FHIR R4B 标准 Bundle 资源包。
    Bundle 包含 Patient、MedicationStatement、AllergyIntolerance 资源。
    """
    verify_patient_access(patient_id, current_user, db)

    try:
        bundle = generate_fhir_bundle(patient_id, db)
    except ValueError as e:
        return Response.error(404, str(e))
    except Exception as e:
        logger.error(f"[FHIR] Bundle 生成失败 patient_id={patient_id}: {e}")
        return Response.error(500, "FHIR Bundle 生成失败，请稍后重试")

    return Response.ok(bundle)


@router.post("/remind/{patient_id}", response_model=Response)
async def send_remind(
    patient_id: int,
    body: RemindRequest,          # 替换 dict，有类型校验和 API 文档
    db: Session = Depends(get_db),
    current_user: Patient = Depends(get_current_user),
):
    """子女端一键提醒：向患者发送漏服提醒"""
    verify_patient_access(patient_id, current_user, db)

    log = db.query(MedicationLog).filter(MedicationLog.id == body.log_id).first()
    if not log:
        return Response.error(404, "记录不存在")

    if log.patient_id != patient_id:
        return Response.error(400, "记录与患者不匹配")

    # 权限校验已通过，patient 必然存在，但仍做防御性检查
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return Response.error(404, "患者不存在")

    drug = db.query(Drug).filter(Drug.id == log.drug_id).first()
    if not drug:
        return Response.error(404, "药物信息不存在")

    success = await send_missed_reminder(patient.openid, drug.generic_name)
    if not success:
        # 推送失败（模板未配置或微信接口错误），记录日志但不阻断业务
        logger.warning(
            f"[Remind] 推送失败 patient_id={patient_id}, log_id={body.log_id}"
        )
        return Response.error(500, "提醒发送失败，请稍后重试")

    return Response.ok({"message": "提醒已发送"})
