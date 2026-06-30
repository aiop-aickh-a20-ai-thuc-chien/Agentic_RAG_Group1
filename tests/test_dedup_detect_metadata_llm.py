from agentic_rag.ingestion.dedup_detect import (
    DedupDocument,
    build_metadata_blocks,
    review_blocked_candidates,
)


def _state(document_id: str, state_id: str, seat_layout: str) -> DedupDocument:
    return DedupDocument(
        document_id=document_id,
        text="VF 9 shared panel text and visible configuration facts.",
        metadata={
            "product_model": "VF9",
            "scope_type": "edition",
            "attribute_group": "configuration",
            "language": "vi",
            "scope_path": f"model:VF9/edition:{state_id}",
            "parent_state_id": "vf9",
            "state_id": state_id,
            "seat_layout": seat_layout,
            "after_snapshot_ref": f"snapshot-{document_id}",
        },
    )


def test_metadata_blocking_caps_broad_blocks() -> None:
    documents = [DedupDocument(document_id=str(index), text="text") for index in range(3)]

    assert build_metadata_blocks(documents, max_block_size=2) == {}


def test_state_review_rejects_siblings_and_detects_replay_with_provenance() -> None:
    eco = _state("eco", "eco", "7 seats")
    plus = _state("plus", "plus", "captain chairs")
    replay = eco.model_copy(
        update={
            "document_id": "eco-replay",
            "metadata": {**eco.metadata, "after_snapshot_ref": "snapshot-eco-replay"},
        }
    )

    reviews = review_blocked_candidates([eco, plus, replay])
    by_pair = {
        (review.document_id, review.duplicate_document_id): review for review in reviews
    }

    assert by_pair[("eco", "plus")].classification == "not_duplicate"
    assert by_pair[("eco", "plus")].pair_category == "sibling_state"
    assert by_pair[("eco", "eco-replay")].classification == "duplicate"
    assert by_pair[("eco", "eco-replay")].pair_category == "same_state_replay"
    assert by_pair[("eco", "eco-replay")].evidence_refs == (
        "snapshot-eco",
        "snapshot-eco-replay",
    )
