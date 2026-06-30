"""Deterministic flat-versus-semantic recall@3 benchmark for VinFast chunks."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from rank_bm25 import BM25Okapi

from agentic_rag.ingestion.integration.url.vinfast import VinFastProduct, product_chunks

ROOT = Path(__file__).resolve().parent


def _products() -> list[VinFastProduct]:
    captured_at = datetime(2026, 6, 22, tzinfo=UTC)
    return [
        VinFastProduct(
            product_type="Real Car",
            model_name="VF 3",
            variant="Eco",
            base_price_vnd=268_780_000,
            battery_subscription=True,
            specs={
                "motor": "01 Motor",
                "max_power_kW": 30,
                "max_torque_Nm": 110,
                "range_km": 215,
                "fast_charge_time_min": "36 minutes (10% - 70%)",
                "drive_type": "RWD",
            },
            promotions=[
                "ĐẶT CỌC 15.000.000 VNĐ",
                "Mức giá tham khảo, áp dụng theo điều khoản & điều kiện.",
            ],
            source_url="https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html",
            scraped_at=captured_at,
        ),
        VinFastProduct(
            product_type="Real Car",
            model_name="VF 9",
            variant="Eco",
            base_price_vnd=1_274_150_000,
            battery_subscription=False,
            specs={
                "range_per_charge": "626 km",
                "power": "402 hp",
                "torque": "620 Nm",
                "warranty": "200.000 km or 10 years",
            },
            promotions=["Free charging up to 3 years under the V-Green program"],
            source_url="https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
            scraped_at=captured_at,
        ),
    ]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w.-]+", text.casefold())


def _flat_windows(products: list[VinFastProduct], size: int = 180) -> list[str]:
    windows: list[str] = []
    for product in products:
        raw = json.dumps(product.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        windows.extend(raw[offset : offset + size] for offset in range(0, len(raw), size))
    return windows


def _recall_at_3(corpus: list[str], questions: list[dict[str, str]]) -> float:
    index = BM25Okapi([_tokens(text) for text in corpus])
    hits = 0
    for item in questions:
        scores = index.get_scores(_tokens(item["question"]))
        ranked = sorted(range(len(corpus)), key=lambda position: scores[position], reverse=True)[:3]
        answer = item["answer"].casefold()
        hits += any(answer in corpus[position].casefold() for position in ranked)
    return hits / len(questions)


def main() -> None:
    questions = json.loads((ROOT / "vinfast_chunking_questions.json").read_text(encoding="utf-8"))
    products = _products()
    flat = _flat_windows(products)
    semantic = [chunk.text for product in products for chunk in product_chunks(product)]
    print(f"questions={len(questions)}")
    print(f"flat_chunks={len(flat)} flat_recall_at_3={_recall_at_3(flat, questions):.3f}")
    print(
        f"semantic_chunks={len(semantic)} "
        f"semantic_recall_at_3={_recall_at_3(semantic, questions):.3f}"
    )


if __name__ == "__main__":
    main()
