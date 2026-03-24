-- 扩展 fact_fundamental 表，支持排雷检查所需字段（利息偿付、商誉、审计）
-- 运行: psql -U postgres -d your_db -f migrations/add_fact_fundamental_risk_columns.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fact_fundamental' AND column_name='operate_profit') THEN
    ALTER TABLE fact_fundamental ADD COLUMN operate_profit NUMERIC(20,4);
    COMMENT ON COLUMN fact_fundamental.operate_profit IS '营业利润（元）';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fact_fundamental' AND column_name='fin_exp') THEN
    ALTER TABLE fact_fundamental ADD COLUMN fin_exp NUMERIC(20,4);
    COMMENT ON COLUMN fact_fundamental.fin_exp IS '财务费用（元）';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fact_fundamental' AND column_name='goodwill') THEN
    ALTER TABLE fact_fundamental ADD COLUMN goodwill NUMERIC(20,4);
    COMMENT ON COLUMN fact_fundamental.goodwill IS '商誉（元）';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fact_fundamental' AND column_name='total_equity') THEN
    ALTER TABLE fact_fundamental ADD COLUMN total_equity NUMERIC(20,4);
    COMMENT ON COLUMN fact_fundamental.total_equity IS '归属母公司净资产（元）';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fact_fundamental' AND column_name='audit_result') THEN
    ALTER TABLE fact_fundamental ADD COLUMN audit_result VARCHAR(200);
    COMMENT ON COLUMN fact_fundamental.audit_result IS '审计意见';
  END IF;
END $$;
