"""§9 要求：两份假 scores.json，README 自动段能生成且表头正确、history.csv 追加一行。"""

import csv
import json

from bench import report

FAKE_TASK_CATEGORIES = {
    "f01_single": "single_step",
    "f02_multi": "multi_step",
    "f03_refuse": "should_refuse",
    "f04_clarify": "should_clarify",
    "f05_injection": "injection",
}


def _fake_score(task_id, model, passed, failure_type=None, **overrides):
    base = {
        "task_id": task_id,
        "model": model,
        "passed": passed,
        "failure_type": failure_type,
        "n_tool_calls": 2,
        "n_unneeded_calls": 0,
        "n_steps": 2,
        "latency_ms": 1000.0,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "cost_usd": 0.001,
        "judge_used": False,
        "judge_agrees_with_rules": None,
    }
    base.update(overrides)
    return base


def _setup_fake_env(tmp_path, monkeypatch):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    monkeypatch.setattr(report, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(report, "HISTORY_CSV", results_dir / "history.csv")
    monkeypatch.setattr(report, "README_PATH", tmp_path / "README.md")
    monkeypatch.setattr(report, "load_task_categories", lambda tasks_dir=None: FAKE_TASK_CATEGORIES)
    monkeypatch.setattr(report, "load_models_config", lambda: {"judge": {"slug": "model-b"}})
    return results_dir


def _write_scores(results_dir, date_str, scores):
    date_dir = results_dir / date_str
    date_dir.mkdir(parents=True)
    (date_dir / "scores.json").write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")


def test_generate_report_from_two_fake_score_files(tmp_path, monkeypatch):
    results_dir = _setup_fake_env(tmp_path, monkeypatch)

    day1_scores = [
        _fake_score("f01_single", "model-a", True),
        _fake_score("f02_multi", "model-a", False, "wrong_final_state"),
        _fake_score("f01_single", "model-b", True),
        _fake_score("f03_refuse", "model-b", True, judge_used=True, judge_agrees_with_rules=True),
    ]
    day2_scores = [
        _fake_score("f01_single", "model-a", True),
        _fake_score("f04_clarify", "model-a", False, "no_clarify"),
        _fake_score("f01_single", "model-b", True),
        _fake_score("f05_injection", "model-b", False, "injection_followed"),
    ]
    _write_scores(results_dir, "2026-09-18", day1_scores)
    _write_scores(results_dir, "2026-09-19", day2_scores)

    report.generate_report("2026-09-18")
    summary_day2 = report.generate_report("2026-09-19")

    # summary.json 结构
    assert summary_day2["date"] == "2026-09-19"
    assert summary_day2["n_models"] == 2
    models_in_summary = {r["model"] for r in summary_day2["leaderboard"]}
    assert models_in_summary == {"model-a", "model-b"}

    # history.csv：header + 2 天 * 2 模型 = 4 行
    history_path = results_dir / "history.csv"
    assert history_path.is_file()
    with open(history_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == report.HISTORY_COLUMNS
    assert len(rows) == 1 + 4  # header + 4 data rows

    # README 自动段：表头正确、markers 都在
    readme_text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert report.AUTO_START in readme_text
    assert report.AUTO_END in readme_text
    assert (
        "| model | overall pass | single | multi | refuse | clarify | injection "
        "| tool-call precision | avg steps | p50 latency | cost/task |" in readme_text
    )
    assert "已连续运行 2 天" in readme_text
    assert "累计 8 次 (task, model) 评测" in readme_text
    # judge 模型（model-b）被标注
    assert "model-b \\*" in readme_text
    assert "该模型同时也是本轮的 judge" in readme_text


def test_generate_report_twice_same_date_does_not_duplicate_history(tmp_path, monkeypatch):
    results_dir = _setup_fake_env(tmp_path, monkeypatch)
    scores = [
        _fake_score("f01_single", "model-a", True),
        _fake_score("f01_single", "model-b", True),
    ]
    _write_scores(results_dir, "2026-09-18", scores)

    report.generate_report("2026-09-18")
    report.generate_report("2026-09-18")  # 同一天重跑一次 report，不该攒出重复行

    with open(results_dir / "history.csv", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1 + 2  # header + 2 模型各一行，不是 4 行


def test_summarize_by_model_category_pass_rates():
    scores = [
        _fake_score("f01_single", "model-a", True),
        _fake_score("f02_multi", "model-a", False, "wrong_final_state"),
    ]
    rows = report.summarize_by_model(scores, FAKE_TASK_CATEGORIES)
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "model-a"
    assert row["overall_pass"] == 0.5
    assert row["category_pass"]["single_step"] == 1.0
    assert row["category_pass"]["multi_step"] == 0.0
    assert row["category_pass"]["should_refuse"] is None


def test_failure_type_counts_only_counts_failures():
    scores = [
        _fake_score("f01_single", "model-a", True),
        _fake_score("f02_multi", "model-a", False, "wrong_final_state"),
        _fake_score("f02_multi", "model-b", False, "wrong_final_state"),
    ]
    counts = report.failure_type_counts(scores)
    assert counts == {"model-a": {"wrong_final_state": 1}, "model-b": {"wrong_final_state": 1}}


def test_judge_agreement_rate():
    scores = [
        _fake_score("f03_refuse", "model-a", True, judge_used=True, judge_agrees_with_rules=True),
        _fake_score("f03_refuse", "model-b", False, "no_refusal", judge_used=True, judge_agrees_with_rules=False),
        _fake_score("f01_single", "model-a", True),  # 没有 judge，不计入一致率
    ]
    result = report.judge_agreement_rate(scores)
    assert result == {"n_pairs": 2, "agreement_rate": 0.5}


def test_generate_report_missing_scores_raises(tmp_path, monkeypatch):
    _setup_fake_env(tmp_path, monkeypatch)
    import pytest

    with pytest.raises(SystemExit):
        report.generate_report("2099-01-01")
