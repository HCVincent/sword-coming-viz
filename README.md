# 剑来可视化系统

围绕《剑来》前三季原著构建的离线可视化与编剧分析工作台。当前仓库包含原著预处理、规则抽取、统一知识库、前端可视化，以及角色弧光、冲突链、伏笔回收等编剧视图。

## 内容范围

- 原著输入：仓库根目录下的三份原著文档
- 数据产物：`data/` 下的章节索引、统一知识库、编剧分析数据
- 前端应用：`visualization/`
- 离线构建脚本：`scripts/`

## 目录结构

```text
.
├── data/                        # 统一知识库与编剧分析数据
├── model/                       # 通用知识模型
├── prompts/                     # 小说抽取提示词
├── scripts/                     # 构建与同步脚本
├── swordcoming_pipeline/        # 抽取辅助工具
├── tests/                       # Python 测试
├── visualization/               # React + Vite 前端
├── 剑来第一季原著.doc
├── 剑来第二季原著.docx
└── 剑来第三季原著.docx
```

## 本地使用

### 1. 构建离线数据

```powershell
cd D:\code\NovelVisualization\SwordComing
python scripts\build_swordcoming_book.py --source-dir .
python scripts\build_swordcoming_offline_data.py --sync
```

### 2. 启动前端

```powershell
cd D:\code\NovelVisualization\SwordComing\visualization
npm install
npm run dev
```

默认地址通常是 [http://localhost:5173](http://localhost:5173)。

### 3. 运行校验

```powershell
cd D:\code\NovelVisualization\SwordComing
uv run pytest
python scripts\validate_unified_knowledge.py data\unified_knowledge.json
python scripts\validate_unified_knowledge.py data\writer_insights.json
cd visualization
npm run build
```

## 主要数据文件

- `data/book_config.json`：书籍配置、快速筛选、默认视图
- `data/unit_progress_index.json`：章节与叙事进度索引
- `data/unified_knowledge.json`：人物、地点、事件、关系的统一知识库
- `data/writer_insights.json`：角色弧光、冲突链、伏笔回收等编剧分析数据
- `data/chapter_synopses.json`：每章概要、关键进展、出场角色与叙事功能
- `data/key_events_index.json`：每章关键事件排名索引（含重要度评分与涉及角色）
- `data/swordcoming_core_cast.json`：核心角色、地点、关系规则与编剧聚焦配置
- `data/swordcoming_manual_overrides.json`：人工覆写与消歧规则

## 在线模型抽取

仓库保留了可选的大模型抽取入口 `knowledge_extraction.py`。如果要使用该链路，需要在本地 `.env` 中配置：

- `DEEPSEEK_API_KEY`

默认的离线规则链路不依赖 API Key。

## 许可证

本仓库按 GPLv3 许可证发布，详见 [LICENSE](LICENSE)。
