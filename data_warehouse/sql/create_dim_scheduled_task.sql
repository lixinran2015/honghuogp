-- 定时任务配置表
CREATE TABLE IF NOT EXISTS dim_scheduled_task (
    id SERIAL PRIMARY KEY,
    task_name VARCHAR(50) NOT NULL UNIQUE COMMENT '任务名称（唯一标识）',
    task_display_name VARCHAR(100) NOT NULL COMMENT '任务显示名称',
    task_description TEXT COMMENT '任务描述',
    
    -- 调度配置
    cron_expression VARCHAR(100) COMMENT 'Cron表达式（如：0 15 * * 1-5 表示工作日15:00）',
    schedule_time VARCHAR(20) COMMENT '简单时间配置（如：15:30，用于每日执行）',
    schedule_days VARCHAR(50) COMMENT '执行日期（如：1-5表示周一到周五，或：1,3,5表示周一三五）',
    
    -- 任务状态
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
    is_running BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否正在运行',
    
    -- 任务类型和执行信息
    task_type VARCHAR(50) NOT NULL COMMENT '任务类型（daily_update, fundamental_update等）',
    task_handler VARCHAR(200) COMMENT '任务处理函数路径（可选，用于动态调用）',
    
    -- 元数据
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    last_run_at TIMESTAMP COMMENT '最后执行时间',
    next_run_at TIMESTAMP COMMENT '下次执行时间'
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_scheduled_task_name ON dim_scheduled_task(task_name);
CREATE INDEX IF NOT EXISTS idx_scheduled_task_enabled ON dim_scheduled_task(is_enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_task_type ON dim_scheduled_task(task_type);

-- 添加注释
COMMENT ON TABLE dim_scheduled_task IS '定时任务配置表';
COMMENT ON COLUMN dim_scheduled_task.task_name IS '任务名称（唯一标识）';
COMMENT ON COLUMN dim_scheduled_task.task_display_name IS '任务显示名称';
COMMENT ON COLUMN dim_scheduled_task.task_description IS '任务描述';
COMMENT ON COLUMN dim_scheduled_task.cron_expression IS 'Cron表达式（如：0 15 * * 1-5 表示工作日15:00）';
COMMENT ON COLUMN dim_scheduled_task.schedule_time IS '简单时间配置（如：15:30，用于每日执行）';
COMMENT ON COLUMN dim_scheduled_task.schedule_days IS '执行日期（如：1-5表示周一到周五，或：1,3,5表示周一三五）';
COMMENT ON COLUMN dim_scheduled_task.is_enabled IS '是否启用';
COMMENT ON COLUMN dim_scheduled_task.is_running IS '是否正在运行';
COMMENT ON COLUMN dim_scheduled_task.task_type IS '任务类型（daily_update, fundamental_update等）';
COMMENT ON COLUMN dim_scheduled_task.task_handler IS '任务处理函数路径（可选，用于动态调用）';
COMMENT ON COLUMN dim_scheduled_task.created_at IS '创建时间';
COMMENT ON COLUMN dim_scheduled_task.updated_at IS '更新时间';
COMMENT ON COLUMN dim_scheduled_task.last_run_at IS '最后执行时间';
COMMENT ON COLUMN dim_scheduled_task.next_run_at IS '下次执行时间';

