# 知识库文档目录

本目录下的 **Markdown (.md)** 文件会作为 RAG 知识库的文档来源（需先执行导入脚本进入向量库后，智能问答才会检索到）。

## 文档从哪里来？

1. **本目录下的 .md 文件**（推荐）
   - 在 `concepts/`、`faq/` 等子目录中放入或编写 `.md` 文件，例如：
     - 策略说明、选股规则、概念解释
     - 常见问题、操作说明
   - 执行一次导入脚本，将当前所有 .md 导入到 RAG 向量库：
     ```bash
     # 在项目根目录执行
     python -m backend.scripts.tools.import_documents_to_rag
     ```
   - 之后智能问答会先检索这些文档，再结合 DeepSeek 回答。

2. **行业龙头数据导入 RAG**
   - 使用脚本将行业龙头数据写入 RAG（便于问“某行业龙头有哪些”等）：
     ```bash
     python -m backend.scripts.tools.batch_import_industry_leaders --json 你的行业龙头.json --rag
     ```

3. **自行调用接口**
   - 若有其他系统，可调用 `RAGService.add_documents()` 传入 `[{ "id", "content", "metadata" }, ...]` 写入向量库。

## 当前示例文档

- `concepts/启动筛选规则.md`：启动相关筛选规则说明
- `faq/多级漏斗框架.md`：多级漏斗框架说明

新增或修改 .md 后，重新执行上面的导入脚本即可更新 RAG 检索内容。
