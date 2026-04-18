# Augur · 占卜师

> 一个由传奇投资大师组成的委员会，随召随到。给它一个标的，读取神谕。

```
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
```

**Augur**（占卜师），古罗马祭司，通过观察飞鸟方位解读神意。这位 augur 不读鸟，
只读盘。

给定一个标的（AAPL、TSLA、BTC……），系统召集 15 位以上历史投资大师——巴菲特、
芒格、格雷厄姆、索罗斯、达利欧、西蒙斯、凯茜·伍德……——让他们各自研读同一份
市场快照、以各自的投资哲学独立思考、独立投票。最终合成一份报告，暴露共识、
揭示分歧、凸显异见。

兼容任意 **OpenAI 兼容** 接口（OpenAI、DeepSeek、Moonshot、Together、Groq、
vLLM、Ollama……）。可选配 **Exa 网页搜索** 为快照接入实时数据。

> [English README](./README.md)

**本项目不构成投资建议。** 仅供研究与娱乐。牛熊占卜是用来思考的，不是用来交
易的。

---

## 核心价值

单个 LLM 给出的"平均意见"往往中庸乏味。强制多个鲜明人格独立决策再统计，可以：
- **暴露分歧**：价值派与成长派对同一标的的真实分歧
- **识别共识**：跨学派一致的结论才有参考意义
- **展示视角**：不是一句"持有"，而是巴菲特为什么不加仓、索罗斯为什么看反身性

---

## 流程图

```
┌────────────────────────────────────────────────────────────────────────────┐
│  $ augur run AAPL --limit N                                                │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 1  市场快照            │
                 │  ─────────────────────────   │
                 │                              │
                 │  ┌─ 若配置 EXA_API_KEY ─┐    │
                 │  │  ① LLM 规划           │    │
                 │  │    4-6 个搜索 query   │    │
                 │  │  ② Exa 并行执行       │    │
                 │  │  ③ LLM 基于搜索       │    │
                 │  │    结果合成 Snapshot  │    │
                 │  └──────────────────────┘    │
                 │                              │
                 │  ┌─ 否则 ────────────────┐    │
                 │  │  LLM 从训练知识      │    │
                 │  │  直接生成 Snapshot    │    │
                 │  │  （可能过期）         │    │
                 │  └──────────────────────┘    │
                 │                              │
                 │  输出：共享 Snapshot         │
                 └─────────────┬────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 2  观鸟（Auspices）   │
                 │  ─────────────────────────   │
                 │                              │
                 │  asyncio.gather +            │
                 │  Semaphore(concurrency)：    │
                 │                              │
                 │  ┌──────┐ ┌──────┐ ┌──────┐  │
                 │  │巴菲特│ │索罗斯│ │ ...  │  │
                 │  └───┬──┘ └──┬───┘ └──┬───┘  │
                 │      │       │        │      │
                 │   research research research │
                 │    model × N 次调用          │
                 │      │       │        │      │
                 │      ▼       ▼        ▼      │
                 │   PersonaVote (JSON)         │
                 │   • action: buy/hold/sell    │
                 │   • confidence 0-100         │
                 │   • key_reasons / concerns   │
                 │   • reasoning（2-3 段叙述）  │
                 │                              │
                 │  所有调用共享 system prompt  │
                 │  = framework + snapshot      │
                 │  （字节完全一致 → provider   │
                 │   自动前缀缓存生效）         │
                 └─────────────┬────────────────┘
                               │
                 ┌─────────────▼────────────────┐
                 │  Phase 3  神谕（Augury）     │
                 │  ─────────────────────────   │
                 │                              │
                 │  • 确定性统计                 │
                 │    （按 action/school 计票、  │
                 │     top reasons/concerns）   │
                 │                              │
                 │  • 合成模型读所有票，写       │
                 │    叙事部分：共识、分歧、     │
                 │    异见、改变立场的条件       │
                 └─────────────┬────────────────┘
                               │
                               ▼
                  reports/AAPL_YYYY-MM-DD.md
```

---

## 安装

### 推荐 —— `uv tool`（全局可用，无需建项目）

```bash
uv tool install git+https://github.com/xgzlucario/augur.git

augur list-personas   # 验证 —— 应显示 15 位大师
```

`augur` 命令会安装到隔离环境中全局可用。

### 开发者 —— 从源码 editable 安装

```bash
git clone https://github.com/xgzlucario/augur.git
cd augur
python3 -m venv .venv
.venv/bin/pip install -e .

cp .env.example .env                  # 填入 key 和模型 ID
.venv/bin/augur list-personas         # 验证 —— 应显示 15 位大师
```

需 Python 3.11+。

---

## 配置

`augur` 从环境变量读取凭证和模型 ID。最简单的方式：在你运行 `augur` 的目录下放
一个 `.env` 文件——每次调用会自动加载。

```env
# 必填：OpenAI 兼容接口
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                  # OpenAI 官方留空；其他 provider 填完整 URL

# 必填：两个模型层
OPENAI_MODEL_RESEARCH=gpt-4o-mini # 每位大师调用一次 → 选便宜快的
OPENAI_MODEL_SYNTHESIS=gpt-4o     # 每次 run 调用两次（快照+汇总）→ 选强的

# 可选：Exa 网页搜索（为快照接入实时数据）
EXA_API_KEY=                      # 在 https://exa.ai 注册获取
```

也可以直接在 shell 里 `export OPENAI_API_KEY=...`。报告写到你运行 `augur` 的
目录下的 `./reports/`。

---

## 使用

```bash
# 完整 run（加载所有大师）
augur run AAPL

# 限定子集
augur run TSLA --limit 5                  # 前 5 位
augur run NVDA --schools value,contrarian # 仅指定学派
augur run BTC --concurrency 5             # 控制并发

# 即使配置了 EXA_API_KEY 也强制用训练知识路径
augur run AAPL --no-search

# 列出已加载的所有大师
augur list-personas

# 详细调试日志
augur run AAPL -v
```

报告输出到 `reports/<TICKER>_<YYYY-MM-DD>.md`。

---

## 网页搜索

配置 `EXA_API_KEY` 后自动启用。快照变成"LLM 规划 → 搜索 → 合成"三步：

1. 合成模型根据 ticker 生成 4-6 个多样化查询
2. Exa 并行执行（每个 query 取 5 条，返回 text + highlights 直接可用）
3. 合成模型读取聚合结果，写出结构化 Snapshot
4. 若搜索返回 0 命中，自动降级到 LLM-only；未配置 key 或指定 `--no-search` 则直
   接跳过搜索环节

**添加其他 provider**（Tavily、Serper、Brave……）：

1. 在 `src/augur/search.py` 加类，实现 `async def search(query, num_results) -> list[SearchResult]`
2. 扩展 `get_provider()` 让它在相应环境变量存在时返回新类

目前只实现了 Exa，但 `SearchProvider` Protocol 让新增变得廉价。

---

## 添加新的大师

在 `personas/<学派>/<id>.yaml` 下新建文件：

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
era: "1980-2020"
philosophy: |
  2-3 句核心信念。
key_metrics:
  - 他特别看重的指标 1
  - 他特别看重的指标 2
avoids:
  - 他明确回避的东西 1
voice: |
  他的说话风格：语气、口头禅、常引用的话。
```

所有 YAML 的 `id` 必须唯一，`id` 会原样出现在报告里。

默认内置 15 位大师，涵盖五大学派（价值派、成长派、宏观派、量化派、逆向派）。
`augur list-personas` 查看完整名单。

---

## 项目结构

```
src/augur/
  client.py        AsyncOpenAI 单例 + 模型 ID getter
  schemas.py       Pydantic 模型：Snapshot、Decision、PersonaVote、RunStats
  personas.py      YAML 加载 + persona prompt 渲染
  search.py        SearchProvider Protocol + ExaSearch 实现 + 工厂函数
  snapshot.py      Phase 1（规划 → 搜索 → 合成，或纯 LLM 回退）
  analyst.py       单位大师调用（research 模型 + prompt 约束 JSON）
  orchestrator.py  Phase 2 fan-out，asyncio.gather + Semaphore
  aggregator.py    确定性统计 + 合成模型写叙事
  report.py        Markdown 渲染
  cli.py           Typer 入口（单一 async pipeline）
  json_utils.py    宽容 JSON 提取（剥 markdown fence、截大括号）
personas/          按学派分组的 YAML
reports/           生成的占卜报告（已 gitignore）
```

---

## 实现要点

- **两个模型层的意义在于成本**。research 模型每位大师调一次（大 run 可能 100+
  次），synthesis 模型每次 run 只调两次。研究层用便宜快的、合成层用强的，轻松
  节省一个量级的钱。
- **system prompt 在一次 run 内只构造一次，所有大师调用发送完全相同的字节**。
  这是 provider 自动前缀缓存（OpenAI、DeepSeek、Moonshot、带前缀缓存的
  vLLM 等）能命中的前提。
- **不使用 `response_format={"type": "json_object"}`**。部分 OpenAI 兼容 provider
  会静默丢弃或错误处理这个参数。Augur 改为纯靠 prompt 约束 JSON 输出，配合宽容
  解析器 `json_utils.extract_json`（自动剥离 markdown fence、前后杂文，从第一个
  `{` 截到最后一个 `}`）。
- **单位大师失败会被跳过，不影响整体**。JSON 解析失败或 API 错误 → 丢弃这一票
  继续跑。报告末尾会列出失败的 persona ID。
- **不内置成本估算**。各 provider 定价差异极大。`RunStats` 只报告 token 数量，
  乘以 provider 价格自己算。

---

## 免责声明

Augur 模拟历史投资人格，仅供研究与娱乐用途，**不构成任何投资建议**。模型可能
产生错误、偏见或过时信息，输出是为了想象一群历史上的投资大师会如何辩论，而不
是为了决定你的钱该怎么处置。实际投资请咨询持牌专业人士。
