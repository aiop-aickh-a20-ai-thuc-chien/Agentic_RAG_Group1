from __future__ import annotations

import json
from pathlib import Path

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.evaluation.runner import (
    read_url_list,
    run_base_url_evaluation,
)
from agentic_rag.ingestion.url.loader import LoadedUrlDocument


def test_read_url_list_ignores_blanks_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "\n# comment\nhttps://example.com/a\n\nhttps://example.com/b\n",
        encoding="utf-8",
    )

    assert read_url_list(path) == ["https://example.com/a", "https://example.com/b"]


def test_run_base_url_evaluation_writes_resumable_outputs(tmp_path: Path) -> None:
    url = "https://example.com/a"
    url_list = tmp_path / "urls.txt"
    url_list.write_text(f"{url}\n", encoding="utf-8")
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            {
                "version": "test",
                "samples": [
                    {
                        "sample_id": "example_a",
                        "input": {"source_url": url, "source": url},
                        "expectations": {
                            "min_chunk_count": 1,
                            "max_chunk_count": 1,
                            "required_metadata_keys": ["source", "source_type"],
                            "required_text_snippets": ["Example"],
                            "forbidden_text_snippets": ["Copyright"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_loader(_url: str) -> LoadedUrlDocument:
        return LoadedUrlDocument(
            markdown="# Example\n\nUseful body text.",
            chunks=[
                Chunk(
                    chunk_id="url_example_c0001",
                    text="# Example\n\nUseful body text.",
                    metadata={"source": url, "source_type": "unknown"},
                )
            ],
            artifacts=None,
        )

    summary = run_base_url_evaluation(
        url_list_path=url_list,
        golden_path=golden,
        output_dir=tmp_path / "out",
        use_browser_extractor=False,
        loader=fake_loader,
    )

    assert summary.processed_count == 1
    assert summary.passed_count == 1
    assert Path(summary.results_jsonl).exists()
    assert Path(summary.summary_json).exists()
    assert Path(summary.summary_markdown).exists()
