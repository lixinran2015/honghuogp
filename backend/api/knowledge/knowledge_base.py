"""
知识库文档 API
提供文档列表与文档内容，供前端浏览 backend/knowledge_base/documents/ 下的 Markdown
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/knowledge-base", tags=["知识库"])
logger = logging.getLogger(__name__)

# 文档根目录：backend/knowledge_base/documents
_DOCS_ROOT = Path(__file__).resolve().parent.parent / "knowledge_base" / "documents"


def _safe_relative_path(rel: str) -> Path:
    """解析相对路径，禁止 .. 越界"""
    p = (_DOCS_ROOT / rel).resolve()
    if not str(p).startswith(str(_DOCS_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="无效的文档路径")
    return p


def _title_from_content(content: str, fallback: str) -> str:
    """从内容首行 # 标题 提取标题"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
    return fallback


@router.get("/documents")
async def list_documents():
    """
    获取知识库文档列表
    扫描 documents 下所有 .md 文件，按目录分组返回
    """
    if not _DOCS_ROOT.exists():
        logger.warning(f"知识库目录不存在: {_DOCS_ROOT}")
        return {"documents": [], "categories": []}
    result = []
    seen = set()
    for path in sorted(_DOCS_ROOT.rglob("*.md")):
        try:
            rel = path.relative_to(_DOCS_ROOT)
            path_key = str(rel).replace("\\", "/")
            if path_key in seen:
                continue
            seen.add(path_key)
            # 用第一行 # 标题 或 文件名作为 title
            try:
                raw = path.read_text(encoding="utf-8")
                title = _title_from_content(raw, path.stem)
            except Exception as e:
                logger.debug("读取文件标题失败 %s: %s", path, e)
                title = path.stem
            category = rel.parts[0] if len(rel.parts) > 1 else "根目录"
            result.append({
                "id": path_key,
                "path": path_key,
                "title": title,
                "category": category,
            })
        except Exception as e:
            logger.debug(f"跳过 {path}: {e}")
            continue
    categories = sorted({r["category"] for r in result})
    return {"documents": result, "categories": categories}


@router.get("/documents/content")
async def get_document_content(
    path: str = Query(..., description="文档相对路径，如 concepts/启动筛选规则.md")
):
    """
    获取单篇文档内容（Markdown 原文）
    """
    path = path.strip()
    if not path or ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="无效的文档路径")
    try:
        full = _safe_relative_path(path)
        if not full.is_file():
            raise HTTPException(status_code=404, detail="文档不存在")
        content = full.read_text(encoding="utf-8")
        title = _title_from_content(content, full.stem)
        return {"path": path, "title": title, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"读取文档失败: {path}")
        raise HTTPException(status_code=500, detail="读取文档失败")


@router.post("/import-to-rag")
async def import_documents_to_rag():
    """
    将 knowledge_base/documents/ 下所有 .md 文档导入到 RAG 向量库。
    导入后智能问答会先检索这些文档作为上下文。
    """
    if not _DOCS_ROOT.exists():
        raise HTTPException(status_code=400, detail="知识库文档目录不存在，请联系管理员")
    md_files = list(_DOCS_ROOT.rglob("*.md"))
    if not md_files:
        raise HTTPException(status_code=400, detail="未找到 .md 文件，请先在 documents 目录下添加文档")
    documents = []
    for path in sorted(md_files):
        try:
            rel = path.relative_to(_DOCS_ROOT)
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
        except Exception as e:
            logger.warning("跳过 %s: %s", path, e)
    if not documents:
        raise HTTPException(status_code=400, detail="没有可导入的文档")
    try:
        from backend.knowledge_base.rag_service import RAGService
        rag = RAGService()
        if rag.add_documents(documents):
            return {"success": True, "message": f"已成功将 {len(documents)} 个文档导入 RAG 知识库", "count": len(documents)}
        return {"success": False, "message": "RAG 写入失败", "count": 0}
    except ImportError as e:
        logger.exception("RAG 依赖未安装")
        raise HTTPException(status_code=503, detail="RAG 依赖未安装（需 chromadb、sentence-transformers），请先安装后重试")
    except Exception as e:
        logger.exception("导入 RAG 失败")
        raise HTTPException(status_code=500, detail="导入失败，请稍后重试")


@router.post("/import-industry-leaders-to-rag")
async def import_industry_leaders_to_rag():
    """
    将板块龙头管理（dim_industry_leader）中的数据同步到 RAG 知识库。
    智能问答在回答「某行业龙头有哪些」等问题时会检索到与管理页一致的龙头数据。
    """
    from datetime import datetime
    from data_warehouse.service.warehouse_service import WarehouseService
    from sqlalchemy import text

    try:
        ws = WarehouseService()
        session = ws.get_session()
        try:
            rows = session.execute(
                text("""
                    SELECT ts_code, stock_name, industry, sector_name, leader_type, leader_reason, main_business
                    FROM dim_industry_leader
                    WHERE is_active = TRUE
                    ORDER BY industry, leader_type, ts_code
                """)
            ).fetchall()
        finally:
            session.close()
    except Exception as e:
        logger.exception("查询 dim_industry_leader 失败")
        raise HTTPException(status_code=500, detail="查询龙头数据失败，请稍后重试")

    if not rows:
        raise HTTPException(status_code=400, detail="板块龙头管理中暂无有效数据（is_active=TRUE），请先在板块龙头管理页添加数据后再同步")

    # 按行业分组，与 batch_import 的文档格式一致
    by_industry = {}
    for row in rows:
        ts_code, stock_name, industry, sector_name, leader_type, leader_reason, main_business = row
        industry = (industry or "").strip() or "未分类"
        sector_name = (sector_name or industry)
        leader_type = (leader_type or "行业龙头").strip()
        reason = (leader_reason or "").strip()
        main_business = (main_business or "").strip()
        if industry not in by_industry:
            by_industry[industry] = {"sector_name": sector_name, "leaders": []}
        leader_info = f"- {stock_name} ({ts_code}): {leader_type}，{reason}"
        if main_business:
            leader_info += f"，主营业务：{main_business}"
        by_industry[industry]["leaders"].append(leader_info)

    documents = []
    for industry, data in sorted(by_industry.items()):
        sector_name = data["sector_name"]
        leader_list = data["leaders"]
        content = f"""【{industry}】行业龙头股票列表

{sector_name}行业的龙头股票包括：

{chr(10).join(leader_list)}

这些股票在各自行业中具有领先地位，通常具有以下特征：
1. 市场份额领先
2. 技术或成本优势明显
3. 品牌影响力强
4. 财务状况稳健
"""
        documents.append({
            "id": f"industry_leader_{industry}",
            "content": content,
            "metadata": {
                "title": f"{industry}行业龙头",
                "category": "行业龙头",
                "industry": industry,
                "sector_name": sector_name,
                "leader_count": len(leader_list),
                "source": "dim_industry_leader",
                "updated_at": datetime.now().isoformat(),
            },
        })

    try:
        from backend.knowledge_base.rag_service import RAGService
        rag = RAGService()
        if rag.add_documents(documents):
            return {
                "success": True,
                "message": f"已成功将板块龙头管理中的 {len(documents)} 个行业、共 {len(rows)} 条龙头同步到 RAG 知识库",
                "count": len(documents),
                "leader_count": len(rows),
            }
        return {"success": False, "message": "RAG 写入失败", "count": 0, "leader_count": 0}
    except ImportError:
        logger.exception("RAG 依赖未安装")
        raise HTTPException(status_code=503, detail="RAG 依赖未安装（需 chromadb、sentence-transformers），请先安装后重试")
    except Exception as e:
        logger.exception("同步龙头到 RAG 失败")
        raise HTTPException(status_code=500, detail="同步失败，请稍后重试")
