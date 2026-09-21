"""沙箱目录相关的共享小工具，供各 MCP server 内部使用。"""

import os
from pathlib import Path


def sandbox_dir() -> Path:
    raw = os.environ.get("SANDBOX_DIR")
    if not raw:
        raise RuntimeError("环境变量 SANDBOX_DIR 未设置")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def resolve_in_sandbox(rel_path: str) -> Path | None:
    """将相对路径解析到沙箱内的绝对路径；越界/绝对路径返回 None。"""
    if not rel_path or os.path.isabs(rel_path):
        return None
    if ".." in Path(rel_path).parts:
        return None
    base = sandbox_dir()
    target = (base / rel_path).resolve()
    if target != base and base not in target.parents:
        return None
    return target
