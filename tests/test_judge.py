"""judge.py 不打真实网络请求：只测 JSON 抽取逻辑和三个 judge_* 函数用假模型的行为。"""

import pytest

from bench.scoring import judge


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeModel:
    def __init__(self, content: str):
        self._content = content
        self.received_messages = None

    async def ainvoke(self, messages):
        self.received_messages = messages
        return FakeResponse(self._content)


def test_extract_json_object_plain():
    assert judge.extract_json_object('{"is_refusal": true}') == {"is_refusal": True}


def test_extract_json_object_with_surrounding_text():
    text = '好的，这是结果：\n{"is_refusal": false}\n谢谢'
    assert judge.extract_json_object(text) == {"is_refusal": False}


def test_extract_json_object_no_json_raises():
    with pytest.raises(ValueError):
        judge.extract_json_object("没有 json 在这里")


@pytest.mark.asyncio
async def test_judge_refusal_true():
    model = FakeModel('{"is_refusal": true}')
    result = await judge.judge_refusal("查一下乌兰巴托天气", "抱歉，没有这个城市的数据。", model)
    assert result == {"is_refusal": True}


@pytest.mark.asyncio
async def test_judge_clarify_false():
    model = FakeModel('{"asked_clarifying_question": false}')
    result = await judge.judge_clarify("帮我加个待办", "好的，已经加上了。", model)
    assert result == {"asked_clarifying_question": False}


@pytest.mark.asyncio
async def test_judge_correctness_true():
    model = FakeModel('{"correct": true}')
    result = await judge.judge_correctness("算一下", "983.1", "983.1", model)
    assert result == {"correct": True}


@pytest.mark.asyncio
async def test_judge_malformed_output_returns_none():
    model = FakeModel("我不知道该怎么回答")
    result = await judge.judge_refusal("x", "y", model)
    assert result == {"is_refusal": None}


@pytest.mark.asyncio
async def test_judge_trace_routes_by_behavior():
    refuse_model = FakeModel('{"is_refusal": true}')
    assert await judge.judge_trace("q", "a", "refuse", None, refuse_model) == {"is_refusal": True}

    clarify_model = FakeModel('{"asked_clarifying_question": true}')
    assert await judge.judge_trace("q", "a", "clarify", None, clarify_model) == {
        "asked_clarifying_question": True
    }

    answer_model = FakeModel('{"correct": false}')
    assert await judge.judge_trace("q", "a", "answer", "参考答案", answer_model) == {"correct": False}

    # answer 类没有 reference_answer 时不问 judge
    unused_model = FakeModel('{"correct": true}')
    assert await judge.judge_trace("q", "a", "answer", None, unused_model) is None
