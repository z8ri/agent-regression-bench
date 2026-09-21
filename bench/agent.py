"""建 MCP client + langchain.agents.create_agent（ReAct 循环），跑一个 (task, model)，返回 Trace。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from bench.sandbox import read_final_state, sandbox_session
from bench.tasks import TaskSpec
from bench.trace import FinalState, Trace, ToolCallRecord

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
_RETRY_DELAYS_S = [1, 2]  # §12：API 报错重试 2 次，指数退避


def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _build_model(model_slug: str, api_key: str, max_tokens: int) -> ChatOpenAI:
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model=model_slug,
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"usage": {"include": True}},
    )


def _usage_of(msg: AIMessage) -> dict:
    return (
        msg.response_metadata.get("token_usage")
        or msg.response_metadata.get("usage")
        or msg.usage_metadata
        or {}
    )


def _cost_of(usage: dict) -> float | None:
    for key in ("cost", "total_cost", "cost_usd"):
        value = usage.get(key)
        if value is not None:
            return float(value)
    return None


def _is_hallucinated_tool_message(msg: ToolMessage) -> bool:
    if getattr(msg, "status", None) != "error":
        return False
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return "is not a valid tool" in content


def extract_trace_fields(messages: list) -> dict:
    tool_calls: list[ToolCallRecord] = []
    pending_by_id: dict[str, ToolCallRecord] = {}
    final_answer = None
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = 0.0
    have_cost = False
    n_steps = 0
    hallucinated = False

    for msg in messages:
        if isinstance(msg, AIMessage):
            n_steps += 1
            usage = _usage_of(msg)
            prompt_tokens += usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            completion_tokens += usage.get("completion_tokens") or usage.get("output_tokens") or 0
            cost = _cost_of(usage)
            if cost is not None:
                cost_usd += cost
                have_cost = True
            for tc in msg.tool_calls or []:
                record = ToolCallRecord(name=tc["name"], args=tc.get("args", {}))
                tool_calls.append(record)
                pending_by_id[tc["id"]] = record
            if msg.content and not msg.tool_calls:
                final_answer = msg.content if isinstance(msg.content, str) else str(msg.content)
        elif isinstance(msg, ToolMessage):
            if _is_hallucinated_tool_message(msg):
                hallucinated = True
            record = pending_by_id.get(msg.tool_call_id)
            if record is not None:
                record.result = msg.content if isinstance(msg.content, str) else str(msg.content)

    return {
        "tool_calls": tool_calls,
        "final_answer": final_answer,
        "prompt_tokens": prompt_tokens or None,
        "completion_tokens": completion_tokens or None,
        "cost_usd": cost_usd if have_cost else None,
        "n_steps": n_steps,
        "hallucinated": hallucinated,
    }


async def _ainvoke_with_retry(agent, payload: dict, config: dict):
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0, *_RETRY_DELAYS_S]):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await agent.ainvoke(payload, config=config)
        except GraphRecursionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 分类交给调用方，这里只负责重试
            last_exc = exc
    raise last_exc


async def run_task(
    task: TaskSpec,
    model_slug: str,
    api_key: str,
    max_steps: int = 10,
    timeout_s: int = 120,
    max_tokens: int = 1024,
) -> Trace:
    """外层再包一层超时：sandbox_session 起 5 个 MCP 子进程这一步本身不在内部
    timeout_s 的保护范围内，实测真的会偶发卡死（子进程握手没响应），
    不兜底的话整个 nightly job 会被一个任务挂死。"""
    start = time.monotonic()
    try:
        return await asyncio.wait_for(
            _run_task_body(task, model_slug, api_key, max_steps, timeout_s, max_tokens, start),
            timeout=timeout_s + 30,
        )
    except TimeoutError:
        return Trace(
            task_id=task.id,
            model=model_slug,
            prompt=task.prompt,
            n_steps=0,
            latency_ms=(time.monotonic() - start) * 1000,
            error="timeout",
            final_state=FinalState(),
        )


async def _run_task_body(
    task: TaskSpec,
    model_slug: str,
    api_key: str,
    max_steps: int,
    timeout_s: int,
    max_tokens: int,
    start: float,
) -> Trace:
    async with sandbox_session(task.setup) as (sandbox_dir, tools):
        model = _build_model(model_slug, api_key, max_tokens)
        agent = create_agent(model, tools, system_prompt=_load_system_prompt())

        error: str | None = None
        fields = {
            "tool_calls": [],
            "final_answer": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "cost_usd": None,
            "n_steps": 0,
            "hallucinated": False,
        }
        try:
            result = await asyncio.wait_for(
                _ainvoke_with_retry(
                    agent,
                    {"messages": [HumanMessage(content=task.prompt)]},
                    {"recursion_limit": max_steps * 2 + 2},
                ),
                timeout=timeout_s,
            )
            fields = extract_trace_fields(result["messages"])
        except TimeoutError:
            error = "timeout"
        except GraphRecursionError:
            error = "max_steps_loop"
        except Exception:  # noqa: BLE001 - 重试后仍失败，记为 api_error，任务继续
            error = "api_error"

        if error is None and fields["hallucinated"]:
            error = "hallucinated_tool"

        latency_ms = (time.monotonic() - start) * 1000
        final_state_raw = read_final_state(sandbox_dir)

    return Trace(
        task_id=task.id,
        model=model_slug,
        prompt=task.prompt,
        tool_calls=fields["tool_calls"],
        final_answer=fields["final_answer"],
        n_steps=fields["n_steps"],
        latency_ms=latency_ms,
        prompt_tokens=fields["prompt_tokens"],
        completion_tokens=fields["completion_tokens"],
        cost_usd=fields["cost_usd"],
        error=error,
        final_state=FinalState(**final_state_raw),
    )
