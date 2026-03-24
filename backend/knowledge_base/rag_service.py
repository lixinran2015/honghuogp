"""
RAG服务
实现向量检索、上下文注入、结果缓存
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 国内环境优先使用 Hugging Face 镜像，避免连接 huggingface.co 超时（WinError 10060）
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("Chroma或sentence-transformers未安装，RAG功能受限")


class RAGService:
    """RAG服务类"""
    
    def __init__(self, persist_directory: Optional[str] = None):
        """
        初始化RAG服务
        
        Args:
            persist_directory: 向量数据库持久化目录，默认在项目根目录下的 .chroma_db
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("Chroma或sentence-transformers未安装，请先安装依赖：pip install chromadb sentence-transformers")
        
        # 设置持久化目录
        if persist_directory is None:
            persist_directory = str(project_root / ".chroma_db")
        
        self.persist_directory = persist_directory
        
        # 初始化Chroma客户端
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 初始化 embedding 模型（带超时，避免从 Hugging Face 下载时长时间卡住）
        self.embedder = self._load_embedder_with_timeout(timeout_seconds=45)
        
        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name="stock_knowledge_base",
            metadata={"description": "股票系统知识库"}
        )
        
        # 结果缓存（避免重复查询）
        self._query_cache = {}
        self._cache_ttl = 3600  # 缓存1小时
    
    def _load_embedder_with_timeout(self, timeout_seconds: int = 45):
        """在子线程中加载 embedding 模型，超时则放弃，避免请求卡住。"""
        result = [None]  # 用列表以便在闭包中赋值
        
        def _load():
            try:
                model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                result[0] = model
            except Exception as e:
                logger.warning(f"加载多语言模型失败: {e}")
                try:
                    result[0] = SentenceTransformer('all-MiniLM-L6-v2')
                except Exception as e2:
                    logger.warning(f"加载默认模型失败: {e2}")
        
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_load)
                future.result(timeout=timeout_seconds)
            if result[0] is not None:
                logger.info("✅ RAG服务初始化成功，使用多语言embedding模型")
                return result[0]
        except concurrent.futures.TimeoutError:
            logger.warning(
                f"⚠️ 加载embedding模型超时（{timeout_seconds}秒），RAG功能不可用。"
                "可设置环境变量 HF_ENDPOINT=https://hf-mirror.com 或提前下载模型到本地缓存。"
            )
        except Exception as e:
            logger.warning(f"加载embedding模型异常: {e}")
        return None
    
    def add_documents(self, documents: List[Dict[str, str]], collection_name: str = "stock_knowledge_base"):
        """
        添加文档到向量数据库
        
        Args:
            documents: 文档列表，每个文档包含：
                - content: 文档内容
                - metadata: 元数据（title, category, source等）
            collection_name: 集合名称
        """
        if not self.embedder:
            logger.error("Embedding模型未加载，无法添加文档")
            return False
        
        try:
            collection = self.client.get_or_create_collection(name=collection_name)
            
            # 准备数据
            ids = []
            contents = []
            metadatas = []
            
            for i, doc in enumerate(documents):
                doc_id = doc.get('id', f"doc_{int(time.time() * 1000)}_{i}")
                content = doc.get('content', '')
                metadata = doc.get('metadata', {})
                
                if not content:
                    continue
                
                ids.append(doc_id)
                contents.append(content)
                metadatas.append(metadata)
            
            if not contents:
                logger.warning("没有有效文档可添加")
                return False
            
            # 生成embeddings
            logger.info(f"正在生成 {len(contents)} 个文档的embeddings...")
            embeddings = self.embedder.encode(contents, show_progress_bar=True).tolist()
            
            # 添加到集合
            collection.add(
                ids=ids,
                documents=contents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"✅ 成功添加 {len(contents)} 个文档到知识库")
            return True
            
        except Exception as e:
            logger.error(f"添加文档失败: {e}", exc_info=True)
            return False
    
    def query(
        self,
        query_text: str,
        n_results: int = 3,
        min_similarity: float = 0.7,
        collection_name: str = "stock_knowledge_base"
    ) -> List[Dict]:
        """
        查询知识库
        
        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            min_similarity: 最小相似度阈值（Chroma使用距离，需要转换）
            collection_name: 集合名称
            
        Returns:
            List[Dict]: 查询结果列表，每个结果包含：
                - content: 文档内容
                - metadata: 元数据
                - distance: 距离（越小越相似）
        """
        if not self.embedder:
            logger.error("Embedding模型未加载，无法查询")
            return []
        
        # 检查缓存
        cache_key = f"{query_text}_{n_results}_{min_similarity}"
        if cache_key in self._query_cache:
            cached_result, cached_time = self._query_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                logger.debug(f"使用缓存的查询结果: {cache_key}")
                return cached_result
        
        try:
            collection = self.client.get_collection(name=collection_name)
            
            # 生成查询embedding
            query_embedding = self.embedder.encode([query_text])[0].tolist()
            
            # 查询（Chroma使用距离，距离越小越相似）
            # 注意：Chroma的距离是余弦距离，1-相似度，所以min_similarity需要转换为max_distance
            max_distance = 1.0 - min_similarity
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # 格式化结果
            formatted_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i] if results['distances'] else 1.0
                    similarity = 1.0 - distance
                    
                    # 只返回相似度大于阈值的结果
                    if similarity >= min_similarity:
                        formatted_results.append({
                            'id': doc_id,
                            'content': results['documents'][0][i] if results['documents'] else '',
                            'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                            'distance': distance,
                            'similarity': similarity
                        })
            
            # 缓存结果
            self._query_cache[cache_key] = (formatted_results, time.time())
            
            logger.info(f"✅ 查询完成，找到 {len(formatted_results)} 个相关文档")
            return formatted_results
            
        except Exception as e:
            logger.error(f"查询知识库失败: {e}", exc_info=True)
            return []
    
    def build_context(self, query_text: str, max_context_length: int = 1000) -> str:
        """
        构建检索上下文
        
        Args:
            query_text: 查询文本
            max_context_length: 最大上下文长度（字符数）
            
        Returns:
            str: 格式化的上下文文本
        """
        results = self.query(query_text, n_results=3, min_similarity=0.6)
        
        if not results:
            return ""
        
        context_parts = []
        current_length = 0
        
        for result in results:
            content = result['content']
            metadata = result.get('metadata', {})
            title = metadata.get('title', '未知')
            category = metadata.get('category', '未知')
            
            # 格式化文档片段
            doc_text = f"【{category}】{title}\n{content}\n"
            
            if current_length + len(doc_text) > max_context_length:
                break
            
            context_parts.append(doc_text)
            current_length += len(doc_text)
        
        return "\n".join(context_parts)
    
    def clear_cache(self):
        """清空查询缓存"""
        self._query_cache.clear()
        logger.info("✅ 查询缓存已清空")
