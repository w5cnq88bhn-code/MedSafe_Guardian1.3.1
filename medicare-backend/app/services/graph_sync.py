"""
图谱数据同步服务
在 API 启动时（lifespan）自动将 PostgreSQL 数据同步到 Neo4j。
同步是幂等的，可重复执行。
"""
import logging
from sqlalchemy.orm import Session
from app.models.drug import Drug
from app.models.drug_interaction import DrugInteraction
from app.models.patient import Patient
from app.models.schedule import MedicationSchedule
from app.services import graph_service

logger = logging.getLogger(__name__)


def sync_all(db: Session):
    """全量同步：药物、相互作用、疾病知识库。启动时执行一次。"""
    if not graph_service.is_available():
        logger.warning("[GraphSync] Neo4j 不可用，跳过同步")
        return

    try:
        graph_service.init_graph_schema()

        # 同步药物
        drugs = db.query(Drug).all()
        graph_service.sync_drugs_to_graph([
            {"id": d.id, "generic_name": d.generic_name,
             "brand_name": d.brand_name or "", "category": d.category or ""}
            for d in drugs
        ])

        # 同步相互作用
        interactions = db.query(DrugInteraction).all()
        graph_service.sync_interactions_to_graph([
            {"drug_a_id": i.drug_a_id, "drug_b_id": i.drug_b_id,
             "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
             "warning_text": i.warning_text or "",
             "advice": i.advice or ""}
            for i in interactions
        ])

        # 同步疾病知识库（静态）
        graph_service.sync_disease_knowledge()

        # 同步所有患者
        patients = db.query(Patient).all()
        for patient in patients:
            active_drug_ids = [
                row.drug_id for row in
                db.query(MedicationSchedule.drug_id)
                  .filter(MedicationSchedule.patient_id == patient.id,
                          MedicationSchedule.is_active == True)
                  .distinct().all()
            ]
            diseases = []
            if patient.diagnosis_disease:
                diseases = [d.strip() for d in patient.diagnosis_disease.replace("、", ",").split(",")]
            graph_service.sync_patient_to_graph(
                patient.id, patient.name or "",
                diseases, active_drug_ids
            )

        stats = graph_service.get_graph_stats()
        logger.info(f"[GraphSync] 同步完成: {stats}")

    except Exception as e:
        logger.error(f"[GraphSync] 同步失败: {e}", exc_info=True)
