from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from agentic_rag.core.contracts import (
    Chunk,
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
)
from agentic_rag.ingestion.url.dom import (
    append_visual_semantics_markdown,
    extract_visual_semantics,
)
from agentic_rag.ingestion.url.llm_review import (
    UrlLlmReviewEvidence,
    UrlLlmReviewInput,
    review_url_artifacts_with_llm,
)
from agentic_rag.ingestion.url.loader import (
    _with_visual_semantics_metadata,
    load_html_with_artifacts,
)


def test_extract_visual_semantics_finds_old_price_hidden_text_and_generated_label() -> None:
    semantics = extract_visual_semantics(
        """
        <html>
          <head>
            <style>.price::before { content: "Price:"; }</style>
          </head>
          <body>
            <main>
              <p>Current price 1.393.180.000 VND</p>
              <p><del>1.699.000.000 VND</del></p>
              <p style="display:none">Hidden stock price 1.888.000.000 VND</p>
            </main>
          </body>
        </html>
        """
    )

    kinds = {fact.kind for fact in semantics.facts}

    assert "old_price" in kinds
    assert "hidden_text" in kinds
    assert "generated_label" in kinds
    assert semantics.old_prices[0].text == "1.699.000.000 VND"
    assert semantics.old_prices[0].trusted_for_retrieval is True
    hidden_fact = next(fact for fact in semantics.facts if fact.kind == "hidden_text")
    assert hidden_fact.trusted_for_retrieval is False


def test_append_visual_semantics_markdown_adds_strikethrough_old_price() -> None:
    semantics = extract_visual_semantics("<p><s>1.699.000.000 VND</s></p>")

    markdown = append_visual_semantics_markdown(
        "# VF 9\n\nCurrent price 1.393.180.000 VND", semantics, title="VF 9"
    )

    assert "## Visual Pricing Evidence" in markdown
    assert "~~1.699.000.000 VND~~" in markdown


def test_append_visual_semantics_markdown_applies_to_existing_price_context() -> None:
    semantics = extract_visual_semantics("<p><s>1.699.000.000 VND</s></p>")

    markdown = append_visual_semantics_markdown(
        "# VF 9\n\nCurrent price 1.393.180.000 VND. Original price 1.699.000.000 VND.",
        semantics,
        title="VF 9",
    )

    assert "Visual Pricing Evidence" not in markdown
    assert "Original price ~~1.699.000.000 VND~~" in markdown


def test_load_html_with_artifacts_preserves_visual_price_metadata(tmp_path: Path) -> None:
    loaded = load_html_with_artifacts(
        """
        <html>
          <head><title>VF 9</title></head>
          <body>
            <main>
              <h1>VF 9</h1>
              <p>Current price 1.393.180.000 VND</p>
              <p>
                Original price
                <span style="text-decoration: line-through">1.699.000.000 VND</span>
              </p>
            </main>
          </body>
        </html>
        """,
        source="https://shop.vinfastauto.com/vn_vi/vf9",
        source_url="https://shop.vinfastauto.com/vn_vi/vf9",
        data_artifact_dir=tmp_path,
        run_id="visual-price",
    )

    visual_chunks = [chunk for chunk in loaded.chunks if chunk.metadata.get("original_price")]

    assert visual_chunks
    assert any("~~1.699.000.000 VND~~" in chunk.text for chunk in loaded.chunks)
    assert not any("Visual Pricing Evidence" in chunk.text for chunk in loaded.chunks)
    assert visual_chunks[0].metadata["original_price"] == "1.699.000.000 VND"
    assert visual_chunks[0].metadata["section_origin"] == "source_data_static"
    assert visual_chunks[0].metadata["trusted_for_retrieval"] is True
    assert loaded.artifacts is not None
    assert loaded.artifacts.visual_semantics_path is not None
    payload = json.loads(loaded.artifacts.visual_semantics_path.read_text(encoding="utf-8"))
    assert payload["facts"][0]["kind"] == "old_price"


def test_visual_debug_chunks_are_marked_for_metadata_prefilter() -> None:
    semantics = extract_visual_semantics("<p><s>1.699.000.000 VND</s></p>")
    semantic_chunk = Chunk(
        chunk_id="semantic",
        text="VF 9 original price ~~1.699.000.000 VND~~.",
        metadata={"source": "unit", "source_type": "official"},
    )
    visual_debug_chunk = Chunk(
        chunk_id="visual-debug",
        text="## Visual Pricing Evidence\n\n- VF 9 original price: ~~1.699.000.000 VND~~.",
        metadata={"source": "unit", "source_type": "official"},
    )

    semantic_chunk, visual_debug_chunk = _with_visual_semantics_metadata(
        [semantic_chunk, visual_debug_chunk],
        semantics=semantics,
    )

    assert semantic_chunk.metadata["trusted_for_retrieval"] is True
    assert semantic_chunk.metadata.get("metadata_prefilter_exclude") is None
    assert visual_debug_chunk.metadata["chunk_type"] == "visual_debug"
    assert visual_debug_chunk.metadata["trusted_for_retrieval"] is False
    assert visual_debug_chunk.metadata["retrieval_visibility"] == "debug_only"
    assert visual_debug_chunk.metadata["metadata_prefilter_exclude"] is True


def test_url_llm_review_uses_client_and_marks_unvalidated_facts() -> None:
    class FakeClient:
        def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
            assert "Deep Ocean" in request.prompt
            return LLMCompletionOutput(
                text=json.dumps(
                    {
                        "proposed_markdown": "VF 9 selected color: Deep Ocean.",
                        "semantic_role": "dynamic_state",
                        "field_mapping": {
                            "variant_options.color": "Deep Ocean",
                            "product_price": "2.000.000.000 VND",
                        },
                        "evidence_refs": ["dom:color"],
                        "confidence": 0.8,
                        "needs_human_review": False,
                        "unvalidated_facts": [],
                    }
                ),
                provider="test",
                model="test",
            )

        def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
            yield LLMStreamDelta(text=self.complete(request).text)

    review = review_url_artifacts_with_llm(
        UrlLlmReviewInput(
            task="Map visual state.",
            markdown="VF 9 selected color: Deep Ocean.",
            evidence=[
                UrlLlmReviewEvidence(
                    evidence_id="dom:color",
                    evidence_source="dom_after_interaction",
                    text="Selected color Deep Ocean",
                )
            ],
        ),
        client=FakeClient(),
    )

    assert review is not None
    assert review.field_mapping["variant_options.color"] == "Deep Ocean"
    assert review.needs_human_review is True
    assert review.unvalidated_facts == ["product_price: 2.000.000.000 VND"]
