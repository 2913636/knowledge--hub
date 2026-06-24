# RAG 知识库中台

多团队知识库中台。每个团队独立 ChromaDB Collection 隔离，管理员统一管理文档和使用统计。

## 架构

```
┌─────────────────────────────────┐
│       Streamlit 统一中台         │
│  问答 │ 文档管理 │ 团队管理 │ 统计 │
└──────────────┬──────────────────┘
               │
┌──────────────┴──────────────────┐
│     多租户 RAG 引擎              │
│  团队A(Collection A)             │
│  团队B(Collection B)             │
│  团队C(Collection C)             │
└──────────────┬──────────────────┘
               │
┌──────────────┴──────────────────┐
│   SQLite 日志 + 统计             │
│  查询记录 / 检索命中率 / 活跃度   │
└─────────────────────────────────┘
```

## 功能

- **多租户隔离**：每个团队独立知识库，互不可见
- **文档管理**：上传 txt/md，自动切片入库
- **使用统计**：每次查询记录（用户/团队/问题/检索命中数）
- **管理后台**：团队创建/删除，文档管理

## 技术栈

- **检索：** ChromaDB 多 Collection
- **模型：** DeepSeek V3
- **日志：** SQLite
- **界面：** Streamlit

## 快速开始

```bash
git clone https://github.com/2913636/knowledge--hub.git
cd knowledge--hub
python -m venv venv
venv\Scripts\activate
pip install chromadb streamlit python-dotenv openai
cp .env.example .env
streamlit run main.py
```

## 项目结构

```
knowledge-hub/
├── main.py          ← Streamlit 中台（问答/文档/团队/统计 4 Tab）
├── rag_engine.py    ← 多租户 RAG 引擎
├── db/
│   └── models.py    ← SQLite 数据库 + 统计查询
└── config.py
```
