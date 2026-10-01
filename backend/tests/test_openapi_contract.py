"""契约同步:提交的 openapi.json 必须等于后端当前 schema(否则前端生成类型已漂移)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dump_openapi import OUT, render  # noqa: E402


def test_committed_openapi_matches_backend():
    assert OUT.exists() and OUT.read_text() == render(), "OpenAPI 与前端提交的 openapi.json 不一致:运行 `make contract` 重新生成并提交"
