"""weather MCP server：从固定 fixtures 查天气，零网络，确定性。"""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "weather.json"

mcp = FastMCP("weather")


def _load_weather() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def get_weather(city: str) -> str:
    """查询城市今天的天气（固定数据，支持中英文城市名）。城市不在表里时明确告知无数据，不猜测。"""
    data = _load_weather()
    key = (city or "").strip()
    entry = data.get(key)
    if entry is None:
        lower_index = {k.lower(): v for k, v in data.items()}
        entry = lower_index.get(key.lower())
    if entry is None:
        return f"{city}：无此城市天气数据。"
    return f"{city}今天天气：温度{entry['temp_c']}°C，{entry['condition']}。"


if __name__ == "__main__":
    mcp.run()
