# Augur · 占卜师

> 一个由传奇投资大师组成的委员会，随召随到。喂它一个标的，读取神谕。

```
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
```

*Augur* —— 古罗马祭司，通过观察飞鸟方位解读神意。这位 augur 不读鸟，只读盘。

15 位历史投资大师——巴菲特、芒格、格雷厄姆、索罗斯、达利欧、西蒙斯、
凯茜·伍德……——共读同一份市场快照，各以自己的投资哲学独立思考、独立投票。最终
由一位"编辑"整合共识与分歧，写成神谕。

兼容任意 **OpenAI 兼容** 接口（OpenAI、DeepSeek、Moonshot、Groq、Ollama……）。
必须配置网页搜索 key（**Exa** 或 **Tavily**）——训练数据对投资分析来说太过时。

> [English README](./README.md)

**本项目不构成投资建议。** 仅供研究与娱乐。

---

## 三幕流程

**观鸟（The Auspices）。** 合成模型规划 4–6 个搜索 query；Exa 或 Tavily 并行
执行；模型把 ~30 条命中压缩成一份共享 `Snapshot`。query 会实时打到终端——你
能看到占卜师选择了去找什么。

**议事会（The Council）。** Augur 对每位大师各开一次 API 调用（默认 10 个并
发）。每次调用发送**字节一致**的 system prompt（框架 + 快照），让 provider 的
自动前缀缓存可以命中。research 模型以大师的口吻返回 `PersonaVote`：
buy/hold/sell、置信度、时间尺度、仓位、理由、疑虑、2-3 段 in-voice 论述。每一
票落地即刻流式打到终端；解析失败的大师被跳过，不影响整体。

**神谕（The Augury）。** 本地统计按 action 和学派计票，合成模型通读全部投票，
写一段中立的编辑叙事——共识、分歧、异见、改变立场的条件——落到 `./reports/` 下
的 Markdown 报告。

典型 run：**1–2 分钟**、~30 条命中、3 次合成调用 + N 次研究调用。

---

## 安装

**推荐**——全局一条命令：

```bash
uv tool install git+https://github.com/xgzlucario/augur.git
augur list-personas   # 应显示 15 位大师
```

从源码：

```bash
git clone https://github.com/xgzlucario/augur.git && cd augur
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/augur list-personas
```

需 Python 3.11+。

---

## 配置

在你运行 `augur` 的目录下放一个 `.env`：

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                  # OpenAI 官方留空；其他 provider 填完整 URL
OPENAI_MODEL_RESEARCH=gpt-4o-mini # N 次（每位大师一次）→ 选便宜快的
OPENAI_MODEL_SYNTHESIS=gpt-4o     # 3 次（规划/快照/叙事）→ 选强的

# 搜索——必填
EXA_API_KEY=                      # https://exa.ai
TAVILY_API_KEY=                   # https://tavily.com
# SEARCH_PROVIDER=exa             # 两个 key 都设时强制选用某个
```

两个搜索 key 都配？默认使用 Exa，除非 `SEARCH_PROVIDER=tavily`。报告写到调用
目录下的 `./reports/`。

---

## 使用

```bash
augur run AAPL                              # 完整 council
augur run TSLA --limit 5                    # 限定数量
augur run NVDA --schools value,contrarian   # 限定学派
augur run BTC --concurrency 5               # 降低并发
augur list-personas                          # 查看名单
augur run AAPL -v                            # 详细日志
```

报告文件：`reports/<TICKER>_<YYYY-MM-DD>.md`。

---

## 添加新大师

在 `personas/<学派>/<id>.yaml` 下新建文件：

```yaml
id: my_master
name: My Master
school: value              # value | growth | macro | quant | contrarian
era: "1980-2020"
philosophy: |
  1-2 句核心信念。
key_metrics:
  - 关注指标 1
avoids:
  - 回避清单 1
voice: |
  语气、口头禅、常引用的话。
```

所有 YAML 的 `id` 必须唯一。默认内置 15 位大师，涵盖五大学派（价值、成长、宏
观、量化、逆向）。

---

## 项目结构

```
src/augur/
  cli.py           Typer 入口 + fan-out 流水线
  snapshot.py      Phase 1 —— 规划 → 搜索 → 合成
  analyst.py       单位大师 → 单票 PersonaVote
  aggregator.py    统计 + 叙事
  search.py        Exa & Tavily provider
  personas.py      YAML 加载 + prompt 渲染
  schemas.py       Pydantic 模型
  client.py        AsyncOpenAI + 模型 getter
  report.py        Markdown 渲染
  json_utils.py    宽容 JSON 提取
personas/          按学派分组的 YAML（随 package 打包）
reports/           生成的占卜报告（已 gitignore）
```

---

## 设计笔记

- **双模型层。** research 模型跑 N 次（每位大师一次），synthesis 模型跑 3 次。
  下层用便宜快的、上层用强的——规模化后省一个量级的钱。
- **不用 `response_format`。** 许多 OpenAI 兼容 provider 对 `json_object` 处理
  不一致。Augur 只靠 prompt 约束，加一个宽容解析器处理 markdown fence 和前后
  杂文。
- **失败大声。** 查询规划失败或搜索返回 0 命中 → 红色错误 panel 退出。过期的
  训练知识比没有答案还糟。

---

## 免责声明

Augur 模拟的是历史上的投资人格。输出是思考工具，不是投资决策。实际交易前请咨
询持牌专业人士。
