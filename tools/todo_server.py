"""todo MCP server：待办事项存在沙箱内的 todos.json，状态可重置、可读取。"""

import json
import re

from mcp.server.fastmcp import FastMCP

from tools._sandbox import sandbox_dir

mcp = FastMCP("todo")

DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _todos_path():
    return sandbox_dir() / "todos.json"


def _load() -> dict:
    path = _todos_path()
    if not path.is_file():
        return {"next_id": 1, "items": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(state: dict) -> None:
    with open(_todos_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


@mcp.tool()
def add_todo(title: str, due: str | None = None) -> str:
    """新增一条待办。due 可选，格式必须是 YYYY-MM-DD，格式不对会报错且不会新增。"""
    if due is not None and not DUE_RE.match(due):
        return f"日期格式错误，需为 YYYY-MM-DD：{due}"
    state = _load()
    item = {"id": state["next_id"], "title": title, "due": due, "done": False}
    state["items"].append(item)
    state["next_id"] += 1
    _save(state)
    return f"已新增待办 #{item['id']}：{title}"


@mcp.tool()
def list_todos() -> str:
    """列出所有待办事项（JSON 格式）。"""
    state = _load()
    if not state["items"]:
        return "当前没有待办"
    return json.dumps(state["items"], ensure_ascii=False)


@mcp.tool()
def complete_todo(id: int) -> str:
    """把某条待办标记为已完成。"""
    state = _load()
    for item in state["items"]:
        if item["id"] == id:
            item["done"] = True
            _save(state)
            return f"待办 #{id} 已标记完成"
    return f"待办不存在：{id}"


@mcp.tool()
def remove_todo(id: int) -> str:
    """删除某条待办。"""
    state = _load()
    for item in state["items"]:
        if item["id"] == id:
            state["items"].remove(item)
            _save(state)
            return f"待办 #{id} 已删除"
    return f"待办不存在：{id}"


if __name__ == "__main__":
    mcp.run()
