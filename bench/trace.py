"""轨迹数据结构：runner 落盘、scoring 读取的唯一格式。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
    result: str | None = None
    timestamp: float | None = None


class FinalState(BaseModel):
    """任务结束后直接读沙箱目录得到的终态（不经过工具返回值）。"""

    files: dict[str, str] = Field(default_factory=dict)  # 相对路径 -> 文件内容
    todos: list[dict] = Field(default_factory=list)


class Trace(BaseModel):
    task_id: str
    model: str
    prompt: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    final_answer: str | None = None
    n_steps: int = 0
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    # api_error | timeout | max_steps_loop | hallucinated_tool | None
    error: str | None = None
    final_state: FinalState = Field(default_factory=FinalState)
