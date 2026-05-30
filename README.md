# GPT 内测模型情报终端

## 这是什么

2026 年 5 月 29 日 UTC 凌晨 3:30 左右，ChatGPT 网页端的模型选择器中短暂出现了大量**内部模型入口**——包含实验代号、A/B 测试分组、人格调参变体等平时不可见的隐藏模型 ID。我们在窗口期内对模型选择器的完整 DOM 进行了抓取存档，随后通过结构化提取、多维交叉比对和自动化清洗，整理出了这份包含 **1638 个去重内部模型 ID** 的情报数据集。

本仓库将这份数据以「赛博朋克风」的交互式情报终端呈现——既提供完整的原始数据和处理脚本，也提供一个开箱即用的可视化分析面板。

## 数据来源与采集方法

### 原始抓取

数据来自 ChatGPT 网页端（`chatgpt.com`）模型选择器组件的 DOM 快照。该选择器使用 Radix UI 的菜单组件，每个模型入口以 `role="menuitemradio"` 或 `role="menuitem"` 的 DOM 节点存在，部分带有 `data-has-submenu`（父级分组入口）和 badge 标签（`alpha` / `beta` / `mainline`）。

### 关键词筛选策略

由于模型选择器在一次展开中只显示当前搜索关键词匹配的条目，我们使用**穷举关键词**策略确保覆盖率：

- **26 个字母**：`a` ~ `z`，逐字母搜索
- **10 个数字**：`0` ~ `9`，捕获带版本号、日期戳、实验编号的模型
- **12 个特殊字符**：`-`（连字符）、`_`（下划线）、`.`（点号）、`+`、`=`、`'`（单引号）、`(`、`)`、`[`、`]`、`,`（逗号）、`:`（冒号）、`|`（竖杠）、`/`（斜杠）

每个关键词的搜索结果单独保存为一份 DOM 快照文件。**36 个字母数字 + 12 个特殊字符 = 48 份分列表**，理论上覆盖了所有可能出现在模型 ID 中的可打印 ASCII 字符组合。

### 为什么这套方案是全面的

- 模型 ID 的命名规范几乎必然包含字母、数字或上述特殊字符中的至少一个——单字符搜索已足够命中
- 逐字符穷举避免了「猜关键词」的遗漏风险
- 对每份分列表独立提取后做交叉去重，任何模型只要在至少一个字符搜索中出现过就会被捕获
- 对父级分组入口（带 `data-has-submenu`）单独标记，防止只记录分组名而遗漏展开后的子模型

## 数据处理流程

```
原始 DOM 快照（48 份）
    ↓ extract_clean_models.py — HTML 结构化解析 + 纯文本提取
逐文件结构化 JSON（含模型名、badge、层级关系等元数据）
    ↓ aggregate_screening_models.py — 跨文件去重合并 + 出现频次统计
去重总表（1638 个唯一模型 ID）
    ↓ fetch_openai_models.py — 拉取 OpenAI 官方 /v1/models 接口
    ↓ compare_api_and_internal_models.py — 内部 ↔ 官方名称匹配打分
    ↓ classify_api_match_tiers.py — 按匹配强度分档
    ↓ organize_model_catalog.py — 最终归类为四桶
归类后的权威数据集
    ↓ derive_model_dimensions.py — 23 维度模型名情报解析
维度分析数据集（代际、代号、能力、人格实验等）
```

### 清洗细节

- **HTML 结构化解析**：不做简单文本切割，而是通过 HTMLParser 解析 Radix UI 菜单的 DOM 树，精确提取 `menuitemradio` / `menuitem` 节点的文本内容，过滤掉 badge 标签文字（如 "alpha"）和 UI 辅助文本（如 "Thinking"、"Instant"）
- **DOM 残渣检测**：部分快照中混入了被浏览器去标签化的 DOM 属性字符串（如 Radix popper wrapper 的整段属性），通过正则检测 `data-radix-*`、`aria-*`、`pointer-events` 等标志自动识别并丢弃
- **名称归一化**：统一空白字符、去除零宽空格和 `&nbsp;`、清理引号括号等包裹字符
- **跨文件去重**：同一模型可能在多个关键词搜索中出现（如 `gpt-5.3-sonic` 同时命中 `g`、`5`、`3`、`s`、`-`、`.`），合并后保留出现次数和来源信息

### 最终归类

| 分类 | 数量 | 说明 |
|------|------|------|
| `official_api_models` | 120 | OpenAI 官方 `/v1/models` 接口返回的公开模型 |
| `internal_official_slots` | 42 | 内部名直接对应官方 API ID 或 mainline 槽位 |
| `internal_official_family_related` | 325 | 属于官方已知模型家族，但非直接官方 ID（如带版本后缀的变体） |
| `internal_experimental` | 1271 | 纯内部实验模型——A/B 测试、人格调参、研究分支、能力实验等 |
| `api_without_internal_signal` | 89 | 存在于官方 API 但未在内部选择器中出现的模型 |

### 23 维度情报解析

对每个模型 ID 的命名字符串进行正则解析，提取出：

- **代际**（generation）：gpt-4 / gpt-4o / gpt-5.1~5.5 / o1 / o3 / o4 等
- **内部代号**（codename）：big_dipper、andromeda、sonic、lupo、thinky、paragen 等 16 个
- **能力标签**（capabilities）：mmlu、code、creative_writing、math、vision 等
- **人格实验**（personality）：sycophancy、confidence、verbosity、emoji_use 等 26 种特质 × more/less 方向
- **A/B 分组**（arm_role）：control / treatment / production / baseline
- **算力档位**（compute_hint / juice_level）：high / medium / low 及数值化等级
- **模型种类**（kind）：model / research_artifact / deploy_slot
- **其他**：tier、campaign 结构、checkpoint 步数、日期标签等

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# （可选）配置 OpenAI API Key 以启用每日自动抓取官方模型列表
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 启动
python server/app.py
# 打开 http://127.0.0.1:3323
```

不配置 API Key 也能正常运行——服务端会直接展示仓库里已提交的官方模型快照，前端状态栏显示 `OFFLINE (cached)`。

## 前端功能

- **态势总览**：KPI 计数器 + 时间线柱状图 + 模型分布饼图
- **模型浏览**：官方模型 / 内测槽位 / 家族关联 / 实验泄露四类分栏，支持实时搜索和排序
- **情报洞察**（四个子页面）：
  - 总览：代际研发强度、代号星图
  - 研究分析：能力雷达图、层级旭日图
  - 人格实验：人格特质热力图、A/B 实验桑基图
  - 实验分析：算力分布矩形树图、Juice 等级分布
- **交互钻取**：点击任意图表元素可弹窗查看对应的具体模型列表
- **每日变动追踪**：自动比对官方 `/v1/models` 接口变化，记录模型新增和下线历史

## 项目结构

```
├── server/app.py              # Flask 后端（端口 3323）
├── web/index.html             # 单文件前端（赛博朋克主题）
├── scripts/                   # 数据处理管线
│   ├── extract_clean_models.py        # DOM 快照 → 结构化 JSON
│   ├── aggregate_screening_models.py  # 跨文件去重合并
│   ├── fetch_openai_models.py         # 拉取官方 /v1/models
│   ├── compare_api_and_internal_models.py  # 内部 ↔ 官方匹配
│   ├── classify_api_match_tiers.py    # 匹配强度分档
│   ├── organize_model_catalog.py      # 最终四桶归类
│   ├── derive_model_dimensions.py     # 23 维度模型名解析
│   └── model_utils.py                # 共享工具函数
├── processed/                 # 处理后的结构化数据
│   ├── organized_catalog/     # 最终归类结果（前端读取）
│   ├── insights/              # 维度分析数据
│   ├── api_compare/           # 内部 ↔ 官方比对结果
│   └── api_models/            # 官方模型快照
├── .env.example               # 环境变量模板
└── requirements.txt           # Python 依赖
```

## HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/api/summary` | 总览数据（计数、抓取状态） |
| GET | `/api/official` | 官方模型列表 |
| GET | `/api/internal` | 内部模型（支持 `?category=` 按桶筛选） |
| GET | `/api/insights` | 维度分析与交叉聚合数据 |
| GET | `/api/history` | 官方模型变动历史 |
| POST | `/api/refresh` | 手动触发重新抓取和重算 |

## 免责声明

本项目仅用于技术研究和信息归档目的。所有数据均来自公开可访问的网页端界面在特定时间窗口内的快照，不涉及任何逆向工程、API 滥用或认证信息的使用。模型 ID 本身是字符串标识符，不构成受版权保护的作品。如有任何侵权疑虑，请通过 Issue 联系。

## License

MIT
