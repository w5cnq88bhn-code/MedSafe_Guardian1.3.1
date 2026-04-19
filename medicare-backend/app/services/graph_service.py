"""
Neo4j 药物知识图谱服务
======================
图谱节点类型：
  (:Drug   {id, name, category})          药物
  (:Disease{id, name})                    疾病
  (:Symptom{id, name})                    症状/副作用
  (:Patient{id, name})                    患者

图谱关系类型：
  (:Drug)-[:INTERACTS_WITH {severity, warning}]->(:Drug)   药物相互作用（双向）
  (:Drug)-[:CAUSES]->(:Symptom)                            药物引发症状
  (:Drug)-[:TREATS]->(:Disease)                            药物治疗疾病
  (:Drug)-[:CONTRAINDICATED_FOR]->(:Disease)               药物对疾病相对禁忌
  (:Patient)-[:HAS_DISEASE]->(:Disease)                    患者患有疾病
  (:Patient)-[:TAKES]->(:Drug)                             患者正在服用药物

二阶推理示例：
  MATCH (d:Drug)-[:CAUSES]->(s:Symptom)<-[:HAS_SYMPTOM]-(dis:Disease)<-[:HAS_DISEASE]-(p:Patient)
  WHERE d.id = $drug_id AND p.id = $patient_id
  RETURN d, s, dis, p
  → 药物A会引发症状S，症状S是疾病D的表现，患者P患有疾病D → 药物A对患者P相对禁忌
"""
import logging
from typing import Optional, List, Dict, Any
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

from app.core.config import settings

logger = logging.getLogger(__name__)

_driver: Optional[Driver] = None


def get_driver() -> Optional[Driver]:
    """获取 Neo4j 驱动（懒加载，连接失败时返回 None 而非崩溃）。"""
    global _driver
    if _driver is not None:
        return _driver
    try:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_lifetime=3600,
            max_connection_pool_size=20,
            connection_timeout=5,
        )
        _driver.verify_connectivity()
        logger.info(f"[Graph] Neo4j 连接成功: {settings.NEO4J_URI}")
        return _driver
    except (ServiceUnavailable, AuthError, Exception) as e:
        logger.warning(f"[Graph] Neo4j 连接失败，图谱功能降级: {e}")
        _driver = None
        return None


def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def is_available() -> bool:
    return get_driver() is not None


# ── 图谱初始化 ────────────────────────────────────────────────────────────

def init_graph_schema():
    """创建约束和索引（幂等，可重复执行）。"""
    driver = get_driver()
    if not driver:
        return
    with driver.session() as session:
        constraints = [
            "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:Drug) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT disease_id IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (s:Symptom) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.id IS UNIQUE",
        ]
        for c in constraints:
            try:
                session.run(c)
            except Exception as e:
                logger.debug(f"[Graph] 约束已存在或创建失败: {e}")
    logger.info("[Graph] 图谱 Schema 初始化完成")


def sync_drugs_to_graph(drugs: List[Dict]):
    """
    将 PostgreSQL 中的药物数据同步到 Neo4j。
    drugs: [{"id": 1, "generic_name": "阿司匹林", "category": "抗血小板药"}, ...]
    """
    driver = get_driver()
    if not driver:
        return
    with driver.session() as session:
        session.run("""
            UNWIND $drugs AS d
            MERGE (drug:Drug {id: d.id})
            SET drug.name = d.generic_name,
                drug.category = d.category,
                drug.brand_name = d.brand_name
        """, drugs=drugs)
    logger.info(f"[Graph] 同步药物节点: {len(drugs)} 个")


def sync_interactions_to_graph(interactions: List[Dict]):
    """
    将药物相互作用同步到图谱（双向关系）。
    interactions: [{"drug_a_id": 1, "drug_b_id": 2, "severity": "high", "warning_text": "..."}]
    """
    driver = get_driver()
    if not driver:
        return
    with driver.session() as session:
        session.run("""
            UNWIND $rels AS r
            MATCH (a:Drug {id: r.drug_a_id}), (b:Drug {id: r.drug_b_id})
            MERGE (a)-[rel:INTERACTS_WITH {severity: r.severity}]->(b)
            SET rel.warning = r.warning_text, rel.advice = r.advice
            MERGE (b)-[rel2:INTERACTS_WITH {severity: r.severity}]->(a)
            SET rel2.warning = r.warning_text, rel2.advice = r.advice
        """, rels=interactions)
    logger.info(f"[Graph] 同步药物相互作用: {len(interactions)} 对")


def sync_disease_knowledge():
    """
    写入药物-疾病-症状知识（静态知识库，基于临床文献）。
    这是二阶推理的核心数据。
    """
    driver = get_driver()
    if not driver:
        return

    # 疾病节点
    diseases = [
        {"id": "d_hypertension",   "name": "高血压"},
        {"id": "d_diabetes",       "name": "2型糖尿病"},
        {"id": "d_heart_failure",  "name": "慢性心力衰竭"},
        {"id": "d_afib",           "name": "心房颤动"},
        {"id": "d_hyperkalemia",   "name": "高钾血症"},
        {"id": "d_hypokalemia",    "name": "低钾血症"},
        {"id": "d_bleeding",       "name": "出血风险"},
        {"id": "d_hypoglycemia",   "name": "低血糖"},
        {"id": "d_rhabdomyolysis", "name": "横纹肌溶解"},
        {"id": "d_bradycardia",    "name": "心动过缓"},
        {"id": "d_renal_failure",  "name": "肾功能不全"},
    ]

    # 症状节点
    symptoms = [
        {"id": "s_high_bp",        "name": "血压升高"},
        {"id": "s_bleeding",       "name": "出血"},
        {"id": "s_low_glucose",    "name": "血糖降低"},
        {"id": "s_muscle_pain",    "name": "肌肉疼痛"},
        {"id": "s_slow_heart",     "name": "心率减慢"},
        {"id": "s_high_potassium", "name": "血钾升高"},
        {"id": "s_low_potassium",  "name": "血钾降低"},
        {"id": "s_digoxin_toxic",  "name": "地高辛毒性反应"},
    ]

    # 药物-症状关系（药物会引发的症状/风险）
    drug_causes_symptom = [
        # drug_id(int) → symptom_id(str)
        {"drug_id": 1,  "symptom_id": "s_bleeding",       "mechanism": "抑制血小板聚集"},
        {"drug_id": 2,  "symptom_id": "s_bleeding",       "mechanism": "抑制凝血因子"},
        {"drug_id": 3,  "symptom_id": "s_bleeding",       "mechanism": "抑制血小板聚集"},
        {"drug_id": 4,  "symptom_id": "s_muscle_pain",    "mechanism": "抑制HMG-CoA还原酶"},
        {"drug_id": 6,  "symptom_id": "s_high_bp",        "mechanism": "停药反跳"},
        {"drug_id": 8,  "symptom_id": "s_slow_heart",     "mechanism": "β受体阻滞"},
        {"drug_id": 9,  "symptom_id": "s_slow_heart",     "mechanism": "β受体阻滞"},
        {"drug_id": 10, "symptom_id": "s_high_potassium", "mechanism": "抑制醛固酮"},
        {"drug_id": 11, "symptom_id": "s_high_potassium", "mechanism": "抑制醛固酮"},
        {"drug_id": 12, "symptom_id": "s_low_potassium",  "mechanism": "促进钾排泄"},
        {"drug_id": 13, "symptom_id": "s_high_potassium", "mechanism": "保钾利尿"},
        {"drug_id": 14, "symptom_id": "s_low_potassium",  "mechanism": "强效排钾"},
        {"drug_id": 15, "symptom_id": "s_low_glucose",    "mechanism": "改善胰岛素敏感性"},
        {"drug_id": 16, "symptom_id": "s_low_glucose",    "mechanism": "促进胰岛素分泌"},
        {"drug_id": 25, "symptom_id": "s_digoxin_toxic",  "mechanism": "治疗窗窄"},
        {"drug_id": 26, "symptom_id": "s_slow_heart",     "mechanism": "延长动作电位"},
        {"drug_id": 28, "symptom_id": "s_bleeding",       "mechanism": "抑制血小板+损伤胃黏膜"},
    ]

    # 症状-疾病关系（症状是疾病的表现/风险因素）
    symptom_indicates_disease = [
        {"symptom_id": "s_high_bp",        "disease_id": "d_hypertension"},
        {"symptom_id": "s_bleeding",       "disease_id": "d_bleeding"},
        {"symptom_id": "s_low_glucose",    "disease_id": "d_hypoglycemia"},
        {"symptom_id": "s_muscle_pain",    "disease_id": "d_rhabdomyolysis"},
        {"symptom_id": "s_slow_heart",     "disease_id": "d_bradycardia"},
        {"symptom_id": "s_high_potassium", "disease_id": "d_hyperkalemia"},
        {"symptom_id": "s_low_potassium",  "disease_id": "d_hypokalemia"},
        {"symptom_id": "s_low_potassium",  "disease_id": "d_digoxin_toxic" if False else "d_hypokalemia"},
        {"symptom_id": "s_digoxin_toxic",  "disease_id": "d_heart_failure"},
    ]

    # 药物-疾病禁忌关系（直接禁忌，一阶）
    drug_contraindicated = [
        {"drug_id": 8,  "disease_id": "d_bradycardia",   "reason": "加重心动过缓"},
        {"drug_id": 9,  "disease_id": "d_bradycardia",   "reason": "加重心动过缓"},
        {"drug_id": 10, "disease_id": "d_hyperkalemia",  "reason": "升高血钾"},
        {"drug_id": 11, "disease_id": "d_hyperkalemia",  "reason": "升高血钾"},
        {"drug_id": 13, "disease_id": "d_hyperkalemia",  "reason": "保钾利尿"},
        {"drug_id": 14, "disease_id": "d_hypokalemia",   "reason": "加重低钾"},
        {"drug_id": 16, "disease_id": "d_hypoglycemia",  "reason": "促进胰岛素分泌"},
        {"drug_id": 25, "disease_id": "d_hypokalemia",   "reason": "低钾增强地高辛毒性"},
    ]

    with driver.session() as session:
        # 写入疾病节点
        session.run("""
            UNWIND $diseases AS d
            MERGE (dis:Disease {id: d.id})
            SET dis.name = d.name
        """, diseases=diseases)

        # 写入症状节点
        session.run("""
            UNWIND $symptoms AS s
            MERGE (sym:Symptom {id: s.id})
            SET sym.name = s.name
        """, symptoms=symptoms)

        # 药物→症状
        session.run("""
            UNWIND $rels AS r
            MATCH (d:Drug {id: r.drug_id}), (s:Symptom {id: r.symptom_id})
            MERGE (d)-[rel:CAUSES]->(s)
            SET rel.mechanism = r.mechanism
        """, rels=drug_causes_symptom)

        # 症状→疾病
        session.run("""
            UNWIND $rels AS r
            MATCH (s:Symptom {id: r.symptom_id}), (dis:Disease {id: r.disease_id})
            MERGE (s)-[:INDICATES]->(dis)
        """, rels=symptom_indicates_disease)

        # 药物→疾病禁忌
        session.run("""
            UNWIND $rels AS r
            MATCH (d:Drug {id: r.drug_id}), (dis:Disease {id: r.disease_id})
            MERGE (d)-[rel:CONTRAINDICATED_FOR]->(dis)
            SET rel.reason = r.reason
        """, rels=drug_contraindicated)

    logger.info("[Graph] 疾病知识库同步完成")


def sync_patient_to_graph(patient_id: int, patient_name: str,
                           diseases: List[str], drug_ids: List[int]):
    """
    将患者的疾病和用药情况同步到图谱。
    diseases: 疾病名称列表（从 diagnosis_disease 字段解析）
    drug_ids: 当前有效药物 ID 列表
    """
    driver = get_driver()
    if not driver:
        return

    # 疾病名称 → 图谱疾病ID 映射
    disease_name_map = {
        "高血压": "d_hypertension",
        "糖尿病": "d_diabetes",
        "2型糖尿病": "d_diabetes",
        "心力衰竭": "d_heart_failure",
        "慢性心力衰竭": "d_heart_failure",
        "心房颤动": "d_afib",
        "肾功能不全": "d_renal_failure",
    }

    matched_disease_ids = []
    for name in diseases:
        for key, did in disease_name_map.items():
            if key in name:
                matched_disease_ids.append(did)

    with driver.session() as session:
        # 创建/更新患者节点
        session.run("""
            MERGE (p:Patient {id: $pid})
            SET p.name = $name
        """, pid=patient_id, name=patient_name)

        # 清除旧的疾病和用药关系，重新建立
        session.run("""
            MATCH (p:Patient {id: $pid})-[r:HAS_DISEASE|TAKES]->()
            DELETE r
        """, pid=patient_id)

        # 建立患者-疾病关系
        if matched_disease_ids:
            session.run("""
                UNWIND $disease_ids AS did
                MATCH (p:Patient {id: $pid}), (dis:Disease {id: did})
                MERGE (p)-[:HAS_DISEASE]->(dis)
            """, pid=patient_id, disease_ids=matched_disease_ids)

        # 建立患者-药物关系
        if drug_ids:
            session.run("""
                UNWIND $drug_ids AS did
                MATCH (p:Patient {id: $pid}), (d:Drug {id: did})
                MERGE (p)-[:TAKES]->(d)
            """, pid=patient_id, drug_ids=drug_ids)


# ── 核心推理查询 ──────────────────────────────────────────────────────────

def query_direct_conflicts(drug_ids: List[int]) -> List[Dict]:
    """
    一阶查询：直接药物相互作用（等价于原来的关系表查询，但走图谱）。
    """
    driver = get_driver()
    if not driver:
        return []
    with driver.session() as session:
        result = session.run("""
            UNWIND $ids AS id1
            UNWIND $ids AS id2
            WITH id1, id2 WHERE id1 < id2
            MATCH (a:Drug {id: id1})-[r:INTERACTS_WITH]->(b:Drug {id: id2})
            RETURN a.id AS drug_a_id, a.name AS drug_a_name,
                   b.id AS drug_b_id, b.name AS drug_b_name,
                   r.severity AS severity,
                   r.warning AS warning_text,
                   r.advice AS advice
        """, ids=drug_ids)
        return [dict(r) for r in result]


def query_second_order_conflicts(patient_id: int, new_drug_ids: List[int]) -> List[Dict]:
    """
    二阶推理：新药 → 症状 → 疾病 → 患者已有疾病 → 相对禁忌。

    推理路径：
      (新药)-[:CAUSES]->(症状)-[:INDICATES]->(疾病)<-[:HAS_DISEASE]-(患者)
      → 新药会引发某症状，该症状指向某疾病，患者恰好患有该疾病
      → 新药对该患者相对禁忌

    这是一阶查表无法发现的隐性风险。
    """
    driver = get_driver()
    if not driver:
        return []
    with driver.session() as session:
        result = session.run("""
            UNWIND $drug_ids AS did
            MATCH (d:Drug {id: did})-[:CAUSES]->(s:Symptom)-[:INDICATES]->(dis:Disease)
                  <-[:HAS_DISEASE]-(p:Patient {id: $patient_id})
            RETURN d.id AS drug_id,
                   d.name AS drug_name,
                   s.name AS symptom_name,
                   dis.name AS disease_name,
                   collect(DISTINCT s.name) AS symptom_chain
        """, drug_ids=new_drug_ids, patient_id=patient_id)
        return [dict(r) for r in result]


def query_direct_contraindications(patient_id: int, new_drug_ids: List[int]) -> List[Dict]:
    """
    一阶禁忌推理：药物直接对患者疾病禁忌。
    (新药)-[:CONTRAINDICATED_FOR]->(疾病)<-[:HAS_DISEASE]-(患者)
    """
    driver = get_driver()
    if not driver:
        return []
    with driver.session() as session:
        result = session.run("""
            UNWIND $drug_ids AS did
            MATCH (d:Drug {id: did})-[r:CONTRAINDICATED_FOR]->(dis:Disease)
                  <-[:HAS_DISEASE]-(p:Patient {id: $patient_id})
            RETURN d.id AS drug_id,
                   d.name AS drug_name,
                   dis.name AS disease_name,
                   r.reason AS reason
        """, drug_ids=new_drug_ids, patient_id=patient_id)
        return [dict(r) for r in result]


def get_graph_stats() -> Dict[str, Any]:
    """返回图谱统计信息，用于健康检查和演示。"""
    driver = get_driver()
    if not driver:
        return {"available": False}
    with driver.session() as session:
        counts = session.run("""
            MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt
        """)
        rels = session.run("""
            MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt
        """)
        return {
            "available": True,
            "nodes": {r["label"]: r["cnt"] for r in counts},
            "relationships": {r["rel_type"]: r["cnt"] for r in rels},
        }
