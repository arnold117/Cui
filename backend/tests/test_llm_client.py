import pytest
from cui.llm.client import _strip_markdown_fences
from cui.llm.errors import LLMResponseError
from tests.fakes import FakeLLMClient


class TestStripMarkdownFences:
    def test_strip_fences_json_block(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_markdown_fences(raw) == '{"key": "value"}'

    def test_strip_fences_plain_json(self):
        raw = '{"key": "value"}'
        assert _strip_markdown_fences(raw) == '{"key": "value"}'

    def test_strip_fences_no_fences(self):
        raw = "plain text response"
        assert _strip_markdown_fences(raw) == "plain text response"

    def test_strip_fences_text_before(self):
        raw = 'Here is the result:\n```json\n{"key": "val"}\n```'
        assert _strip_markdown_fences(raw) == '{"key": "val"}'

    def test_strip_fences_text_after(self):
        raw = '```json\n{"key": "val"}\n```\nHope this helps!'
        assert _strip_markdown_fences(raw) == '{"key": "val"}'

    def test_strip_fences_text_both_sides(self):
        raw = 'Here is the result:\n```json\n{"key": "val"}\n```\nHope this helps!'
        assert _strip_markdown_fences(raw) == '{"key": "val"}'


class TestCompleteJson:
    def test_complete_json_clean(self):
        client = FakeLLMClient(['{"result": "ok"}'])
        out = client.complete_json("sys", "usr")
        assert out == {"result": "ok"}

    def test_complete_json_with_fences(self):
        client = FakeLLMClient(['```json\n{"result": "ok"}\n```'])
        out = client.complete_json("sys", "usr")
        assert out == {"result": "ok"}

    def test_complete_json_retry_on_bad_then_good(self):
        client = FakeLLMClient(["not json at all", '{"fixed": true}'])
        out = client.complete_json("sys", "usr", retries=2)
        assert out == {"fixed": True}

    def test_complete_json_all_retries_fail_raises(self):
        client = FakeLLMClient(["bad", "still bad", "nope"])
        with pytest.raises(LLMResponseError, match="Failed to parse JSON"):
            client.complete_json("sys", "usr", retries=2)

    def test_complete_json_list_response_wrapped(self):
        client = FakeLLMClient(['[1, 2, 3]'])
        out = client.complete_json("sys", "usr")
        assert out == {"data": [1, 2, 3]}
