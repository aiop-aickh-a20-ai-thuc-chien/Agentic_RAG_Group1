import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.integration.url.vinfast import (
    ChangeStore,
    ExtractionStage,
    FailedUrlLog,
    PlaywrightSessionAdapter,
    VinFastExtractionPipeline,
    VinFastProduct,
    content_hash,
    product_chunks,
    retry_async,
    upsert_changed_chunks,
)
from agentic_rag.ingestion.integration.url.vinfast.worker import start_scheduler


def _product(**updates: object) -> VinFastProduct:
    values: dict[str, object] = {
        "product_type": "Real Car",
        "model_name": "VF 9",
        "variant": "Plus",
        "base_price_vnd": 1_699_000_000,
        "battery_subscription": False,
        "specs": {"range_km": 626, "airbags": 11, "screen": "15.6 inch"},
        "promotions": ["Free charging"],
        "source_url": "https://example.test/vf9",
        "scraped_at": datetime(2026, 6, 20, 2, tzinfo=UTC),
    }
    values.update(updates)
    return VinFastProduct.model_validate(values)


def test_product_computes_deterministic_id_and_rejects_wrong_id() -> None:
    first = _product()
    second = _product(scraped_at=datetime(2026, 6, 21, 2, tzinfo=UTC))
    assert first.chunk_id == second.chunk_id

    with pytest.raises(ValidationError, match="deterministic product identity"):
        _product(chunk_id="wrong")


def test_scale_model_requires_ratio() -> None:
    with pytest.raises(ValidationError, match="scale_ratio"):
        _product(product_type="Scale Model")


def test_retry_uses_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    assert asyncio.run(retry_async(operation, base_delay=2, sleep=sleep)) == "ok"
    assert delays == [2, 4]


def test_pipeline_falls_back_network_to_dom_without_calling_vlm() -> None:
    calls: list[str] = []

    async def network(url: str) -> None:
        calls.append(f"network:{url}")
        return None

    async def dom(url: str) -> dict[str, object]:
        calls.append(f"dom:{url}")
        return _product().model_dump(mode="json")

    async def vlm(url: str) -> dict[str, object]:
        calls.append(f"vlm:{url}")
        return _product().model_dump(mode="json")

    pipeline = VinFastExtractionPipeline(
        [
            ExtractionStage(name="network", extract=network),
            ExtractionStage(name="dom", extract=dom),
            ExtractionStage(name="vlm", extract=vlm),
        ],
        retries=1,
    )
    products = asyncio.run(pipeline.extract("https://example.test/vf9"))
    assert products[0].model_name == "VF 9"
    assert calls == ["network:https://example.test/vf9", "dom:https://example.test/vf9"]


def test_terminal_failure_is_logged_as_jsonl(tmp_path: Path) -> None:
    async def fail(url: str) -> None:
        raise TimeoutError(url)

    path = tmp_path / "failed_urls.jsonl"
    pipeline = VinFastExtractionPipeline(
        [ExtractionStage(name="network", extract=fail)],
        failed_urls=FailedUrlLog(path),
        retries=1,
    )
    with pytest.raises(RuntimeError, match="VinFast extraction failed"):
        asyncio.run(pipeline.extract("https://example.test/blocked"))
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["url"] == "https://example.test/blocked"
    assert "TimeoutError" not in record["reason"]


def test_change_store_writes_hash_and_only_snapshots_changes(tmp_path: Path) -> None:
    store = ChangeStore(tmp_path)
    assert store.record("vf9_plus", {"price": 1}, captured_at=datetime(2026, 6, 20))
    assert not store.record("vf9_plus", {"price": 1}, captured_at=datetime(2026, 6, 21))
    assert store.record("vf9_plus", {"price": 2}, captured_at=datetime(2026, 6, 21))
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})
    assert (tmp_path / "vf9_plus_2026-06-20.json").exists()
    assert (tmp_path / "vf9_plus_2026-06-21.json").exists()


def test_product_chunks_are_semantic_and_have_complete_metadata() -> None:
    chunks = product_chunks(_product())
    by_category = {chunk.metadata["category"]: chunk for chunk in chunks}
    assert {"range_charging", "safety", "interior", "pricing"} <= set(by_category)
    pricing = by_category["pricing"]
    assert pricing.metadata["model"] == "VF 9"
    assert pricing.metadata["variant"] == "Plus"
    assert pricing.metadata["battery_option"] == "Mua pin"
    assert "Mua pin" in pricing.text
    assert pricing.metadata["scraped_at"] == "2026-06-20T02:00:00+00:00"
    assert pricing.metadata["chunk_id"] == pricing.chunk_id


def test_playwright_adapter_registers_network_before_navigation() -> None:
    calls: list[str] = []

    class Response:
        async def json(self) -> dict[str, object]:
            return {"data": [_product().model_dump(mode="json")]}

    class Page:
        def on(self, event: str, callback: Any) -> None:
            calls.append(f"on:{event}")
            self.callback = callback

        async def goto(self, url: str, *, wait_until: str) -> None:
            calls.append(f"goto:{url}:{wait_until}")
            await self.callback(Response())

        async def wait_for_timeout(self, milliseconds: int) -> None:
            calls.append(f"wait:{milliseconds}")

    adapter = PlaywrightSessionAdapter(Page(), network_settle_ms=25)
    pipeline = VinFastExtractionPipeline(adapter.stages(), retries=1)
    products = asyncio.run(pipeline.extract("https://example.test/vf9"))

    assert products == [_product()]
    assert calls == [
        "on:response",
        "goto:https://example.test/vf9:domcontentloaded",
        "wait:25",
    ]


def test_playwright_adapter_falls_back_on_same_page() -> None:
    calls: list[str] = []

    class Response:
        async def json(self) -> dict[str, object]:
            return {"not": "a product"}

    class Locator:
        async def inner_text(self) -> str:
            calls.append("dom")
            return "VF 9 Plus"

    class Page:
        def on(self, event: str, callback: Any) -> None:
            calls.append(f"on:{event}")
            self.callback = callback

        async def goto(self, url: str, *, wait_until: str) -> None:
            calls.append("goto")
            await self.callback(Response())

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        def locator(self, selector: str) -> Locator:
            calls.append(f"locator:{selector}")
            return Locator()

        async def screenshot(self, *, full_page: bool) -> bytes:
            raise AssertionError("VLM must not run after DOM succeeds")

    adapter = PlaywrightSessionAdapter(
        Page(), text_extractor=lambda text, url: _product(source_url=url), network_settle_ms=0
    )
    products = asyncio.run(
        VinFastExtractionPipeline(adapter.stages(), retries=1).extract("https://example.test/vf9")
    )

    assert products[0].model_name == "VF 9"
    assert calls == ["on:response", "goto", "locator:body", "dom"]


def test_playwright_adapter_rejects_http_error_before_fallback() -> None:
    class Response:
        status = 404

    class Page:
        def on(self, event: str, callback: object) -> None:
            return None

        async def goto(self, url: str, *, wait_until: str) -> Response:
            return Response()

    pipeline = VinFastExtractionPipeline(
        PlaywrightSessionAdapter(Page(), network_settle_ms=0).stages(), retries=1
    )

    with pytest.raises(RuntimeError, match="HTTP 404"):
        asyncio.run(pipeline.extract("https://example.test/missing"))


def test_changed_chunk_gate_is_idempotent(tmp_path: Path) -> None:
    chunks = product_chunks(_product())
    writes: list[list[str]] = []

    def writer(values: list[Chunk]) -> dict[str, object]:
        writes.append([value.chunk_id for value in values])
        return {"enabled": True, "chunk_count": len(values), "vector_store": "pgvector"}

    store = ChangeStore(tmp_path)
    first = upsert_changed_chunks(chunks, store, writer=writer)
    second = upsert_changed_chunks(chunks, store, writer=writer)

    assert first["chunk_count"] == len(chunks)
    assert second == {"enabled": True, "chunk_count": 0, "skipped": len(chunks)}
    assert writes == [[chunk.chunk_id for chunk in chunks]]


def test_changed_chunk_gate_upserts_modified_content(tmp_path: Path) -> None:
    original = product_chunks(_product())
    modified = product_chunks(_product(base_price_vnd=1_700_000_000))
    writes: list[list[Chunk]] = []

    def writer(values: list[Chunk]) -> dict[str, object]:
        writes.append(values)
        return {"enabled": True, "chunk_count": len(values)}

    store = ChangeStore(tmp_path)
    upsert_changed_chunks(original, store, writer=writer)
    trace = upsert_changed_chunks(modified, store, writer=writer)

    assert trace["chunk_count"] == 1
    assert writes[-1][0].metadata["category"] == "pricing"


def test_changed_chunk_gate_does_not_advance_hash_after_failed_write(tmp_path: Path) -> None:
    chunks = product_chunks(_product())
    store = ChangeStore(tmp_path)

    def fail(values: list[Chunk]) -> dict[str, object]:
        raise RuntimeError("Neon unavailable")

    with pytest.raises(RuntimeError, match="Neon unavailable"):
        upsert_changed_chunks(chunks, store, writer=fail)

    writes: list[Chunk] = []

    def succeed(values: list[Chunk]) -> dict[str, object]:
        writes.extend(values)
        return {"enabled": True, "chunk_count": len(values)}

    upsert_changed_chunks(chunks, store, writer=succeed)
    assert len(writes) == len(chunks)


def test_dedicated_worker_starts_one_timezone_aware_scheduler() -> None:
    calls: list[object] = []

    class Scheduler:
        def start(self) -> None:
            calls.append("start")

    async def job() -> None:
        calls.append("job")

    def factory(run_pipeline: object, *, hour: int, timezone: str) -> Scheduler:
        calls.extend([run_pipeline, hour, timezone])
        return Scheduler()

    scheduler = start_scheduler(job, hour=3, scheduler_factory=factory)

    assert isinstance(scheduler, Scheduler)
    assert calls == [job, 3, "Asia/Ho_Chi_Minh", "start"]
