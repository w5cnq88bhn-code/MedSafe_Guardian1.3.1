-- =====================================================================
-- 药安守护 完整演示数据集 seed_demo.sql
-- 在 seed_data.sql 基础上补充：
--   1. 今日服药计划（pending 状态，可演示"今日用药"页）
--   2. adherence_predictions（今日生成，可演示预测曲线）
--   3. association_rules（5条规则，可演示关联规则卡片）
-- 执行方式：
--   docker-compose exec postgres psql -U medicare -d medicare -f /docker-entrypoint-initdb.d/seed_demo.sql
-- 或在容器外：
--   docker-compose exec -T postgres psql -U medicare -d medicare < sql/seed_demo.sql
-- =====================================================================

-- ===================== 今日 pending 服药记录 =====================
-- 让"今日用药"页面有数据可以操作（演示服药登记功能）
INSERT INTO medication_logs
    (patient_id, drug_id, schedule_id, scheduled_time, actual_taken_time, status, taken_dose, source)
SELECT
    1,
    ms.drug_id,
    ms.id,
    CURRENT_DATE + ms.time_point,
    NULL,
    'pending',
    ms.dosage,
    'system'
FROM medication_schedules ms
WHERE ms.patient_id = 1 AND ms.is_active = TRUE
ON CONFLICT DO NOTHING;

-- ===================== 依从性预测数据（今日生成）=====================
-- 模拟 LSTM 输出：晚间漏服概率更高，周末略高
-- 未来第1天
INSERT INTO adherence_predictions
    (patient_id, prediction_date, target_day_offset, target_time_slot, miss_probability, model_version)
VALUES
(1, CURRENT_DATE, 1, 'morning',   0.1200, 'v1.0'),
(1, CURRENT_DATE, 1, 'afternoon', 0.2100, 'v1.0'),
(1, CURRENT_DATE, 1, 'evening',   0.3400, 'v1.0'),
-- 未来第2天（概率略升）
(1, CURRENT_DATE, 2, 'morning',   0.1500, 'v1.0'),
(1, CURRENT_DATE, 2, 'afternoon', 0.2600, 'v1.0'),
(1, CURRENT_DATE, 2, 'evening',   0.7800, 'v1.0'),  -- 高风险，触发红色警告
-- 未来第3天
(1, CURRENT_DATE, 3, 'morning',   0.1800, 'v1.0'),
(1, CURRENT_DATE, 3, 'afternoon', 0.3100, 'v1.0'),
(1, CURRENT_DATE, 3, 'evening',   0.8200, 'v1.0')   -- 高风险
ON CONFLICT ON CONSTRAINT uq_prediction DO UPDATE
    SET miss_probability = EXCLUDED.miss_probability,
        model_version    = EXCLUDED.model_version;

-- ===================== 关联规则数据（Apriori 挖掘结果）=====================
-- 基于张爷爷90天服药记录的真实规律
-- drug_id 对应：1=阿司匹林, 6=氨氯地平, 8=美托洛尔, 15=二甲双胍, 20=碳酸钙D3

-- 先清除旧规则，避免重复
DELETE FROM association_rules WHERE patient_id = 1;

INSERT INTO association_rules
    (patient_id, antecedent, consequent, support, confidence, lift, rule_description, generated_date)
VALUES
-- 规则1：服阿司匹林 → 服氨氯地平（高置信度，心血管联合用药）
(1, '[1]'::jsonb, '[6]'::jsonb,
 0.7800, 0.9200, 1.1500,
 '服用【阿司匹林】时通常也需服用【氨氯地平】，请勿遗漏',
 CURRENT_DATE),

-- 规则2：服阿司匹林+氨氯地平 → 服美托洛尔（三联心血管用药）
(1, '[1, 6]'::jsonb, '[8]'::jsonb,
 0.7200, 0.8800, 1.2300,
 '服用【阿司匹林、氨氯地平】时通常也需服用【美托洛尔】，请勿遗漏',
 CURRENT_DATE),

-- 规则3：服二甲双胍早间 → 服阿司匹林（早间联合用药规律）
(1, '[15]'::jsonb, '[1]'::jsonb,
 0.6900, 0.8500, 1.0800,
 '服用【二甲双胍】时通常也需服用【阿司匹林】，请勿遗漏',
 CURRENT_DATE),

-- 规则4：服美托洛尔 → 服碳酸钙D3（晚间联合用药）
(1, '[8]'::jsonb, '[20]'::jsonb,
 0.6100, 0.7900, 1.3200,
 '服用【美托洛尔】时通常也需服用【碳酸钙D3】，请勿遗漏',
 CURRENT_DATE),

-- 规则5：服氨氯地平+美托洛尔 → 服二甲双胍（多病共患联合用药）
(1, '[6, 8]'::jsonb, '[15]'::jsonb,
 0.5800, 0.7600, 1.1900,
 '服用【氨氯地平、美托洛尔】时通常也需服用【二甲双胍】，请勿遗漏',
 CURRENT_DATE);
