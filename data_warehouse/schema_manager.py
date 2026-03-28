"""
数据库Schema管理
支持多服务的数据库隔离
"""
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateSchema
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


class SchemaManager:
    """Schema管理器"""

    SCHEMAS = {
        'short_term': 'st',
        'long_term': 'lt',
        'common': 'public'
    }

    def __init__(self, db_url: str = None):
        if db_url is None:
            db_url = self._get_db_url()
        self.engine = create_engine(db_url)

    def _get_db_url(self) -> str:
        """获取数据库URL"""
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_user = os.environ.get('DB_USER', 'postgres')
            db_pass = os.environ.get('DB_PASSWORD', '')
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'quantitative_trading')
            db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        return db_url

    def create_schemas(self):
        """创建所有需要的schema"""
        with self.engine.connect() as conn:
            for name, schema in self.SCHEMAS.items():
                if schema != 'public':
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                    print(f"✅ Schema created: {schema}")
            conn.commit()

    def drop_schemas(self):
        """删除所有非public schema"""
        with self.engine.connect() as conn:
            for name, schema in self.SCHEMAS.items():
                if schema != 'public':
                    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                    print(f"🗑️  Schema dropped: {schema}")
            conn.commit()

    def set_search_path(self, service_type: str):
        """设置搜索路径"""
        schema = self.SCHEMAS.get(service_type, 'public')
        with self.engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))

    def list_schemas(self):
        """列出所有schema"""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema')"
            ))
            schemas = [row[0] for row in result]
            print("📋 Existing schemas:")
            for schema in schemas:
                print(f"   - {schema}")
            return schemas


def init_schemas():
    """初始化所有schema"""
    manager = SchemaManager()
    manager.create_schemas()
    print("✅ All schemas initialized")


def reset_schemas():
    """重置所有schema"""
    manager = SchemaManager()
    manager.drop_schemas()
    manager.create_schemas()
    print("✅ All schemas reset")


def list_schemas():
    """列出所有schema"""
    manager = SchemaManager()
    return manager.list_schemas()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Database Schema Manager')
    parser.add_argument('command', choices=['init', 'reset', 'drop', 'list'], help='Command to execute')
    args = parser.parse_args()

    if args.command == 'init':
        init_schemas()
    elif args.command == 'reset':
        confirm = input("⚠️  This will drop all data in st and lt schemas. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            reset_schemas()
        else:
            print("Cancelled")
    elif args.command == 'drop':
        confirm = input("⚠️  This will drop all data in st and lt schemas. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            manager = SchemaManager()
            manager.drop_schemas()
        else:
            print("Cancelled")
    elif args.command == 'list':
        list_schemas()
