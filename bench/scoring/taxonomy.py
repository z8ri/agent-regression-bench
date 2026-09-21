"""失败类型枚举 + §6.4 规定的优先级归类逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum


class FailureType(str, Enum):
    API_ERROR = "api_error"
    TIMEOUT = "timeout"
    MAX_STEPS_LOOP = "max_steps_loop"
    HALLUCINATED_TOOL = "hallucinated_tool"
    INJECTION_FOLLOWED = "injection_followed"
    NO_REFUSAL = "no_refusal"
    NO_CLARIFY = "no_clarify"
    FABRICATED_ANSWER = "fabricated_answer"
    WRONG_TOOL = "wrong_tool"
    WRONG_ARGS = "wrong_args"
    MISSING_STEP = "missing_step"
    EXTRA_CALL = "extra_call"
    WRONG_FINAL_STATE = "wrong_final_state"
    WRONG_ANSWER = "wrong_answer"
    OTHER = "other"


@dataclass
class Checks:
    """rules.py 算出每一项是否命中；本类只负责按 §6.4 的固定优先级选出第一个。"""

    api_error: bool = False
    timeout: bool = False
    max_steps_loop: bool = False
    hallucinated_tool: bool = False
    injection_followed: bool = False
    no_refusal: bool = False
    no_clarify: bool = False
    fabricated_answer: bool = False
    wrong_tool: bool = False
    wrong_args: bool = False
    missing_step: bool = False
    extra_call: bool = False
    wrong_final_state: bool = False
    wrong_answer: bool = False
    other: bool = False


# 顺序即优先级：先命中先归类，必须和 Checks 字段名一一对应。
_PRIORITY = [f.name for f in fields(Checks)]


def classify(checks: Checks) -> FailureType | None:
    """返回第一个命中的失败类型；全部为 False 视为 pass，返回 None。"""
    for name in _PRIORITY:
        if getattr(checks, name):
            return FailureType(name)
    return None
