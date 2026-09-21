# 工程笔记：跑第一轮 5×30 时踩过的三个坑

这份笔记记录 2026-09-20/21 第一次把「30 任务 × 5 模型」跑通时遇到的三个真实问题——都是靠实际运行、看真实报错定位的，不是设计阶段能预见的。留在这里是因为它们比"这个项目有 xx 个功能"更能说明这套 pipeline 到底可靠在哪、脆弱在哪。

## 1. judge 模型把评分逻辑本身喂错了数据

**现象**：第一轮跑完，`should_refuse` 类任务里出现了大量 `other` 失败类型，而且集中在同一道任务（`t16_kb_unknown_policy_en`）上，几乎每个模型都中招。抽查 trace 发现模型的回复其实是一句标准的拒答（"公司没有这项政策的相关记录，建议联系 HR"），不该判失败。

**根因**：judge 用的是 `z-ai/glm-4.5`，一个带隐藏推理 token 的模型。当时 `build_judge_model` 给的 `max_tokens=200`——实测一次真实调用里 `completion_tokens=110`，其中 `reasoning_tokens=102`，留给最终 JSON 输出的预算所剩无几，经常直接截断成空字符串。而 [`rules.py`](../bench/scoring/rules.py) 里原来的判断是 `not judge_verdict.get("is_refusal", False)`——把"没解析出结果"（`None`）和"judge 明确说不是"（`False`）混成了同一回事，空输出被当成了"judge 说不是拒答"。

**修法**：两处都要改，只改一处不够。
- [`judge.py`](../bench/scoring/judge.py:31) 把 `max_tokens` 提到 1024，给推理 token 留出空间。
- [`rules.py`](../bench/scoring/rules.py:37) 加了 `_judge_says_no()`，显式区分 `None`（没问出结果，视为"没有信号"）和 `False`（judge 真的给出了否定判断），三处调用点（`no_clarify`、`checks.other`、`wrong_answer`）统一改用它。

**教训**：打分系统自己也需要交叉验证——第一轮的 `other` 桶本该是个兜底分类，结果占比异常高，这个信号本身就该被当成"评分逻辑有 bug"的报警，而不是"模型表现差"。

## 2. sandbox 启动阶段没有超时保护，真实卡死过 3 小时

**现象**：一次完整跑批后台挂了很久，`results/<date>/traces/` 下的文件数量长时间不再增长，进程还在但 CPU 占用接近 0。

**根因**：[`agent.py`](../bench/agent.py:120) 原来只用 `asyncio.wait_for(..., timeout=timeout_s)` 包住了 agent 的 `ainvoke` 调用，但 `async with sandbox_session(...)` 这一步——起 5 个 MCP 子进程、跟它们握手——完全不在这个超时范围内。子进程握手偶发卡死时，这个任务就会无限期挂着，把整批任务拖死。

**修法**：`run_task` 现在只做一件事：把 `_run_task_body`（包含 sandbox 启停在内的完整逻辑）整体套一层 `asyncio.wait_for(timeout_s + 30)`，超时统一归为 `error="timeout"`。见 [`agent.py:120-146`](../bench/agent.py)。

## 3. MCP 默认的"每次工具调用开一个新子进程"在高并发下会把协议撞坏

**现象**：修完第 2 个问题重跑，进程不再卡死，但会在中途直接崩溃退出，日志里是 `langchain_mcp_adapters` 内部的 `UnboundLocalError: cannot access local variable 'tools'`，往上翻是 `json.decoder.JSONDecodeError: Extra data`——底层的 MCP stdio JSON-RPC 消息帧被撞坏了。

**根因**：`MultiServerMCPClient.get_tools()` 的默认行为是"每次工具调用都新开一个 session"，对 stdio transport 来说就是每次工具调用都新起一个子进程。5 个模型并发（`asyncio.Semaphore(3)`）、每个任务好几次工具调用、每次调用起 5 个 server 里的 1 个，子进程开关的 churn 量相当大，在高负载下会撞出 stdio 层面的竞态。

**修法**：改成每个任务给 5 个 server 各开一个**常驻 session**（`client.session(name)` + `load_mcp_tools(session)`，用 `AsyncExitStack` 管生命周期），任务期间所有工具调用复用同一批 session，子进程数从"每次调用一个"降到"每个 server 一个"。见 [`sandbox.py:74-97`](../bench/sandbox.py)。

顺带修了一个关联问题：[`todo_server.py`](../bench/../tools/todo_server.py) 原来直接 `open(...).write()` 写 `todos.json`，并发写入下可能被读到写一半的文件（同样表现为 JSON 解析报错）。改成写临时文件再 `os.replace()` 原子替换。

## 修完之后

三处都改完后，同样的 5 模型 × 30 任务重新跑了一次：150 条评测，0 个 `api_error`、0 个未捕获异常、0 次卡死。这版结果就是 [README](../README.md) 里榜单和 `results/2026-09-21/` 里的数据。
