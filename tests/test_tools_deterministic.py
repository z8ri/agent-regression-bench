"""§9 要求：每个工具确定性、fs/calc/weather 的越界与拒答行为。"""

import json

import pytest

from tools import calc_server, fs_server, kb_server, todo_server, weather_server


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DIR", str(tmp_path))
    return tmp_path


# ---------- weather ----------


def test_weather_deterministic_same_input_same_output():
    r1 = weather_server.get_weather("上海")
    r2 = weather_server.get_weather("上海")
    assert r1 == r2
    assert "26" in r1 and "多云" in r1


def test_weather_zh_en_alias_agree():
    zh = weather_server.get_weather("北京")
    en = weather_server.get_weather("Beijing")
    assert "18" in zh and "18" in en
    assert "晴" in zh and "晴" in en


def test_weather_unknown_city_returns_explicit_no_data_not_raise():
    result = weather_server.get_weather("乌兰巴托")
    assert "无此城市天气数据" in result


# ---------- fs ----------


def test_fs_write_read_deterministic():
    fs_server.write_file("a.txt", "hello")
    r1 = fs_server.read_file("a.txt")
    r2 = fs_server.read_file("a.txt")
    assert r1 == r2 == "hello"


def test_fs_rejects_parent_traversal():
    result = fs_server.write_file("../escape.txt", "x")
    assert "不合法" in result


def test_fs_rejects_absolute_path():
    result = fs_server.write_file("/etc/passwd", "x")
    assert "不合法" in result


def test_fs_read_missing_file_returns_error_string_not_raise():
    result = fs_server.read_file("missing.txt")
    assert "不存在" in result


def test_fs_delete_then_list():
    fs_server.write_file("b.txt", "x")
    assert "b.txt" in fs_server.list_files()
    fs_server.delete_file("b.txt")
    assert "b.txt" not in fs_server.list_files()


def test_fs_append():
    fs_server.write_file("c.txt", "1")
    fs_server.append_file("c.txt", "2")
    assert fs_server.read_file("c.txt") == "12"


# ---------- todo ----------


def test_todo_add_list_complete_remove_deterministic():
    r1 = todo_server.add_todo("提交报销", "2026-09-29")
    assert "#1" in r1
    listing = json.loads(todo_server.list_todos())
    assert listing == [
        {"id": 1, "title": "提交报销", "due": "2026-09-29", "done": False}
    ]
    todo_server.complete_todo(1)
    listing2 = json.loads(todo_server.list_todos())
    assert listing2[0]["done"] is True
    r2 = todo_server.remove_todo(1)
    assert "已删除" in r2
    assert todo_server.list_todos() == "当前没有待办"


def test_todo_rejects_bad_due_format():
    result = todo_server.add_todo("x", "明天")
    assert "格式错误" in result
    assert todo_server.list_todos() == "当前没有待办"


def test_todo_complete_missing_id_returns_error():
    assert "不存在" in todo_server.complete_todo(999)


# ---------- calc ----------


def test_calc_basic_expression():
    assert calc_server.calculate("(1250 - 380) * 1.13") == "983.1"


def test_calc_deterministic():
    r1 = calc_server.calculate("2 + 2 * 2")
    r2 = calc_server.calculate("2 + 2 * 2")
    assert r1 == r2 == "6"


def test_calc_rejects_letters_not_eval():
    result = calc_server.calculate("__import__('os').system('ls')")
    assert "非法表达式" in result


def test_calc_rejects_division_by_zero():
    assert calc_server.calculate("1/0") == "除数不能为零"


# ---------- kb ----------


def test_kb_search_deterministic():
    r1 = kb_server.search_kb("报销流程要求几天")
    r2 = kb_server.search_kb("报销流程要求几天")
    assert r1 == r2
    assert "报销政策" in r1
    assert "7" in r1


def test_kb_search_no_match_returns_explicit_message():
    assert kb_server.search_kb("外星人入侵怎么办") == "无相关文档"


def test_kb_meeting_room_doc_contains_injection_bait():
    result = kb_server.search_kb("会议室预订规则")
    assert "会议室预订规则" in result
    assert "SYSTEM" in result
