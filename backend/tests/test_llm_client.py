import json
from types import SimpleNamespace

import pytest
from cui.llm.client import AnthropicClient, _strip_markdown_fences
from cui.llm.errors import LLMResponseError
from cui.research_universe.challenge_generator import CHALLENGE_SCHEMA, RealChallengeGenerator, RealEvidenceCandidateGenerator
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


# --- #33: AnthropicClient sends a json_schema only when the caller gives one ---

class _FakeMessages:
    """Stands in for anthropic.Anthropic().messages; records create() kwargs."""
    def __init__(self, texts):
        self.texts, self.calls = list(texts), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.texts.pop(0))])


def _anthropic(texts):
    client = AnthropicClient(api_key="test", model="m")
    client._client = SimpleNamespace(messages=_FakeMessages(texts))
    return client, client._client.messages


CHALLENGE = json.dumps({"attack_surface": "a", "why_it_matters": "w", "self_check_method": "s", "uncertainty": "low", "title": "t"})
EVIDENCE = json.dumps({"relation": "silent", "rationale": "r", "evidence_highlight": "h", "uncertainty": "low"})


def test_anthropic_without_schema_sends_no_output_config_and_parses_fenced_text_with_retry():
    client, messages = _anthropic(["not json", '```json\n{"query_en": "rlhf reasoning"}\n```'])
    assert client.complete_json("sys", "usr") == {"query_en": "rlhf reasoning"}
    assert len(messages.calls) == 2 and all("output_config" not in c for c in messages.calls)


def test_anthropic_with_schema_sends_exactly_that_schema():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"], "additionalProperties": False}
    client, messages = _anthropic(['{"x": "y"}'])
    assert client.complete_json("sys", "usr", schema=schema) == {"x": "y"}
    assert messages.calls[0]["output_config"] == {"format": {"type": "json_schema", "schema": schema}}


@pytest.mark.parametrize("path", [
    lambda g: g.generate(question="q?", claim="c."),
    lambda g: g.generate_additional(question="q?", claim="c.", prior_attack_surfaces=["used"]),
    lambda g: g.generate_literature(question="q?", claim="c.", materials=[{"locator": "arxiv:1", "excerpt": "e"}], prior_attack_surfaces=[]),
], ids=["narrow", "expanded", "literature"])
def test_challenge_paths_send_the_challenge_schema(path):
    client, messages = _anthropic([CHALLENGE])
    path(RealChallengeGenerator(client, "m"))
    assert messages.calls[0]["output_config"]["format"]["schema"] == CHALLENGE_SCHEMA


def test_evidence_screening_sends_no_schema():
    client, messages = _anthropic([EVIDENCE])
    draft = RealEvidenceCandidateGenerator(client, "m").generate(claim="c.", material_excerpt="e", parse_status="parsed")
    assert draft.relation == "silent" and "output_config" not in messages.calls[0]
