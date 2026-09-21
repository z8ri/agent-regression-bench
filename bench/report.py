"""results/<date>/ → summary.json + README 自动段 + history.csv 追加一行。

用法：python -m bench.report [--date YYYY-MM-DD]，默认今天。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
from pathlib import Path

import yaml

from bench.tasks import load_all_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
HISTORY_CSV = RESULTS_DIR / "history.csv"
README_PATH = REPO_ROOT / "README.md"
MODELS_YAML = REPO_ROOT / "bench" / "models.yaml"
TASKS_DIR = REPO_ROOT / "tasks"

AUTO_START = "<!-- AUTO-GENERATED:START -->"
AUTO_END = "<!-- AUTO-GENERATED:END -->"

CATEGORIES = ["single_step", "multi_step", "should_refuse", "should_clarify", "injection"]
CATEGORY_LABELS = {
    "single_step": "single",
    "multi_step": "multi",
    "should_refuse": "refuse",
    "should_clarify": "clarify",
    "injection": "injection",
}
HISTORY_COLUMNS = [
    "date",
    "model",
    "overall_pass",
    "single",
    "multi",
    "refuse",
    "clarify",
    "injection",
    "precision",
    "cost_total",
]


def _is_date(name: str) -> bool:
    try:
        dt.date.fromisoformat(name)
        return True
    except ValueError:
        return False


def load_scores(date_dir: Path) -> list[dict]:
    path = date_dir / "scores.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_task_categories(tasks_dir: Path = TASKS_DIR) -> dict[str, str]:
    return {t.id: t.category for t in load_all_tasks(tasks_dir)}


def summarize_by_model(scores: list[dict], task_categories: dict[str, str]) -> list[dict]:
    """按模型聚合榜单需要的字段，按 overall_pass 降序。"""
    by_model: dict[str, list[dict]] = {}
    for s in scores:
        by_model.setdefault(s["model"], []).append(s)

    rows = []
    for model, model_scores in sorted(by_model.items()):
        n = len(model_scores)
        overall_pass = (sum(1 for s in model_scores if s["passed"]) / n) if n else 0.0

        category_pass: dict[str, float | None] = {}
        for cat in CATEGORIES:
            cat_scores = [s for s in model_scores if task_categories.get(s["task_id"]) == cat]
            category_pass[cat] = (
                sum(1 for s in cat_scores if s["passed"]) / len(cat_scores) if cat_scores else None
            )

        total_calls = sum(s["n_tool_calls"] for s in model_scores)
        unneeded_calls = sum(s["n_unneeded_calls"] for s in model_scores)
        precision = (1.0 - unneeded_calls / total_calls) if total_calls else 1.0

        avg_steps = statistics.mean(s["n_steps"] for s in model_scores) if model_scores else 0.0
        latencies = [s["latency_ms"] for s in model_scores if s["latency_ms"] is not None]
        p50_latency = statistics.median(latencies) if latencies else None
        costs = [s["cost_usd"] for s in model_scores if s["cost_usd"] is not None]
        cost_total = sum(costs)
        cost_per_task = (cost_total / n) if n else 0.0

        rows.append(
            {
                "model": model,
                "n_evaluations": n,
                "overall_pass": overall_pass,
                "category_pass": category_pass,
                "precision": precision,
                "avg_steps": avg_steps,
                "p50_latency_ms": p50_latency,
                "cost_per_task_usd": cost_per_task,
                "cost_total_usd": cost_total,
            }
        )
    rows.sort(key=lambda r: r["overall_pass"], reverse=True)
    return rows


def failure_type_counts(scores: list[dict]) -> dict[str, dict[str, int]]:
    """model -> failure_type -> count，只统计没 pass 的。"""
    counts: dict[str, dict[str, int]] = {}
    for s in scores:
        if s["passed"]:
            continue
        model_counts = counts.setdefault(s["model"], {})
        ft = s["failure_type"] or "other"
        model_counts[ft] = model_counts.get(ft, 0) + 1
    return counts


def judge_agreement_rate(scores: list[dict]) -> dict:
    pairs = [s for s in scores if s.get("judge_agrees_with_rules") is not None]
    if not pairs:
        return {"n_pairs": 0, "agreement_rate": None}
    agree = sum(1 for s in pairs if s["judge_agrees_with_rules"])
    return {"n_pairs": len(pairs), "agreement_rate": agree / len(pairs)}


def history_totals(up_to: str | None = None) -> tuple[int, int]:
    """(连续运行天数, 累计 (task, model) 评测次数)；直接扫 results/*/scores.json，不依赖 history.csv。"""
    if not RESULTS_DIR.is_dir():
        return 0, 0
    date_names = sorted(p.name for p in RESULTS_DIR.iterdir() if p.is_dir() and _is_date(p.name))
    if up_to:
        date_names = [d for d in date_names if d <= up_to]

    total_evaluations = 0
    dates: list[dt.date] = []
    for name in date_names:
        scores = load_scores(RESULTS_DIR / name)
        if not scores:
            continue
        total_evaluations += len(scores)
        dates.append(dt.date.fromisoformat(name))

    dates = sorted(set(dates))
    streak = 0
    if dates:
        streak = 1
        for i in range(len(dates) - 1, 0, -1):
            if (dates[i] - dates[i - 1]).days == 1:
                streak += 1
            else:
                break
    return streak, total_evaluations


def load_models_config() -> dict:
    with open(MODELS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fmt_pct(x: float | None) -> str:
    return f"{x * 100:.0f}%" if x is not None else "—"


def render_leaderboard_table(rows: list[dict], judge_slug: str) -> str:
    header = (
        "| model | overall pass | single | multi | refuse | clarify | injection "
        "| tool-call precision | avg steps | p50 latency | cost/task |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = [header]
    for r in rows:
        name = r["model"] + (" \\*" if r["model"] == judge_slug else "")
        cats = " | ".join(_fmt_pct(r["category_pass"][c]) for c in CATEGORIES)
        latency = f"{r['p50_latency_ms']:.0f}ms" if r["p50_latency_ms"] is not None else "—"
        cost = f"${r['cost_per_task_usd']:.5f}"
        lines.append(
            f"| {name} | {_fmt_pct(r['overall_pass'])} | {cats} | {_fmt_pct(r['precision'])} | "
            f"{r['avg_steps']:.1f} | {latency} | {cost} |\n"
        )
    if any(r["model"] == judge_slug for r in rows):
        lines.append("\n\\* 该模型同时也是本轮的 judge。\n")
    return "".join(lines)


def render_failure_table(counts: dict[str, dict[str, int]], models: list[str]) -> str:
    all_types = sorted({ft for m in counts.values() for ft in m})
    if not all_types:
        return "本轮没有失败案例。\n"
    header = "| failure_type | " + " | ".join(models) + " |\n"
    header += "|---|" + "---|" * len(models) + "\n"
    lines = [header]
    for ft in all_types:
        row = [str(counts.get(m, {}).get(ft, 0)) for m in models]
        lines.append(f"| {ft} | " + " | ".join(row) + " |\n")
    return "".join(lines)


def render_auto_section(
    date_str: str,
    rows: list[dict],
    counts: dict[str, dict[str, int]],
    agreement: dict,
    n_tasks: int,
    repeat: int,
    judge_slug: str,
) -> str:
    models = [r["model"] for r in rows]
    total_cost = sum(r["cost_total_usd"] for r in rows)
    streak_days, total_evaluations = history_totals(up_to=date_str)

    agreement_line = (
        f"judge 与规则一致率：{_fmt_pct(agreement['agreement_rate'])}（{agreement['n_pairs']} 对重叠判定）"
        if agreement["n_pairs"]
        else "judge 与规则一致率：本轮没有需要 judge 的重叠判定"
    )

    parts = [
        AUTO_START,
        "",
        f"_最近一次运行：{date_str}，{n_tasks} 个任务 × {len(models)} 个模型，repeat={repeat}，"
        f"总成本 ${total_cost:.4f}_",
        "",
        "### 榜单",
        "",
        render_leaderboard_table(rows, judge_slug),
        "### 失败类型 × 模型",
        "",
        render_failure_table(counts, models),
        f"### {agreement_line}",
        "",
        f"已连续运行 {streak_days} 天，累计 {total_evaluations} 次 (task, model) 评测。",
        "",
        AUTO_END,
    ]
    return "\n".join(parts)


def update_readme(auto_section: str) -> None:
    if README_PATH.is_file():
        content = README_PATH.read_text(encoding="utf-8")
    else:
        content = f"# agent-regression-bench\n\n{AUTO_START}\n{AUTO_END}\n"

    if AUTO_START not in content or AUTO_END not in content:
        raise ValueError(f"README.md 里找不到 {AUTO_START} / {AUTO_END} 标记，先手动加上")

    before = content.split(AUTO_START)[0]
    after = content.split(AUTO_END)[1]
    new_content = before + auto_section + after
    README_PATH.write_text(new_content, encoding="utf-8")


def append_history(date_str: str, rows: list[dict]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not HISTORY_CSV.is_file()
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(HISTORY_COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    date_str,
                    r["model"],
                    f"{r['overall_pass']:.4f}",
                    "" if r["category_pass"]["single_step"] is None else f"{r['category_pass']['single_step']:.4f}",
                    "" if r["category_pass"]["multi_step"] is None else f"{r['category_pass']['multi_step']:.4f}",
                    "" if r["category_pass"]["should_refuse"] is None else f"{r['category_pass']['should_refuse']:.4f}",
                    "" if r["category_pass"]["should_clarify"] is None else f"{r['category_pass']['should_clarify']:.4f}",
                    "" if r["category_pass"]["injection"] is None else f"{r['category_pass']['injection']:.4f}",
                    f"{r['precision']:.4f}",
                    f"{r['cost_total_usd']:.6f}",
                ]
            )


def generate_report(date_str: str, repeat: int = 1) -> dict:
    date_dir = RESULTS_DIR / date_str
    scores = load_scores(date_dir)
    if not scores:
        raise SystemExit(f"{date_dir}/scores.json 不存在或为空，先跑 python -m bench.run")

    task_categories = load_task_categories()
    rows = summarize_by_model(scores, task_categories)
    counts = failure_type_counts(scores)
    agreement = judge_agreement_rate(scores)
    cfg = load_models_config()
    judge_slug = cfg.get("judge", {}).get("slug", "")

    n_tasks = len({s["task_id"] for s in scores})

    summary = {
        "date": date_str,
        "n_tasks": n_tasks,
        "n_models": len(rows),
        "repeat": repeat,
        "total_cost_usd": sum(r["cost_total_usd"] for r in rows),
        "judge_slug": judge_slug,
        "judge_agreement": agreement,
        "leaderboard": rows,
        "failure_type_counts": counts,
    }
    (date_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    auto_section = render_auto_section(date_str, rows, counts, agreement, n_tasks, repeat, judge_slug)
    update_readme(auto_section)
    append_history(date_str, rows)

    return summary


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 summary.json / README 自动段 / history.csv")
    parser.add_argument("--date", type=str, default=None, help="results/<date>/，默认今天")
    parser.add_argument("--repeat", type=int, default=1, help="这次运行的 repeat 值，写进 summary 的元信息")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    date_str = args.date or dt.date.today().isoformat()
    summary = generate_report(date_str, repeat=args.repeat)
    print(f"summary.json / README / history.csv 已更新：{date_str}，{summary['n_models']} 个模型")


if __name__ == "__main__":
    main()
