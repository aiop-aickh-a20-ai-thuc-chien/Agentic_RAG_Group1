"""Tiny Vietnamese EV corpus for the demo.

Designed so the downstream stages have visible work to do:
- entity surface VARIANTS that must resolve     ("VF 8" / "VinFast VF8" / "vf8")
- predicate VARIANTS that must canonicalize     ("sản xuất bởi" / "made by" / "sản xuất")
- a DIRECTION that must flip                     ("VinFast sản xuất VF 8" -> VF8 made_by VinFast)
- JUNK that the gates must drop                  (pronoun subject, accessory-only edge, fake evidence)

`SIMULATED_EXTRACTIONS` stands in for what the LLM would emit per chunk. In
production this dict does not exist — `kg.extract` calls the real LLM instead.
"""

from __future__ import annotations

from kg.schema import Chunk, Document, OpenTriple

DOCUMENTS = [
    Document(
        doc_id="d_catalogue",
        title="Catalogue VinFast",
        chunks=[
            Chunk(
                doc_id="d_catalogue",
                chunk_id="d_catalogue::c1",
                heading="Dòng VF 8",
                section_path=("Catalogue", "VF 8"),
                text=(
                    "VinFast sản xuất VF 8. VF 8 được trang bị pin LFP. "
                    "VF 8 áp dụng chính sách thuê pin."
                ),
            ),
            Chunk(
                doc_id="d_catalogue",
                chunk_id="d_catalogue::c2",
                heading="Giá & phụ kiện",
                section_path=("Catalogue", "VF 8", "Giá"),
                text=("VinFast VF8 có giá 1.2 tỷ. Xe này tương thích với bộ sạc V-Green."),
            ),
        ],
    ),
    Document(
        doc_id="d_vf5",
        title="Thông số VF 5",
        chunks=[
            Chunk(
                doc_id="d_vf5",
                chunk_id="d_vf5::c3",
                heading="Tổng quan",
                section_path=("VF 5", "Tổng quan"),
                text="VF 5 được sản xuất bởi VinFast. VF 5 trang bị pin lithium LFP.",
            ),
            Chunk(
                doc_id="d_vf5",
                chunk_id="d_vf5::c4",
                heading="Chính sách",
                section_path=("VF 5", "Chính sách"),
                text="vf5 made by VinFast. VF 5 áp dụng chính sách bảo hành 10 năm.",
            ),
        ],
    ),
    Document(
        doc_id="d_misc",
        title="Phụ kiện & dòng VF 3",
        chunks=[
            Chunk(
                doc_id="d_misc",
                chunk_id="d_misc::c5",
                heading="Phụ kiện",
                section_path=("Phụ kiện",),
                text=("Thảm cốp 3D VF 8 làm bằng cao su. Bộ sạc V-Green tương thích với VF 8."),
            ),
            Chunk(
                doc_id="d_misc",
                chunk_id="d_misc::c6",
                heading="VF 3",
                section_path=("VF 3",),
                text="VF 3 được trang bị pin LFP.",
            ),
        ],
    ),
]


def _t(s, st, p, o, ot, ev) -> OpenTriple:
    return OpenTriple(
        subject=s, subject_type=st, predicate=p, object=o, object_type=ot, evidence=ev
    )


# What the LLM "would" return per chunk (open: free-form predicate + type).
SIMULATED_EXTRACTIONS: dict[str, list[OpenTriple]] = {
    "d_catalogue::c1": [
        # direction REVERSED on purpose (org -> product); must flip to product -> org
        _t("VinFast", "org", "sản xuất", "VF 8", "product", "VinFast sản xuất VF 8"),
        _t("VF 8", "product", "được trang bị", "pin LFP", "feature", "VF 8 được trang bị pin LFP"),
        _t(
            "VF 8",
            "product",
            "áp dụng chính sách",
            "chính sách thuê pin",
            "policy",
            "VF 8 áp dụng chính sách thuê pin",
        ),
    ],
    "d_catalogue::c2": [
        _t("VinFast VF8", "product", "có giá", "1.2 tỷ", "value", "VinFast VF8 có giá 1.2 tỷ"),
        # pronoun subject -> gate drops it
        _t(
            "Xe này",
            "generic",
            "tương thích với",
            "bộ sạc V-Green",
            "feature",
            "Xe này tương thích với bộ sạc V-Green",
        ),
    ],
    "d_vf5::c3": [
        _t(
            "VF 5",
            "product",
            "được sản xuất bởi",
            "VinFast",
            "org",
            "VF 5 được sản xuất bởi VinFast",
        ),
        _t(
            "VF 5",
            "product",
            "trang bị",
            "pin lithium LFP",
            "feature",
            "VF 5 trang bị pin lithium LFP",
        ),
    ],
    "d_vf5::c4": [
        _t("vf5", "product", "made by", "VinFast", "org", "vf5 made by VinFast"),
        _t(
            "VF 5",
            "product",
            "áp dụng",
            "chính sách bảo hành 10 năm",
            "policy",
            "VF 5 áp dụng chính sách bảo hành 10 năm",
        ),
    ],
    "d_misc::c5": [
        # both endpoints accessory/generic -> gate drops it
        _t(
            "Thảm cốp 3D VF 8",
            "accessory",
            "làm bằng",
            "cao su",
            "accessory",
            "Thảm cốp 3D VF 8 làm bằng cao su",
        ),
        _t(
            "bộ sạc V-Green",
            "feature",
            "tương thích với",
            "VF 8",
            "product",
            "Bộ sạc V-Green tương thích với VF 8",
        ),
    ],
    "d_misc::c6": [
        _t("VF 3", "product", "được trang bị", "pin LFP", "feature", "VF 3 được trang bị pin LFP"),
        # hallucinated evidence (not a substring of the chunk) -> gate drops it
        _t("VF 3", "product", "sản xuất bởi", "Toyota", "org", "VF 3 do Toyota sản xuất"),
    ],
}
