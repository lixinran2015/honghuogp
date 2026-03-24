-- 龙头诊断结果表
-- 存储AI生成的龙头诊断结果，避免重复调用API

CREATE TABLE IF NOT EXISTS fact_leader_diagnosis (
    id BIGSERIAL PRIMARY KEY,
    
    -- 股票信息
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    
    -- 诊断结果（JSON格式）
    diagnosis_result JSONB NOT NULL,
    
    -- 元数据
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    
    -- 唯一约束：同一股票同一日期只能有一条诊断记录
    CONSTRAINT uk_leader_diagnosis_ts_date UNIQUE (ts_code, trade_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_leader_diagnosis_ts_code ON fact_leader_diagnosis(ts_code);
CREATE INDEX IF NOT EXISTS idx_leader_diagnosis_trade_date ON fact_leader_diagnosis(trade_date);
CREATE INDEX IF NOT EXISTS idx_leader_diagnosis_generated_at ON fact_leader_diagnosis(generated_at);

-- 添加注释
COMMENT ON TABLE fact_leader_diagnosis IS '龙头诊断结果表（AI生成）';
COMMENT ON COLUMN fact_leader_diagnosis.ts_code IS '股票代码';
COMMENT ON COLUMN fact_leader_diagnosis.trade_date IS '交易日期';
COMMENT ON COLUMN fact_leader_diagnosis.diagnosis_result IS '诊断结果（JSON）：包含analysis, level1_logic, level2_market, level3_timing, recommendation等';
COMMENT ON COLUMN fact_leader_diagnosis.generated_at IS '生成时间';
COMMENT ON COLUMN fact_leader_diagnosis.prompt_tokens IS 'Prompt token数量（输入token，用于计算成本）';
COMMENT ON COLUMN fact_leader_diagnosis.completion_tokens IS 'Completion token数量（输出token，通常比输入更贵）';
COMMENT ON COLUMN fact_leader_diagnosis.total_tokens IS '总token数量（prompt_tokens + completion_tokens，用于成本统计和预算管理）';

-- Token字段的意义和价值：
-- 1. 成本追踪：DeepSeek API按token计费，存储这些数据可以：
--    - 计算每次诊断的实际成本（例如：prompt $0.14/1M tokens, completion $0.56/1M tokens）
--    - 统计每日/每月API使用量和费用
--    - 设置预算预警和成本控制
--
-- 2. 使用分析：
--    - 分析哪些诊断消耗了更多token（可能是prompt过长或响应过长）
--    - 识别异常高消耗的诊断（可能存在问题需要优化）
--    - 评估系统整体API使用效率
--
-- 3. 优化参考：
--    - prompt_tokens高：说明输入数据量大，可以考虑精简prompt
--    - completion_tokens高：说明AI生成了较长响应，可以调整max_tokens限制
--    - 对比不同诊断的token消耗，优化prompt设计
--
-- 4. 性能监控：
--    - token数量间接反映响应长度和复杂度
--    - 监控token使用趋势，预测未来成本
--    - 识别token消耗异常（可能表示API调用异常或prompt设计问题）
--
-- 5. 历史记录：
--    - 保留历史使用数据，便于分析使用趋势
--    - 支持成本报表和审计
--    - 为未来功能扩展（如成本统计页面）提供数据基础
