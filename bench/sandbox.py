"""每个任务一个沙箱临时目录：写 setup、起停 5 个 MCP stdio server、读终态。"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

REPO_ROOT = Path(__file__).resolve().parent.parent

# 用 -m 以模块方式启动（cwd=REPO_ROOT），而不是直接跑脚本路径：
# fs_server / todo_server 里 `from tools._sandbox import ...` 需要 repo 根目录在 sys.path 上，
# 直接 `python tools/xxx_server.py` 只会把 tools/ 自己加进 sys.path，import 会失败。
SERVER_MODULES = {
    "weather": "tools.weather_server",
    "fs": "tools.fs_server",
    "todo": "tools.todo_server",
    "calc": "tools.calc_server",
    "kb": "tools.kb_server",
}


def write_setup(sandbox_dir: Path, setup: dict) -> None:
    files = (setup or {}).get("files", {})
    for rel_path, content in files.items():
        target = sandbox_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    todos = (setup or {}).get("todos")
    if todos:
        state = {"next_id": len(todos) + 1, "items": todos}
        (sandbox_dir / "todos.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def read_final_state(sandbox_dir: Path) -> dict:
    files = {}
    for path in sorted(sandbox_dir.rglob("*")):
        if path.is_file() and path.name != "todos.json":
            files[str(path.relative_to(sandbox_dir))] = path.read_text(
                encoding="utf-8", errors="replace"
            )

    todos_path = sandbox_dir / "todos.json"
    todos = []
    if todos_path.is_file():
        state = json.loads(todos_path.read_text(encoding="utf-8"))
        todos = state.get("items", [])

    return {"files": files, "todos": todos}


def _connections(sandbox_dir: Path) -> dict:
    env = {**os.environ, "SANDBOX_DIR": str(sandbox_dir)}
    return {
        name: {
            "command": sys.executable,
            "args": ["-m", module],
            "cwd": str(REPO_ROOT),
            "transport": "stdio",
            "env": env,
        }
        for name, module in SERVER_MODULES.items()
    }


@contextlib.asynccontextmanager
async def sandbox_session(setup: dict):
    """建临时沙箱目录 + 5 个 MCP server 的工具列表；退出时自动清理临时目录。

    每个 server 只开一个常驻 session，任务期间所有工具调用复用它——不用
    MultiServerMCPClient.get_tools() 的默认行为（每次工具调用都新开一个 session，
    也就是新起一个子进程）。实测在 5 模型并发、每任务好几次工具调用的负载下，
    默认行为的子进程 churn 大到会把某个 server 的 stdio JSON-RPC 帧撞坏
    （`Extra data` JSONDecodeError），常驻 session 把子进程数从"每次调用一个"
    降到"每个 server 一个"，规避这个问题。
    """
    with tempfile.TemporaryDirectory(prefix="agent-bench-") as tmp:
        sandbox_dir = Path(tmp).resolve()
        write_setup(sandbox_dir, setup)
        client = MultiServerMCPClient(_connections(sandbox_dir))
        async with AsyncExitStack() as stack:
            tools = []
            for name in SERVER_MODULES:
                session = await stack.enter_async_context(client.session(name))
                tools.extend(await load_mcp_tools(session))
            yield sandbox_dir, tools
