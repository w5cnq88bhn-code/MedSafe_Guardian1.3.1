-- 药安守护 预置数据脚本
-- 包含：30种药物、15对相互作用、演示患者"张爷爷"的90天模拟服药记录

-- ===================== 药物库（30种）=====================
INSERT INTO drugs (generic_name, brand_name, category, description) VALUES
('阿司匹林',       '拜阿司匹灵',   '抗血小板药',   '用于预防心肌梗死和脑卒中，抑制血小板聚集'),
('华法林',         '可密定',       '抗凝血药',     '口服抗凝药，用于预防血栓形成，需定期监测INR'),
('氯吡格雷',       '波立维',       '抗血小板药',   '抑制血小板聚集，用于急性冠脉综合征'),
('辛伐他汀',       '舒降之',       '调脂药',       '降低LDL胆固醇，预防心血管事件'),
('阿托伐他汀',     '立普妥',       '调脂药',       '强效他汀类药物，降低总胆固醇和LDL'),
('氨氯地平',       '络活喜',       '钙通道阻滞剂', '用于高血压和心绞痛治疗'),
('硝苯地平',       '拜新同',       '钙通道阻滞剂', '控释片，用于高血压和冠心病'),
('美托洛尔',       '倍他乐克',     'β受体阻滞剂',  '用于高血压、心绞痛、心力衰竭'),
('比索洛尔',       '康忻',         'β受体阻滞剂',  '选择性β1受体阻滞剂，用于高血压和心衰'),
('依那普利',       '悦宁定',       'ACEI',         '血管紧张素转换酶抑制剂，用于高血压和心衰'),
('缬沙坦',         '代文',         'ARB',          '血管紧张素受体拮抗剂，用于高血压'),
('氢氯噻嗪',       '双氢克尿噻',   '利尿剂',       '噻嗪类利尿剂，用于高血压和水肿'),
('螺内酯',         '安体舒通',     '利尿剂',       '保钾利尿剂，用于心衰和高血压'),
('呋塞米',         '速尿',         '利尿剂',       '强效袢利尿剂，用于急性肺水肿和严重水肿'),
('二甲双胍',       '格华止',       '降糖药',       '2型糖尿病一线用药，改善胰岛素抵抗'),
('格列美脲',       '亚莫利',       '降糖药',       '磺脲类降糖药，促进胰岛素分泌'),
('阿卡波糖',       '拜唐苹',       '降糖药',       'α-葡萄糖苷酶抑制剂，降低餐后血糖'),
('胰岛素（甘精）', '来得时',       '降糖药',       '长效基础胰岛素，每日一次皮下注射'),
('左甲状腺素',     '优甲乐',       '甲状腺激素',   '用于甲状腺功能减退症替代治疗'),
('碳酸钙D3',       '钙尔奇D',      '补钙药',       '补充钙和维生素D3，预防骨质疏松'),
('阿仑膦酸钠',     '福善美',       '抗骨质疏松药', '双膦酸盐类，抑制骨吸收，每周一次'),
('奥美拉唑',       '洛赛克',       '质子泵抑制剂', '抑制胃酸分泌，用于胃溃疡和反流性食管炎'),
('雷贝拉唑',       '波利特',       '质子泵抑制剂', '强效质子泵抑制剂，用于消化性溃疡'),
('多潘立酮',       '吗丁啉',       '促胃动力药',   '促进胃排空，用于恶心呕吐和消化不良'),
('地高辛',         '狄戈辛',       '强心苷',       '用于心力衰竭和心房颤动，治疗窗窄'),
('胺碘酮',         '可达龙',       '抗心律失常药', '广谱抗心律失常药，用于室性和室上性心律失常'),
('氯化钾',         '补达秀',       '电解质补充',   '补充钾离子，预防低钾血症'),
('布洛芬',         '芬必得',       'NSAIDs',       '非甾体抗炎药，用于疼痛和发热'),
('塞来昔布',       '西乐葆',       'NSAIDs',       'COX-2选择性抑制剂，胃肠道副作用较小'),
('氯雷他定',       '开瑞坦',       '抗组胺药',     '第二代抗组胺药，用于过敏性鼻炎和荨麻疹');

-- ===================== 药物相互作用（15对）=====================
-- 注意：drug_a_id < drug_b_id
INSERT INTO drug_interactions (drug_a_id, drug_b_id, severity, warning_text, advice) VALUES
-- 华法林(2) + 阿司匹林(1) → 出血风险极高
(1, 2, 'high',   '阿司匹林与华法林联用显著增加出血风险，可能导致严重内出血或颅内出血。',
                  '避免联用；如必须使用，需密切监测INR和出血症状，考虑使用质子泵抑制剂保护胃黏膜。'),
-- 华法林(2) + 氯吡格雷(3) → 出血风险高
(2, 3, 'high',   '华法林与氯吡格雷联用（双联抗栓）大幅增加出血风险。',
                  '仅在明确适应症（如冠脉支架术后）下使用，需严密监测出血，疗程尽量缩短。'),
-- 华法林(2) + 布洛芬(28) → 出血风险高
(2, 28, 'high',  '布洛芬抑制血小板功能并可能损伤胃黏膜，与华法林联用出血风险极高。',
                  '禁止联用；疼痛治疗可考虑对乙酰氨基酚替代。'),
-- 地高辛(25) + 胺碘酮(26) → 地高辛中毒
(25, 26, 'high', '胺碘酮抑制地高辛肾脏排泄，使地高辛血药浓度升高50-100%，可能导致中毒。',
                  '联用时地高辛剂量应减少30-50%，密切监测地高辛血药浓度和心电图。'),
-- 地高辛(25) + 呋塞米(14) → 低钾致地高辛毒性
(14, 25, 'high', '呋塞米引起低钾血症，低钾状态下地高辛毒性显著增强，可能导致严重心律失常。',
                  '联用时必须同时补钾，定期监测血钾和地高辛浓度。'),
-- 辛伐他汀(4) + 胺碘酮(26) → 横纹肌溶解
(4, 26, 'high',  '胺碘酮抑制CYP3A4，使辛伐他汀血药浓度升高，横纹肌溶解风险增加。',
                  '联用时辛伐他汀剂量不超过20mg/天，或换用受CYP3A4影响较小的他汀（如普伐他汀）。'),
-- 美托洛尔(8) + 维拉帕米（未在列表，用胺碘酮代替）
-- 美托洛尔(8) + 胺碘酮(26) → 心动过缓
(8, 26, 'medium','美托洛尔与胺碘酮联用可能导致严重心动过缓和房室传导阻滞。',
                  '联用时密切监测心率和心电图，心率<50次/分时需减量或停药。'),
-- 依那普利(10) + 螺内酯(13) → 高钾血症
(10, 13, 'medium','ACEI与保钾利尿剂联用可能导致高钾血症，尤其在肾功能不全患者中。',
                   '定期监测血钾，避免同时补钾，肾功能不全患者慎用。'),
-- 二甲双胍(15) + 碘造影剂（用呋塞米代替场景）
-- 格列美脲(16) + 布洛芬(28) → 低血糖风险
(16, 28, 'medium','布洛芬可能增强磺脲类药物的降糖作用，增加低血糖风险。',
                   '联用时加强血糖监测，注意低血糖症状。'),
-- 阿司匹林(1) + 布洛芬(28) → 竞争性拮抗
(1, 28, 'medium','布洛芬可能竞争性拮抗阿司匹林的抗血小板作用，降低心血管保护效果。',
                  '如需止痛，建议在服用阿司匹林前至少30分钟服用布洛芬，或改用对乙酰氨基酚。'),
-- 左甲状腺素(19) + 碳酸钙(20) → 吸收减少
(19, 20, 'medium','碳酸钙与左甲状腺素同服会减少后者吸收，降低疗效。',
                   '两药服用间隔至少4小时，建议左甲状腺素空腹服用。'),
-- 左甲状腺素(19) + 阿仑膦酸钠(21) → 吸收干扰
(19, 21, 'low',  '阿仑膦酸钠可能轻微影响左甲状腺素吸收。',
                  '两药服用间隔至少30分钟。'),
-- 奥美拉唑(22) + 氯吡格雷(3) → 降低氯吡格雷活性
(3, 22, 'medium','奥美拉唑抑制CYP2C19，减少氯吡格雷转化为活性代谢物，降低抗血小板效果。',
                  '如需质子泵抑制剂，优先选择泮托拉唑或雷贝拉唑（对CYP2C19影响较小）。'),
-- 氢氯噻嗪(12) + 格列美脲(16) → 血糖升高
(12, 16, 'low',  '噻嗪类利尿剂可能升高血糖，削弱降糖药效果。',
                  '联用时加强血糖监测，必要时调整降糖药剂量。'),
-- 阿卡波糖(17) + 多潘立酮(24) → 疗效降低
(17, 24, 'low',  '促胃动力药加速胃排空，可能降低阿卡波糖延缓碳水化合物吸收的效果。',
                  '尽量避免同时服用，如需联用，加强餐后血糖监测。');

-- ===================== 演示患者"张爷爷" =====================
INSERT INTO patients (openid, name, phone, birth_year, diagnosis_disease)
VALUES ('demo_openid_zhang', '张建国', '13800138000', 1948,
        '高血压3级、2型糖尿病、冠心病、慢性心力衰竭');

-- 演示子女账号
INSERT INTO patients (openid, name, phone, birth_year, diagnosis_disease)
VALUES ('demo_openid_child', '张明', '13900139000', 1975, NULL);

INSERT INTO caregivers (caregiver_openid, patient_id, relationship)
VALUES ('demo_openid_child', 1, 'child');

-- 张爷爷的过敏记录
INSERT INTO allergies (patient_id, drug_id_or_ingredient, reaction_type, added_date)
VALUES
(1, '青霉素',   '过敏性休克', '2020-01-01'),
(1, '磺胺类',   '皮疹',       '2018-06-15'),
(1, '塞来昔布', '胃肠道不适', '2022-03-10');

-- 张爷爷的服药计划（5种药）
INSERT INTO medication_schedules
    (patient_id, drug_id, dosage, dosage_unit, frequency, time_of_day, time_point, start_date, end_date, is_active)
VALUES
-- 阿司匹林 100mg 每日1次 早上8:00
(1, 1,  100.0, 'mg', 1, 'morning',   '08:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
-- 美托洛尔 25mg 每日2次 早/晚
(1, 8,   25.0, 'mg', 2, 'morning',   '08:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
(1, 8,   25.0, 'mg', 2, 'evening',   '20:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
-- 二甲双胍 500mg 每日3次 早/中/晚
(1, 15, 500.0, 'mg', 3, 'morning',   '08:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
(1, 15, 500.0, 'mg', 3, 'afternoon', '12:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
(1, 15, 500.0, 'mg', 3, 'evening',   '18:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
-- 氨氯地平 5mg 每日1次 早上
(1, 6,    5.0, 'mg', 1, 'morning',   '08:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE),
-- 碳酸钙D3 600mg 每日1次 晚上
(1, 20, 600.0, 'mg', 1, 'evening',   '20:00:00', CURRENT_DATE - INTERVAL '90 days', NULL, TRUE);

-- ===================== 90天模拟服药记录 =====================
-- 使用 generate_series 生成记录，引入规律漏服模式：
-- 1. 基础漏服率约15%
-- 2. 晚间漏服率更高（约25%）
-- 3. 周末漏服率略高
-- 4. 中午（午饭后）漏服率约20%

DO $$
DECLARE
    v_day       DATE;
    v_schedule  RECORD;
    v_sched_ts  TIMESTAMP;
    v_status    VARCHAR(20);
    v_taken_ts  TIMESTAMP;
    v_rand      FLOAT;
    v_miss_rate FLOAT;
BEGIN
    FOR v_day IN
        SELECT d::DATE FROM generate_series(
            CURRENT_DATE - INTERVAL '90 days',
            CURRENT_DATE - INTERVAL '1 day',
            '1 day'::INTERVAL
        ) d
    LOOP
        FOR v_schedule IN
            SELECT id, drug_id, dosage, time_point, time_of_day
            FROM medication_schedules
            WHERE patient_id = 1 AND is_active = TRUE
        LOOP
            v_sched_ts := v_day + v_schedule.time_point;

            -- 计算漏服概率
            v_miss_rate := 0.12;  -- 基础漏服率
            IF v_schedule.time_of_day = 'evening' THEN
                v_miss_rate := v_miss_rate + 0.10;  -- 晚间+10%
            END IF;
            IF v_schedule.time_of_day = 'afternoon' THEN
                v_miss_rate := v_miss_rate + 0.08;  -- 午间+8%
            END IF;
            IF EXTRACT(DOW FROM v_day) IN (0, 6) THEN
                v_miss_rate := v_miss_rate + 0.05;  -- 周末+5%
            END IF;

            v_rand := random();
            IF v_rand < v_miss_rate THEN
                v_status   := 'missed';
                v_taken_ts := NULL;
            ELSE
                v_status   := 'taken';
                -- 实际服药时间在计划时间前后15分钟内随机
                v_taken_ts := v_sched_ts + (random() * 30 - 15) * INTERVAL '1 minute';
            END IF;

            INSERT INTO medication_logs
                (patient_id, drug_id, schedule_id, scheduled_time, actual_taken_time, status, taken_dose, source)
            VALUES
                (1, v_schedule.drug_id, v_schedule.id, v_sched_ts, v_taken_ts, v_status, v_schedule.dosage, 'manual');
        END LOOP;
    END LOOP;
END $$;
