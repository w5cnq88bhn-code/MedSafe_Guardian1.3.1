"""
Apriori 关联规则挖掘任务：每周日凌晨3点为活跃患者挖掘规则。

事务安全：每个患者独立事务，出错时 rollback 不影响其他患者，
且旧规则在新规则成功写入后才被替换（先插入新规则，再删除旧规则，最后 commit）。
"""
import logging
from datetime import date, timedelta
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.log import MedicationLog
from app.models.drug import Drug
from app.models.rule import AssociationRule
from app.models.enums import MedicationStatus
from app.ml.apriori_miner import mine_rules

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.apriori_task.run_apriori_mining",
    max_retries=2,
    default_retry_delay=600,
)
def run_apriori_mining():
    db = SessionLocal()
    try:
        active_since = date.today() - timedelta(days=30)
        active_patient_ids = (
            db.query(MedicationLog.patient_id)
              .filter(MedicationLog.scheduled_time >= active_since)
              .distinct()
              .all()
        )

        all_drugs = db.query(Drug).all()
        drugs = {d.id: d.generic_name for d in all_drugs}
        # 药理分类映射，用于药理学预剪枝
        drug_categories = {d.id: d.category for d in all_drugs if d.category}
        today = date.today()
        processed = skipped = failed = 0

        for (patient_id,) in active_patient_ids:
            try:
                # 获取患者历史服药事务（以天为单位，当天实际服用的药物ID集合）
                logs = (
                    db.query(MedicationLog)
                      .filter(
                          MedicationLog.patient_id == patient_id,
                          MedicationLog.status == MedicationStatus.TAKEN,
                      )
                      .all()
                )

                if len(logs) < 30:
                    skipped += 1
                    continue

                # 按天聚合事务
                transactions: dict = {}
                for log in logs:
                    d = log.scheduled_time.date()
                    transactions.setdefault(d, set()).add(log.drug_id)

                transaction_list = [list(v) for v in transactions.values()]
                if len(transaction_list) < 20:
                    skipped += 1
                    continue

                # 传入药理分类映射，启用预剪枝，仅保留跨类关联（具有临床意义）
                rules = mine_rules(transaction_list, drug_categories=drug_categories)

                # 无规则时跳过（不删除旧规则，保留上次结果）
                if not rules:
                    logger.debug(f"[Apriori] patient_id={patient_id} 未挖掘到规则，保留旧规则")
                    skipped += 1
                    continue

                # 构建新规则对象（先构建，不立即写库）
                new_rule_objs = []
                for rule in rules:
                    antecedent_ids = list(rule["antecedent"])
                    consequent_ids = list(rule["consequent"])
                    ant_names = "、".join(drugs.get(i, str(i)) for i in antecedent_ids)
                    con_names = "、".join(drugs.get(i, str(i)) for i in consequent_ids)
                    new_rule_objs.append(AssociationRule(
                        patient_id       = patient_id,
                        antecedent       = antecedent_ids,
                        consequent       = consequent_ids,
                        support          = rule["support"],
                        confidence       = rule["confidence"],
                        lift             = rule["lift"],
                        rule_description = f"服用【{ant_names}】时通常也需服用【{con_names}】，请勿遗漏",
                        generated_date   = today,
                    ))

                # 先删旧规则，再插新规则，最后 commit（同一事务，原子操作）
                db.query(AssociationRule).filter(
                    AssociationRule.patient_id == patient_id
                ).delete()
                db.add_all(new_rule_objs)
                db.commit()

                logger.debug(f"[Apriori] patient_id={patient_id} 生成规则 {len(new_rule_objs)} 条")
                processed += 1

            except Exception as e:
                db.rollback()
                logger.error(f"[Apriori] patient_id={patient_id} 处理失败: {e}")
                failed += 1
                continue  # 单个患者失败不影响其他患者

        logger.info(
            f"[Apriori] 挖掘完成: 成功={processed}, 跳过={skipped}, 失败={failed}"
        )
        return {"processed": processed, "skipped": skipped, "failed": failed}

    except Exception as e:
        logger.error(f"[Apriori] 任务整体失败: {e}")
        raise
    finally:
        db.close()
