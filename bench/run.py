"""入口：python -m bench.run [--models a,b] [--tasks t01,t02] [--repeat N]

Day 1 范围：只落轨迹 + scores.json，不接 judge，不生成 summary/README（report.py 是 Day 2）。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from bench.agent import run_task
from bench.scoring.rules import score_trace
from bench.tasks import TaskSpec, load_all_tasks
from bench.trace import Trace

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_YAML = REPO_ROOT / "bench" / "models.yaml"
TASKS_DIR = REPO_ROOT / "tasks"
RESULTS_DIR = REPO_ROOT / "results"

KNOWN_TOOLS = {
    "get_weather",
    "write_file",
    "read_file",
    "list_files",
    "append_file",
    "delete_file",
    "add_todo",
    "list_todos",
    "complete_todo",
    "remove_todo",
    "calculate",
    "search_kb",
}


def load_models_config() -> dict:
    with open(MODELS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跑 Agent 工具调用回归基准")
    parser.add_argument("--models", type=str, default=None, help="逗号分隔的模型 slug 子集，默认 models.yaml 全部")
    parser.add_argument("--tasks", type=str, default=None, help="逗号分隔的任务 id 子集，默认 tasks/ 下全部")
    parser.add_argument("--repeat", type=int, default=1, help="同一 (task, model) 重复跑几次，默认 1")
    return parser.parse_args(argv)


async def _run_model(
    model_slug: str,
    tasks: list[TaskSpec],
    repeat: int,
    api_key: str,
    cfg: dict,
    sem: asyncio.Semaphore,
    out_dir: Path,
) -> tuple[str, dict[str, list[Trace]]]:
    """一个模型内部任务严格串行；模型之间由外层 Semaphore 控制并发。"""
    async with sem:
        traces_dir = out_dir / "traces" / model_slug
        traces_dir.mkdir(parents=True, exist_ok=True)
        model_traces: dict[str, list[Trace]] = {}
        for task in tasks:
            traces_for_task: list[Trace] = []
            for run_idx in range(repeat):
                trace = await run_task(
                    task,
                    model_slug,
                    api_key,
                    max_steps=cfg.get("max_steps", 10),
                    timeout_s=cfg.get("timeout_s", 120),
                )
                traces_for_task.append(trace)
                suffix = f"_{run_idx}" if repeat > 1 else ""
                (traces_dir / f"{task.id}{suffix}.json").write_text(
                    trace.model_dump_json(indent=2), encoding="utf-8"
                )
                print(f"[{model_slug}] {task.id} run#{run_idx} -> error={trace.error}")
            model_traces[task.id] = traces_for_task
        return model_slug, model_traces


async def run_all(
    models: list[str],
    tasks: list[TaskSpec],
    repeat: int,
    cfg: dict,
    api_key: str,
    out_dir: Path,
) -> dict[tuple[str, str], list[Trace]]:
    sem = asyncio.Semaphore(3)
    results = await asyncio.gather(
        *[_run_model(model_slug, tasks, repeat, api_key, cfg, sem, out_dir) for model_slug in models]
    )
    traces_by_model_task: dict[tuple[str, str], list[Trace]] = {}
    for model_slug, model_traces in results:
        for task_id, traces in model_traces.items():
            traces_by_model_task[(model_slug, task_id)] = traces
    return traces_by_model_task


def score_all(
    traces_by_model_task: dict[tuple[str, str], list[Trace]],
    tasks_by_id: dict[str, TaskSpec],
    out_dir: Path,
) -> list[dict]:
    scores = []
    for (_model_slug, task_id), traces in traces_by_model_task.items():
        task = tasks_by_id[task_id]
        for trace in traces:
            result = score_trace(trace, task, known_tools=KNOWN_TOOLS)
            scores.append(result.model_dump())
    (out_dir / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    return scores


def main(argv=None) -> None:
    args = parse_args(argv)
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY 未设置：写进 .env（参考 .env.example）或 export 一下")

    cfg = load_models_config()
    all_model_slugs = [m["slug"] for m in cfg["models"]]
    models = args.models.split(",") if args.models else all_model_slugs

    task_ids = args.tasks.split(",") if args.tasks else None
    tasks = load_all_tasks(TASKS_DIR, task_ids)
    if not tasks:
        raise SystemExit("没有匹配到任何任务，检查 --tasks 参数或 tasks/ 目录")
    tasks_by_id = {t.id: t for t in tasks}

    out_dir = RESULTS_DIR / dt.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    traces_by_model_task = asyncio.run(run_all(models, tasks, args.repeat, cfg, api_key, out_dir))
    scores = score_all(traces_by_model_task, tasks_by_id, out_dir)

    n_pass = sum(1 for s in scores if s["passed"])
    print(f"跑完：{len(scores)} 条评测，通过 {n_pass} 条。结果在 {out_dir}")


if __name__ == "__main__":
    main()
