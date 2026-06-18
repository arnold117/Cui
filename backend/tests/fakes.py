from anneal.llm.client import _complete_json_with_retry

class FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    def complete(self, system: str, user: str) -> str:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return self._responses[-1] if self._responses else ""

    def complete_json(self, system: str, user: str, retries: int = 2) -> dict:
        return _complete_json_with_retry(self, system, user, retries)


class CapturingLLMClient(FakeLLMClient):
    """FakeLLMClient that records every (system, user) prompt it receives.

    Used to assert what the grill service actually passed to the LLM — e.g.
    whether the literature-evidence block made it into the prompt.
    """

    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return super().complete(system, user)

    @property
    def last_system(self) -> str:
        return self.calls[-1][0]

    @property
    def last_user(self) -> str:
        return self.calls[-1][1]
