"""
将 backend/knowledge_base/documents/ 下的所有 .md 文档导入到 RAG 向量库（Chroma）。
导入后，智能问答会先检索这些文档作为上下文。

使用方式（在项目根目录执行）：
  python -m backend.scripts.tools.import_documents_to_rag
或：
  cd backend && python scripts/tools/import_documents_to_rag.py
"""

import logging
import sys
from pathlib import Path

# 项目根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# 文档目录：backend/knowledge_base/documents
DOCS_ROOT = project_root / "backend" / "knowledge_base" / "documents"


def _title_from_content(content: str, fallback: str) -> str:
    """从内容首行 # 标题 提取标题"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
    return fallback


def main():
    if not DOCS_ROOT.exists():
        logger.warning("知识库文档目录不存在: %s", DOCS_ROOT)
        return 0

    md_files = list(DOCS_ROOT.rglob("*.md"))
    if not md_files:
        logger.warning("未找到 .md 文件，请在 %s 下添加文档", DOCS_ROOT)
        return 0

    try:
        from backend.knowledge_base.rag_service import RAGService
    except Exception as e:
        logger.error("无法导入 RAGService: %s", e)
        return 1

    documents = []
    for path in sorted(md_files):
        try:
            rel = path.relative_to(DOCS_ROOT)
            path_key = str(rel).replace("\\", "/")
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                continue
            title = _title_from_content(content, path.stem)
            category = rel.parts[0] if len(rel.parts) > 1 else "根目录"
            documents.append({
                "id": path_key,
                "content": content,
                "metadata": {
                    "title": title,
                    "category": category,
                    "path": path_key,
                    "source": "documents",
                },
            })
            logger.info("  准备: %s -> %s", path_key, title)
        except Exception as e:
            logger.warning("跳过 %s: %s", path, e)

    if not documents:
        logger.warning("没有可导入的文档")
        return 0

    logger.info("正在初始化 RAG 并导入 %d 个文档...", len(documents))
    rag = RAGService()
    if rag.add_documents(documents):
        logger.info("✅ 成功将 documents/ 下 %d 个文档导入 RAG 知识库", len(documents))
        return 0
    logger.error("❌ 导入失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
