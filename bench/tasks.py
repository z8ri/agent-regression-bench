"""任务 YAML 的 pydantic schema 与加载器，字段语义见 tasks/schema.md（抄自 SPEC §5）。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CHANGING_TOOLS = {
    "write_file",
    "append_file",
    "delete_file",
    "add_todo",
    "complete_todo",
    "remove_todo",
}


class ArgMatch(BaseModel):
    tool: str
    match: dict = Field(default_factory=dict)


class ToolCallsExpect(BaseModel):
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    ordered: list[list[str]] = Field(default_factory=list)
    max_total: int | None = None


class FileStateExpect(BaseModel):
    exists: bool | None = None
    contains_all: list[str] = Field(default_factory=list)


class TodoStateExpect(BaseModel):
    title_contains: str | None = None
    due: str | None = None
    done: bool | None = None


class FinalStateExpect(BaseModel):
    files: dict[str, FileStateExpect] = Field(default_factory=dict)
    todos: list[TodoStateExpect] = Field(default_factory=list)


class FinalAnswerExpect(BaseModel):
    contains_all: list[str] = Field(default_factory=list)
    not_equals: str | None = None
    # None = 不检查；[] = 一个数字都不许出现；["26"] = 只允许出现 26
    must_not_mention_numbers_outside: list[str] | None = None


class Expect(BaseModel):
    tool_calls: ToolCallsExpect = Field(default_factory=ToolCallsExpect)
    args: list[ArgMatch] = Field(default_factory=list)
    final_state: FinalStateExpect = Field(default_factory=FinalStateExpect)
    final_answer: FinalAnswerExpect | None = None
    behavior: str = "answer"  # answer | refuse | clarify


class JudgeExpect(BaseModel):
    enabled: bool = False
    reference_answer: str | None = None


class TaskSpec(BaseModel):
    id: str
    category: str  # single_step | multi_step | should_refuse | should_clarify | injection
    lang: str  # zh | en
    prompt: str
    setup: dict = Field(default_factory=dict)
    expect: Expect
    judge: JudgeExpect = Field(default_factory=JudgeExpect)


def load_task(path: Path) -> TaskSpec:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return TaskSpec.model_validate(raw)


def load_all_tasks(tasks_dir: Path, task_ids: list[str] | None = None) -> list[TaskSpec]:
    paths = sorted(tasks_dir.glob("t*.yaml"))
    tasks = [load_task(p) for p in paths]
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in tasks if t.id in wanted]
    return tasks
