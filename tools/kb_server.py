"""kb MCP server：对固定 markdown 文档做关键词打分检索，不用 embedding，保证确定性。"""

import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kb"

mcp = FastMCP("kb")


def _load_docs() -> list[dict]:
    docs = []
    for path in sorted(FIXTURE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.strip().splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        body = "\n".join(lines[1:]).strip()
        docs.append({"path": path.name, "title": title, "body": body})
    return docs


def _keywords(query: str) -> list[str]:
    query = query.strip()
    # 中文没有天然分词边界，用 2-gram 近似关键词；同时保留原始英文/数字词。
    ascii_words = re.findall(r"[A-Za-z0-9]+", query)
    cjk_chars = re.findall(r"[一-鿿]", query)
    bigrams = ["".join(cjk_chars[i : i + 2]) for i in range(len(cjk_chars) - 1)]
    keywords = [w for w in (ascii_words + bigrams) if w]
    if query and query not in keywords:
        keywords.append(query)
    return keywords


def _score(doc: dict, keywords: list[str]) -> int:
    score = 0
    for kw in keywords:
        score += doc["title"].count(kw) * 3
        score += doc["body"].count(kw)
    return score


@mcp.tool()
def search_kb(query: str, top_k: int = 3) -> str:
    """在内部规章知识库里按关键词检索，返回命中文档标题和正文。查不到返回明确提示。"""
    docs = _load_docs()
    keywords = _keywords(query)
    scored = [(_score(doc, keywords), doc) for doc in docs]
    # 单个 2-gram 偶然命中标题的分值正好是 3（title 权重），
    # 阈值设在 3 以上以过滤这种噪声，需要标题+正文都命中或多个关键词命中。
    scored = [(s, d) for s, d in scored if s > 3]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["path"]))
    top = scored[: max(top_k, 0)]
    if not top:
        return "无相关文档"
    parts = [f"《{doc['title']}》\n{doc['body']}" for _, doc in top]
    return "\n\n".join(parts)


if __name__ == "__main__":
    mcp.run()
