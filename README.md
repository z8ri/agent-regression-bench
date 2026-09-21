# agent-regression-bench

一个每晚自动运行的 Agent 工具调用回归基准：30 道带标准答案的任务，跑在 5 个确定性、无网络、沙箱化的 MCP 工具上，用同一个 LangGraph ReAct 循环驱动多个大模型，记录完整轨迹，按确定性规则打分（少量用固定 judge），产出按日期归档的榜单与失败分类统计。

## 这是什么，不是什么

这是一个**工程回归工具**，回答三个问题：这个 Agent 靠不靠谱、换模型有没有退步、哪类题最容易翻车。它不是学术基准——不追求覆盖 τ-bench / BFCL 那类公开任务集，也不宣称是"新基准"。真实的是"模型在这个固定工具环境下随时间的行为数据"，不是真实用户流量。

不做的事：Web UI、看板、数据库（榜单就是 Markdown 表 + CSV）；多 Agent；长程任务；记忆/RAG 评测；模型微调；prompt 优化搜索（系统 prompt 固定一份，所有模型共用）。

详细设计见 [SPEC.md](SPEC.md)。

## 怎么跑

```bash
uv sync
cp .env.example .env   # 填入 OPENROUTER_API_KEY

python -m bench.run                                  # 跑 models.yaml 里的全部模型 × 全部任务
python -m bench.run --models deepseek/deepseek-chat   # 只跑一个模型
python -m bench.run --tasks t01_calc_basic,t15_weather_unknown_city  # 只跑几个任务
python -m bench.run --repeat 3                        # 同一 (task, model) 跑 3 次，看方差

python -m bench.report                                 # 用今天的 results/<date>/scores.json 生成榜单
python -m pytest                                       # 跑测试
```

## 怎么加模型 / 加任务

- 加模型：改 `bench/models.yaml` 的 `models` 列表，写 OpenRouter 的模型 slug（先用 `curl https://openrouter.ai/api/v1/models` 核对 slug 是否还存在）。
- 加任务：在 `tasks/` 下新建一个 `tNN_<slug>.yaml`，字段说明见 [tasks/schema.md](tasks/schema.md)。任务分五类：`single_step` / `multi_step` / `should_refuse` / `should_clarify` / `injection`。
- 加 MCP 工具：在 `tools/` 下新建一个 `*_server.py`（用 `mcp.server.fastmcp.FastMCP`），零网络、确定性、状态只写 `SANDBOX_DIR`，然后在 `bench/sandbox.py` 的 `SERVER_MODULES` 里注册。

<!-- AUTO-GENERATED:START -->

_最近一次运行：2026-09-21，30 个任务 × 5 个模型，repeat=1，总成本 $0.1952_

### 榜单

| model | overall pass | single | multi | refuse | clarify | injection | tool-call precision | avg steps | p50 latency | cost/task |
|---|---|---|---|---|---|---|---|---|---|---|
| z-ai/glm-4.5 \* | 90% | 100% | 100% | 80% | 60% | 100% | 91% | 2.4 | 15029ms | $0.00163 |
| minimax/minimax-m2 | 87% | 83% | 62% | 100% | 100% | 100% | 97% | 1.9 | 5381ms | $0.00067 |
| moonshotai/kimi-k2 | 83% | 100% | 100% | 40% | 60% | 100% | 95% | 2.2 | 6266ms | $0.00103 |
| deepseek/deepseek-chat | 73% | 100% | 62% | 80% | 60% | 67% | 92% | 2.1 | 7770ms | $0.00115 |
| qwen/qwen-2.5-72b-instruct | 50% | 100% | 38% | 60% | 60% | 0% | 82% | 2.2 | 4738ms | $0.00203 |

\* 该模型同时也是本轮的 judge。

### 失败类型 × 模型

| failure_type | z-ai/glm-4.5 | minimax/minimax-m2 | moonshotai/kimi-k2 | deepseek/deepseek-chat | qwen/qwen-2.5-72b-instruct |
|---|---|---|---|---|---|
| fabricated_answer | 1 | 0 | 2 | 0 | 1 |
| injection_followed | 0 | 0 | 0 | 2 | 5 |
| max_steps_loop | 0 | 3 | 0 | 0 | 0 |
| missing_step | 0 | 0 | 0 | 1 | 1 |
| no_clarify | 2 | 0 | 2 | 2 | 2 |
| no_refusal | 0 | 0 | 1 | 1 | 1 |
| wrong_final_state | 0 | 1 | 0 | 1 | 5 |
| wrong_tool | 0 | 0 | 0 | 1 | 0 |

### judge 与规则一致率：80%（50 对重叠判定）

已连续运行 1 天，累计 150 次 (task, model) 评测。

<!-- AUTO-GENERATED:END -->

以下内容由 `python -m bench.report` 自动生成，不要手改上面两条标记之间的内容。
