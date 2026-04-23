"""
PDF 就诊报告生成服务（ReportLab）+ FHIR R4B 导出
=================================================

中文字体加载策略（按优先级）：
  1. Docker 镜像中的 WQY 正黑体（Dockerfile 已安装 fonts-wqy-zenhei 并软链接为 simhei.ttf）
  2. 项目目录下的 fonts/simhei.ttf（开发环境手动放置）
  3. Windows 系统字体 C:/Windows/Fonts/simhei.ttf
  4. 降级到 Helvetica（中文显示为空白，仅作最后兜底）

FHIR R4B 导出：
  使用 fhir.resources R4B 子包构建标准资源对象，经 pydantic 验证后序列化。
  Bundle 包含：Patient、MedicationStatement、AllergyIntolerance 资源。
"""
import io
import os
import logging
from datetime import date, datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.allergy import Allergy
from app.models.log import MedicationLog
from app.models.drug import Drug
from app.models.prediction import AdherencePrediction
from app.models.rule import AssociationRule
from app.models.enums import MedicationStatus
from app.services.statistics_service import (
    get_28days_stats, get_14days_daily, get_lifetime_stats
)

logger = logging.getLogger(__name__)

# ── 中文字体注册 ──────────────────────────────────────────────────────────────
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/simhei.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    os.path.join(os.path.dirname(__file__), "../../fonts/simhei.ttf"),
    "C:/Windows/Fonts/simhei.ttf",
]

CN_FONT = "Helvetica"
for _font_path in _FONT_CANDIDATES:
    _font_path = os.path.normpath(_font_path)
    if os.path.exists(_font_path):
        try:
            pdfmetrics.registerFont(TTFont("SimHei", _font_path))
            CN_FONT = "SimHei"
            logger.info(f"[PDF] 中文字体加载成功: {_font_path}")
            break
        except Exception as e:
            logger.warning(f"[PDF] 字体加载失败 {_font_path}: {e}")

if CN_FONT == "Helvetica":
    logger.warning("[PDF] 未找到中文字体，PDF 中文将显示为空白。")


# ── FHIR R4B 导出 ─────────────────────────────────────────────────────────────

def generate_fhir_bundle(patient_id: int, db: Session) -> dict:
    """
    生成 HL7 FHIR R4B 标准 Bundle 资源包。

    使用 fhir.resources R4B 子包构建资源对象，pydantic 在构造时自动做字段校验。
    Bundle 包含：
      - Patient：患者基本信息
      - MedicationStatement：近14天已服药记录
      - AllergyIntolerance：过敏记录
    """
    from fhir.resources.R4B.bundle import Bundle, BundleEntry
    from fhir.resources.R4B.patient import Patient as FHIRPatient
    from fhir.resources.R4B.humanname import HumanName
    from fhir.resources.R4B.contactpoint import ContactPoint
    from fhir.resources.R4B.extension import Extension
    from fhir.resources.R4B.medicationstatement import MedicationStatement
    from fhir.resources.R4B.codeableconcept import CodeableConcept
    from fhir.resources.R4B.coding import Coding
    from fhir.resources.R4B.reference import Reference
    from fhir.resources.R4B.dosage import Dosage
    from fhir.resources.R4B.quantity import Quantity
    from fhir.resources.R4B.allergyintolerance import AllergyIntolerance, AllergyIntoleranceReaction
    from fhir.resources.R4B.meta import Meta

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError("患者不存在")

    today = date.today()
    since = today - timedelta(days=14)

    logs = (
        db.query(MedicationLog, Drug)
          .join(Drug, Drug.id == MedicationLog.drug_id)
          .filter(
              MedicationLog.patient_id == patient_id,
              MedicationLog.scheduled_time >= since,
              MedicationLog.status == MedicationStatus.TAKEN,
          )
          .all()
    )
    allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()

    entries = []

    # ── Patient 资源 ──
    birth_year = patient.birth_year or 1950
    fhir_patient = FHIRPatient(
        id=str(patient_id),
        meta=Meta(profile=["http://hl7.org/fhir/StructureDefinition/Patient"]),
        name=[HumanName(text=patient.name or "未知")],
        birthDate=f"{birth_year}-01-01",
        telecom=(
            [ContactPoint(system="phone", value=patient.phone)]
            if patient.phone else None
        ),
        extension=(
            [Extension(
                url="http://yaoan.app/fhir/StructureDefinition/diagnosis",
                valueString=patient.diagnosis_disease,
            )]
            if patient.diagnosis_disease else None
        ),
    )
    entries.append(BundleEntry(
        fullUrl=f"urn:uuid:patient-{patient_id}",
        resource=fhir_patient,
    ))

    # ── MedicationStatement 资源 ──
    for log, drug in logs:
        effective_dt = (
            log.actual_taken_time or log.scheduled_time
        ).isoformat()

        dose_value = float(log.taken_dose or 0)
        stmt = MedicationStatement(
            id=str(log.id),
            meta=Meta(profile=["http://hl7.org/fhir/StructureDefinition/MedicationStatement"]),
            status="completed",
            subject=Reference(reference=f"urn:uuid:patient-{patient_id}"),
            medicationCodeableConcept=CodeableConcept(
                text=drug.generic_name,
                coding=[Coding(display=drug.brand_name or drug.generic_name)],
            ),
            effectiveDateTime=effective_dt,
            dosage=[Dosage(
                text=f"{dose_value} mg",
                doseAndRate=[{
                    "doseQuantity": Quantity(value=dose_value, unit="mg").dict()
                }],
            )],
        )
        entries.append(BundleEntry(
            fullUrl=f"urn:uuid:medstmt-{log.id}",
            resource=stmt,
        ))

    # ── AllergyIntolerance 资源 ──
    for allergy in allergies:
        recorded = (
            allergy.added_date.isoformat()
            if allergy.added_date else today.isoformat()
        )
        ai = AllergyIntolerance(
            id=str(allergy.id),
            meta=Meta(profile=["http://hl7.org/fhir/StructureDefinition/AllergyIntolerance"]),
            patient=Reference(reference=f"urn:uuid:patient-{patient_id}"),
            code=CodeableConcept(text=allergy.drug_id_or_ingredient),
            reaction=[AllergyIntoleranceReaction(
                description=allergy.reaction_type or "未知反应",
                manifestation=[CodeableConcept(text=allergy.reaction_type or "未知反应")],
            )],
            recordedDate=recorded,
        )
        entries.append(BundleEntry(
            fullUrl=f"urn:uuid:allergy-{allergy.id}",
            resource=ai,
        ))

    bundle = Bundle(
        id=f"yaoan-bundle-{patient_id}-{today.isoformat()}",
        meta=Meta(
            profile=["http://hl7.org/fhir/StructureDefinition/Bundle"],
            tag=[{"system": "http://yaoan.app/fhir", "code": "medication-report"}],
        ),
        type="collection",
        timestamp=datetime.utcnow().isoformat() + "Z",
        total=len(entries),
        entry=entries,
    )

    logger.info(f"[FHIR] Bundle 生成完成: patient_id={patient_id}, entries={len(entries)}")
    # model_dump() 输出标准 Python dict，可直接被 FastAPI 序列化
    return bundle.model_dump(exclude_none=True)


# ── PDF 报告生成 ──────────────────────────────────────────────────────────────

def _make_styles():
    title = ParagraphStyle("title", fontName=CN_FONT, fontSize=18, spaceAfter=12, alignment=1)
    h2    = ParagraphStyle("h2",    fontName=CN_FONT, fontSize=13, spaceBefore=12, spaceAfter=6,
                           textColor=colors.HexColor("#1a5276"))
    body  = ParagraphStyle("body",  fontName=CN_FONT, fontSize=10, spaceAfter=4)
    small = ParagraphStyle("small", fontName=CN_FONT, fontSize=8, spaceAfter=2,
                           textColor=colors.HexColor("#666666"))
    return title, h2, body, small


def generate_report(patient_id: int, db: Session) -> bytes:
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError("患者不存在")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    title_style, h2_style, body_style, small_style = _make_styles()
    story = []

    # ── 封面 ──
    story.append(Paragraph("药安守护 就诊用药报告", title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 0.3*cm))

    age = date.today().year - (patient.birth_year or 1950)
    story.append(Paragraph(f"患者姓名：{patient.name or '—'}　　年龄：{age} 岁", body_style))
    story.append(Paragraph(f"诊断病种：{patient.diagnosis_disease or '—'}", body_style))
    story.append(Paragraph(f"报告生成日期：{date.today().strftime('%Y年%m月%d日')}", body_style))
    story.append(Spacer(1, 0.5*cm))

    # ── 28天总览 ──
    story.append(Paragraph("一、28天用药总览", h2_style))
    stats28 = get_28days_stats(patient_id, db)
    story.append(Paragraph(f"总服用药物种类：{stats28.total_drug_types} 种", body_style))
    story.append(Paragraph(f"总服药次数（已服）：{stats28.total_taken_count} 次", body_style))
    for drug in stats28.drugs:
        diff_text = ""
        if drug.dose_diff > 0:
            diff_text = f"  ⚠ 多服 +{drug.dose_diff}{drug.dosage_unit}"
        elif drug.dose_diff < 0:
            diff_text = f"  ⚠ 少服 {drug.dose_diff}{drug.dosage_unit}"
        story.append(Paragraph(
            f"　• {drug.drug_name}：计划 {drug.planned_dose}{drug.dosage_unit}，"
            f"实际 {drug.actual_dose}{drug.dosage_unit}{diff_text}",
            body_style,
        ))

    # ── 14天每日明细 ──
    story.append(Paragraph("二、14天每日服药明细", h2_style))
    stats14 = get_14days_daily(patient_id, db)
    if stats14.records:
        table_data = [["日期", "药品名称", "剂量", "状态"]]
        for r in stats14.records:
            status_cn = {"taken": "已服", "missed": "漏服", "pending": "待服"}.get(
                r.status.value if hasattr(r.status, "value") else str(r.status), str(r.status)
            )
            table_data.append([
                r.date.strftime("%m/%d"),
                r.drug_name,
                f"{r.dose}{r.dosage_unit}",
                status_cn,
            ])
        t = Table(table_data, colWidths=[2.5*cm, 5*cm, 3*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a5276")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, -1), CN_FONT),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf4fb")]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("暂无记录", body_style))

    # ── 长期服药史 ──
    story.append(Paragraph("三、长期服药史", h2_style))
    lifetime = get_lifetime_stats(patient_id, db)
    if lifetime.drugs:
        for d in lifetime.drugs:
            story.append(Paragraph(
                f"• {d.drug_name}　首次：{d.first_taken or '—'}　最近：{d.last_taken or '—'}",
                body_style,
            ))
    else:
        story.append(Paragraph("暂无记录", body_style))

    # ── 过敏清单 ──
    story.append(Paragraph("四、过敏药物清单", h2_style))
    allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    if allergies:
        for a in allergies:
            story.append(Paragraph(
                f"• {a.drug_id_or_ingredient}（{a.reaction_type or '未知反应'}）", body_style
            ))
    else:
        story.append(Paragraph("无过敏记录", body_style))

    # ── 依从性预测摘要 ──
    story.append(Paragraph("五、依从性预测摘要（未来3天高风险时段）", h2_style))
    preds = (
        db.query(AdherencePrediction)
          .filter(
              AdherencePrediction.patient_id == patient_id,
              AdherencePrediction.prediction_date == date.today(),
              AdherencePrediction.miss_probability > 0.7,
          )
          .order_by(AdherencePrediction.target_day_offset, AdherencePrediction.target_time_slot)
          .all()
    )
    slot_cn = {"morning": "早", "afternoon": "中", "evening": "晚"}
    if preds:
        for p in preds:
            story.append(Paragraph(
                f"• 第{p.target_day_offset}天 "
                f"{slot_cn.get(p.target_time_slot, p.target_time_slot)}："
                f"漏服概率 {float(p.miss_probability)*100:.1f}%（高风险）",
                body_style,
            ))
    else:
        story.append(Paragraph("未来3天无高风险时段", body_style))

    # ── 关联规则洞察 ──
    story.append(Paragraph("六、关联规则洞察（Top 5）", h2_style))
    rules = (
        db.query(AssociationRule)
          .filter(AssociationRule.patient_id == patient_id)
          .order_by(AssociationRule.confidence.desc())
          .limit(5)
          .all()
    )
    if rules:
        for r in rules:
            story.append(Paragraph(
                f"• {r.rule_description}（置信度 {float(r.confidence)*100:.1f}%）",
                body_style,
            ))
    else:
        story.append(Paragraph("暂无关联规则数据", body_style))

    # ── FHIR 导出说明 ──
    story.append(Paragraph("七、数据导出", h2_style))
    story.append(Paragraph(
        f"本报告支持导出 FHIR R4B Bundle（GET /reports/{patient_id}/fhir），"
        "包含 Patient、MedicationStatement、AllergyIntolerance 资源。",
        body_style,
    ))

    # ── 医生备注 ──
    story.append(Paragraph("八、医生备注", h2_style))
    story.append(Spacer(1, 3*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph("（留白，供医生填写）", body_style))

    doc.build(story)
    return buffer.getvalue()
