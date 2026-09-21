"""LLM judge：只做 SPEC §6.3 列出的三件事，温度 0，输出严格 JSON。

judge 模型固定用 models.yaml 里的 `judge` 项；prompt 版本化放在
bench/scoring/judge_prompts/ 下，改动 prompt 要开新文件（v2/v3...），
不要原地改已经用过的版本。
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

PROMPTS_DIR = Path(__file__).parent / "judge_prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_judge_model(model_slug: str, api_key: str) -> ChatOpenAI:
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model=model_slug,
        temperature=0,
        # 有些 judge 候选模型（比如 glm-4.5）默认带隐藏推理 token，200 太小会被推理吃光，
        # 只留下空 content——实测过 completion_tokens=110 里 102 个是 reasoning_tokens。
        max_tokens=1024,
    )


def extract_json_object(text: str) -> dict:
    """从模型输出里抠出第一个 JSON 对象；抠不出来就抛 ValueError。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"输出里没有 JSON 对象：{text!r}")
    return json.loads(text[start : end + 1])


async def _ask(model: ChatOpenAI, system_prompt: str, user_content: str, key: str) -> bool | None:
    response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_content)])
    text = response.content if isinstance(response.content, str) else str(response.content)
    try:
        data = extract_json_object(text)
    except (ValueError, json.JSONDecodeError):
        return None
    value = data.get(key)
    return bool(value) if isinstance(value, bool) else None


async def judge_refusal(prompt: str, final_answer: str | None, model: ChatOpenAI) -> dict:
    system_prompt = _load_prompt("refusal_v1.txt")
    user_content = f"用户问题：{prompt}\n\n助手回复：{final_answer or '（空）'}"
    value = await _ask(model, system_prompt, user_content, "is_refusal")
    return {"is_refusal": value}


async def judge_clarify(prompt: str, final_answer: str | None, model: ChatOpenAI) -> dict:
    system_prompt = _load_prompt("clarify_v1.txt")
    user_content = f"用户问题：{prompt}\n\n助手回复：{final_answer or '（空）'}"
    value = await _ask(model, system_prompt, user_content, "asked_clarifying_question")
    return {"asked_clarifying_question": value}


async def judge_correctness(prompt: str, final_answer: str | None, reference_answer: str, model: ChatOpenAI) -> dict:
    system_prompt = _load_prompt("correctness_v1.txt")
    user_content = f"用户问题：{prompt}\n\n参考答案要点：{reference_answer}\n\n助手回复：{final_answer or '（空）'}"
    value = await _ask(model, system_prompt, user_content, "correct")
    return {"correct": value}


async def judge_trace(prompt: str, final_answer: str | None, behavior: str, reference_answer: str | None, model: ChatOpenAI) -> dict | None:
    """按 §6.3 的边界，只在需要的时候才问 judge；用不上就返回 None。"""
    if behavior == "refuse":
        return await judge_refusal(prompt, final_answer, model)
    if behavior == "clarify":
        return await judge_clarify(prompt, final_answer, model)
    if behavior == "answer" and reference_answer:
        return await judge_correctness(prompt, final_answer, reference_answer, model)
    return None
