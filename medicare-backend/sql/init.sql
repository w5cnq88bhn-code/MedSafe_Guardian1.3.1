-- 药安守护 数据库初始化脚本
-- PostgreSQL 15+

-- ===================== 扩展 =====================
-- pg_trgm：支持中文药物名称的模糊搜索（LIKE '%关键词%' 走索引）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 患者表
CREATE TABLE IF NOT EXISTS patients (
    id          SERIAL PRIMARY KEY,
    openid      VARCHAR(64) NOT NULL UNIQUE,
    name        VARCHAR(50),
    phone       VARCHAR(20),
    birth_year  SMALLINT,
    diagnosis_disease TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 子女/家属绑定表
CREATE TABLE IF NOT EXISTS caregivers (
    id               SERIAL PRIMARY KEY,
    caregiver_openid VARCHAR(64) NOT NULL,
    patient_id       INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    relationship     VARCHAR(20) DEFAULT 'family',
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (caregiver_openid, patient_id)
);

-- 药物基础库
CREATE TABLE IF NOT EXISTS drugs (
    id           SERIAL PRIMARY KEY,
    generic_name VARCHAR(100) NOT NULL,
    brand_name   VARCHAR(100),
    category     VARCHAR(50),
    description  TEXT
);

-- 药物相互作用表
-- 注意：插入数据时必须保证 drug_a_id < drug_b_id，避免重复存储同一对药物的相互作用。
-- 业务层插入前应执行：if drug_a_id > drug_b_id: swap(drug_a_id, drug_b_id)
CREATE TABLE IF NOT EXISTS drug_interactions (
    id           SERIAL PRIMARY KEY,
    drug_a_id    INT NOT NULL REFERENCES drugs(id),
    drug_b_id    INT NOT NULL REFERENCES drugs(id),
    severity     VARCHAR(10) NOT NULL CHECK (severity IN ('high','medium','low')),
    warning_text TEXT NOT NULL,
    advice       TEXT,
    CHECK (drug_a_id < drug_b_id)  -- 强制顺序，避免 (A,B) 和 (B,A) 重复存储
);

-- 服药计划表
-- time_of_day 与 time_point 存在一定冗余，但 time_of_day 便于按时段分组展示，
-- time_point 用于精确触发提醒，两者共存是合理的。
CREATE TABLE IF NOT EXISTS medication_schedules (
    id           SERIAL PRIMARY KEY,
    patient_id   INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    drug_id      INT NOT NULL REFERENCES drugs(id),
    dosage       DECIMAL(8,2) NOT NULL,
    dosage_unit  VARCHAR(20) NOT NULL DEFAULT 'mg',
    frequency    SMALLINT NOT NULL DEFAULT 1 CHECK (frequency IN (1,2,3)),
    time_of_day  VARCHAR(20) NOT NULL CHECK (time_of_day IN ('morning','afternoon','evening')),
    time_point   TIME NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 服药记录表
-- schedule_id 使用 ON DELETE SET NULL：删除服药计划时保留历史记录，仅解除关联。
CREATE TABLE IF NOT EXISTS medication_logs (
    id                SERIAL PRIMARY KEY,
    patient_id        INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    drug_id           INT NOT NULL REFERENCES drugs(id),
    schedule_id       INT REFERENCES medication_schedules(id) ON DELETE SET NULL,
    scheduled_time    TIMESTAMP NOT NULL,
    actual_taken_time TIMESTAMP,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','taken','missed')),
    taken_dose        DECIMAL(8,2),
    source            VARCHAR(20) NOT NULL DEFAULT 'manual',
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 过敏记录表
CREATE TABLE IF NOT EXISTS allergies (
    id                    SERIAL PRIMARY KEY,
    patient_id            INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    drug_id_or_ingredient VARCHAR(100) NOT NULL,
    reaction_type         VARCHAR(100),
    added_date            DATE NOT NULL DEFAULT CURRENT_DATE
);

-- 依从性预测表
CREATE TABLE IF NOT EXISTS adherence_predictions (
    id                SERIAL PRIMARY KEY,
    patient_id        INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    prediction_date   DATE NOT NULL,
    target_day_offset SMALLINT NOT NULL CHECK (target_day_offset IN (1,2,3)),
    target_time_slot  VARCHAR(20) NOT NULL CHECK (target_time_slot IN ('morning','afternoon','evening')),
    miss_probability  DECIMAL(5,4) NOT NULL,
    model_version     VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_prediction UNIQUE (patient_id, prediction_date, target_day_offset, target_time_slot)
);

-- 关联规则表
-- antecedent / consequent 存储药物 ID 数组，格式示例：[1, 3]
-- 表示"服用药物ID=1时，通常也服用药物ID=3"
CREATE TABLE IF NOT EXISTS association_rules (
    id               SERIAL PRIMARY KEY,
    patient_id       INT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    antecedent       JSONB NOT NULL,   -- 前件药物 ID 数组，如 [1, 3]
    consequent       JSONB NOT NULL,   -- 后件药物 ID 数组，如 [5]
    support          DECIMAL(5,4) NOT NULL,
    confidence       DECIMAL(5,4) NOT NULL,
    lift             DECIMAL(8,4) NOT NULL,
    rule_description TEXT NOT NULL,
    generated_date   DATE NOT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ===================== 索引 =====================

-- 服药记录：按患者+时间查询（统计、历史页面高频）
CREATE INDEX idx_logs_patient_time     ON medication_logs(patient_id, scheduled_time DESC);
-- 服药记录：漏服检测任务扫描 pending 状态（部分索引，只索引 pending 行）
CREATE INDEX idx_logs_status_pending   ON medication_logs(status) WHERE status = 'pending';
-- 服药计划：按患者查询有效计划
CREATE INDEX idx_schedules_patient_act ON medication_schedules(patient_id) WHERE is_active = TRUE;
-- 预测结果：按患者+日期查询
CREATE INDEX idx_predictions_lookup    ON adherence_predictions(patient_id, prediction_date);
-- 关联规则：按患者取最新规则
CREATE INDEX idx_rules_patient_date    ON association_rules(patient_id, generated_date DESC);

-- 药物搜索：使用 pg_trgm 支持中文模糊搜索（LIKE '%阿司匹林%' 走索引）
-- 同时覆盖 generic_name 和 brand_name
CREATE INDEX idx_drugs_generic_trgm    ON drugs USING gin(generic_name gin_trgm_ops);
CREATE INDEX idx_drugs_brand_trgm      ON drugs USING gin(brand_name gin_trgm_ops);

-- patients.openid：UNIQUE 约束已隐式创建索引，此处显式声明提升可读性
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_openid ON patients(openid);
-- caregivers：子女查询自己绑定的患者列表
CREATE INDEX idx_caregivers_openid     ON caregivers(caregiver_openid);
