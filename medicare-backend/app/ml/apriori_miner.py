"""
用药场景 Apriori 关联规则挖掘

改进点：基于药理学分类的预剪枝。
同一药理分类内的药物组合（如两种他汀）通常无临床意义，
只保留跨分类的关联规则。

最小事务数 < 10 时直接返回空，避免稀疏数据产生虚假规则。
"""
import logging
from typing import List, Dict, Optional

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

logger = logging.getLogger(__name__)

MIN_SUPPORT    = 0.2
MIN_CONFIDENCE = 0.6
MIN_LIFT       = 1.0


def _build_category_map(drug_categories: Optional[Dict[int, str]] = None) -> Dict[int, str]:
    """
    构建药物ID → 药理分类的映射。
    drug_categories: {drug_id: category_name}，由调用方从数据库传入。
    若未传入，则所有药物视为不同分类（不做预剪枝，退化为标准Apriori）。
    """
    return drug_categories or {}


def _should_prune(drug_a: int, drug_b: int, category_map: Dict[int, str]) -> bool:
    """同一药理分类的药物对返回 True（剪枝）。"""
    if not category_map:
        return False
    cat_a = category_map.get(drug_a)
    cat_b = category_map.get(drug_b)
    if cat_a and cat_b and cat_a == cat_b:
        return True
    return False


def _filter_transactions_by_category(
    transactions: List[List[int]],
    category_map: Dict[int, str],
) -> List[List[int]]:
    # 预剪枝在规则筛选阶段执行，事务本身不过滤（保证支持度计算完整性）
    return transactions


def mine_rules(
    transactions: List[List[int]],
    drug_categories: Optional[Dict[int, str]] = None,
) -> List[dict]:
    """
    Apriori 挖掘，返回跨药理分类的关联规则。

    transactions   : 每条事务为当天实际服用的药物ID列表
    drug_categories: {drug_id: category}，用于预剪枝；不传则不剪枝
    """
    if len(transactions) < 10:
        logger.debug("[Apriori] 事务数不足10条，跳过挖掘")
        return []

    category_map = _build_category_map(drug_categories)

    try:
        te = TransactionEncoder()
        te_array = te.fit_transform(transactions)
        df = pd.DataFrame(te_array, columns=te.columns_)

        frequent_items = apriori(df, min_support=MIN_SUPPORT, use_colnames=True)
        if frequent_items.empty:
            logger.debug("[Apriori] 未发现频繁项集")
            return []

        rules_df = association_rules(
            frequent_items,
            metric="confidence",
            min_threshold=MIN_CONFIDENCE,
            num_itemsets=len(frequent_items),  # mlxtend 0.23+ 必须传此参数
        )
        rules_df = rules_df[rules_df["lift"] >= MIN_LIFT]
        rules_df = rules_df.sort_values("confidence", ascending=False)

        total_rules = len(rules_df)
        result = []
        pruned_count = 0

        for _, row in rules_df.iterrows():
            antecedents = list(row["antecedents"])
            consequents = list(row["consequents"])

            # ── 药理学预剪枝 ──
            # 对前件和后件中的所有药物对进行分类检查
            # 若前件和后件中存在同类药物，则该规则无临床意义，剪枝
            all_drugs = antecedents + consequents
            should_prune = False
            if category_map and len(all_drugs) >= 2:
                for i in range(len(all_drugs)):
                    for j in range(i + 1, len(all_drugs)):
                        if _should_prune(all_drugs[i], all_drugs[j], category_map):
                            should_prune = True
                            break
                    if should_prune:
                        break

            if should_prune:
                pruned_count += 1
                continue

            result.append({
                "antecedent": antecedents,
                "consequent": consequents,
                "support":    round(float(row["support"]), 4),
                "confidence": round(float(row["confidence"]), 4),
                "lift":       round(float(row["lift"]), 4),
            })

        if category_map and total_rules > 0:
            prune_ratio = pruned_count / total_rules * 100
            logger.info(
                f"[Apriori] 药理学预剪枝完成: "
                f"原始规则={total_rules}, 剪枝={pruned_count} ({prune_ratio:.1f}%), "
                f"保留跨类规则={len(result)} (具有临床意义)"
            )
        else:
            logger.info(f"[Apriori] 挖掘完成（无分类信息，未执行预剪枝）: 规则数={len(result)}")

        return result

    except Exception as e:
        logger.error(f"[Apriori] 挖掘失败: {e}")
        return []
