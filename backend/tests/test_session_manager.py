import pytest

from app.session import store as store_mod
from app.session.manager import record_tool_result, recall_payload


@pytest.fixture(autouse=True)
def reset_store(monkeypatch):
    monkeypatch.setattr(store_mod, "_store", store_mod.InMemoryStore())
    yield


@pytest.mark.asyncio
async def test_small_result_inlined(monkeypatch):
    async def fake_summarize(*args, **kwargs):
        return "should-not-be-called"

    monkeypatch.setattr("app.agent.summarizer.summarize", fake_summarize)
    view = await record_tool_result(
        session_id="s1",
        tool_name="http_fetch",
        tool_args={"url": "https://example.com"},
        payload="hello world",
    )
    assert "result" in view
    assert view["result"] == "hello world"
    assert view["handle"].startswith("tr_")


@pytest.mark.asyncio
async def test_large_result_summarized(monkeypatch):
    async def fake_summarize(payload, **kwargs):
        return "summary"

    monkeypatch.setattr("app.agent.summarizer.summarize", fake_summarize)
    big = "x " * 5000
    view = await record_tool_result(
        session_id="s1",
        tool_name="http_fetch",
        tool_args={"url": "https://example.com"},
        payload=big,
    )
    assert view.get("result") is None
    assert view["summary"] == "summary"

    payload, rec = await recall_payload(view["handle"])
    assert rec is not None
    assert payload == big
