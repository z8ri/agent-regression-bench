"""fs MCP server：沙箱内的文件读写，路径越界一律拒绝并返回错误字符串。"""

from mcp.server.fastmcp import FastMCP

from tools._sandbox import resolve_in_sandbox, sandbox_dir

mcp = FastMCP("fs")


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """在沙箱内写文件（覆盖已有内容）。path 不能是绝对路径或包含 ..。"""
    target = resolve_in_sandbox(path)
    if target is None:
        return f"路径不合法：{path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入：{path}"


@mcp.tool()
def read_file(path: str) -> str:
    """读取沙箱内文件内容。"""
    target = resolve_in_sandbox(path)
    if target is None:
        return f"路径不合法：{path}"
    if not target.is_file():
        return f"文件不存在：{path}"
    return target.read_text(encoding="utf-8")


@mcp.tool()
def list_files() -> str:
    """列出沙箱内所有文件（相对路径，按名称排序）。"""
    base = sandbox_dir()
    files = sorted(
        str(p.relative_to(base)) for p in base.rglob("*") if p.is_file()
    )
    if not files:
        return "沙箱内没有文件"
    return "\n".join(files)


@mcp.tool()
def append_file(path: str, content: str) -> str:
    """向沙箱内文件追加内容；文件不存在则新建。"""
    target = resolve_in_sandbox(path)
    if target is None:
        return f"路径不合法：{path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(content)
    return f"已追加：{path}"


@mcp.tool()
def delete_file(path: str) -> str:
    """删除沙箱内文件。"""
    target = resolve_in_sandbox(path)
    if target is None:
        return f"路径不合法：{path}"
    if not target.is_file():
        return f"文件不存在：{path}"
    target.unlink()
    return f"已删除：{path}"


if __name__ == "__main__":
    mcp.run()
