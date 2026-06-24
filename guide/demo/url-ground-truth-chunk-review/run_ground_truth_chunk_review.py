"""Build URL-ingestion review artifacts from golden ground-truth JSON."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import (
    build_chunk_id,
    chunk_markdown_by_sections,
    normalize_for_content_hash,
    normalize_for_dedupe_hash,
    short_hash,
)


DEFAULT_GOLDEN_DATA_DIR = REPO_ROOT / "src" / "agentic_rag" / "ingestion" / "url" / "golden_data"
DEFAULT_MANIFEST = DEFAULT_GOLDEN_DATA_DIR / "ground_truth_manifest.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
MODEL_RE = re.compile(
    r"\b(?:VF\s?\d(?:\s+Plus)?|VF\s?e34|VF\s?8\s+The\s+All\s+New|MPV\s?7|Evo200|Feliz\s+S|Klara\s+S|Vento\s+S|Theon\s+S)\b",
    flags=re.IGNORECASE,
)
PRICE_RE = re.compile(r"\d[\d.]*\s*VNĐ", flags=re.IGNORECASE)


def main() -> None:
    args = _parse_args()
    manifest_path = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    manifest = _load_json(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "manifest": _relative_or_absolute(manifest_path),
        "datasets": [],
    }

    for dataset in manifest.get("datasets", []):
        dataset_summary = _process_dataset(
            dataset=dataset,
            output_root=output_dir,
            max_chars=args.max_chars,
        )
        summary["datasets"].append(dataset_summary)

    _write_json(output_dir / "summary.json", summary)
    (output_dir / "summary.md").write_text(_render_summary_markdown(summary), encoding="utf-8")
    print(f"Wrote {len(summary['datasets'])} dataset review(s) to {output_dir}")
    for dataset in summary["datasets"]:
        print(
            "- {dataset_id}: {chunk_count} URL chunks, {entity_chunk_count} entity chunks, "
            "{missing_count} missing important value(s)".format(**dataset)
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert URL golden JSON to structured Markdown and review URL chunks."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-chars", type=int, default=500)
    return parser.parse_args()


def _process_dataset(
    *,
    dataset: dict[str, Any],
    output_root: Path,
    max_chars: int,
) -> dict[str, Any]:
    dataset_id = str(dataset["dataset_id"])
    ground_truth_file = _resolve_repo_path(dataset["ground_truth_file"])
    data = _load_json(ground_truth_file)
    markdown = _build_markdown(dataset, data)
    chunks = _build_review_chunks(
        markdown=markdown,
        dataset=dataset,
        source=str(ground_truth_file),
        max_chars=max_chars,
    )
    entity_chunks = _build_entity_review_chunks(
        data=data,
        dataset=dataset,
        source=str(ground_truth_file),
    )
    missing_values = _find_missing_values(data, markdown)
    diagnostics = [_chunk_diagnostics(chunk) for chunk in chunks]
    entity_diagnostics = [_chunk_diagnostics(chunk) for chunk in entity_chunks]

    dataset_dir = output_root / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "ground_truth.md").write_text(markdown, encoding="utf-8")
    _write_jsonl(dataset_dir / "chunks.jsonl", [chunk.model_dump(mode="json") for chunk in chunks])
    _write_jsonl(
        dataset_dir / "entity_chunks.jsonl",
        [chunk.model_dump(mode="json") for chunk in entity_chunks],
    )
    _write_json(
        dataset_dir / "manifest.json",
        {
            "dataset": dataset,
            "ground_truth_file": _relative_or_absolute(ground_truth_file),
            "markdown_file": "ground_truth.md",
            "chunks_file": "chunks.jsonl",
            "entity_chunks_file": "entity_chunks.jsonl",
            "chunk_count": len(chunks),
            "entity_chunk_count": len(entity_chunks),
            "missing_important_values": missing_values,
            "chunk_diagnostics": diagnostics,
            "entity_chunk_diagnostics": entity_diagnostics,
        },
    )
    (dataset_dir / "chunks_readable.md").write_text(
        _render_chunks_markdown(chunks, diagnostics, missing_values),
        encoding="utf-8",
    )
    (dataset_dir / "chunks_readable.html").write_text(
        _render_chunks_html(chunks, diagnostics, missing_values),
        encoding="utf-8",
    )
    (dataset_dir / "entity_chunks_readable.md").write_text(
        _render_chunks_markdown(entity_chunks, entity_diagnostics, missing_values),
        encoding="utf-8",
    )

    return {
        "dataset_id": dataset_id,
        "target_url": dataset.get("target_url"),
        "ground_truth_file": _relative_or_absolute(ground_truth_file),
        "output_dir": _relative_or_absolute(dataset_dir),
        "chunk_count": len(chunks),
        "entity_chunk_count": len(entity_chunks),
        "missing_count": len(missing_values),
        "chunks_with_model": sum(1 for item in diagnostics if item["model_mentions"]),
        "chunks_with_price": sum(1 for item in diagnostics if item["contains_price"]),
        "chunks_with_choices": sum(1 for item in diagnostics if item["contains_choices"]),
        "entity_chunks_with_model": sum(1 for item in entity_diagnostics if item["model_mentions"]),
        "entity_chunks_with_price": sum(1 for item in entity_diagnostics if item["contains_price"]),
        "entity_chunks_with_choices": sum(
            1 for item in entity_diagnostics if item["contains_choices"]
        ),
    }


def _build_markdown(dataset: dict[str, Any], data: dict[str, Any]) -> str:
    if "dat_coc_vinfast" in data:
        return _build_deposit_markdown(dataset, data["dat_coc_vinfast"])
    if "vinfast_homepage" in data:
        return _build_homepage_markdown(dataset, data["vinfast_homepage"])
    return _build_generic_markdown(dataset, data)


def _build_deposit_markdown(dataset: dict[str, Any], root: dict[str, Any]) -> str:
    current = root.get("thong_tin_xe_hien_tai", {})
    lines = _dataset_header(dataset, "Ground truth đặt cọc VinFast")
    lines.extend(
        [
            "## Thông tin xe hiện tại",
            "",
            f"- Mẫu xe đang hiển thị: {_scalar(current.get('model'))}",
            f"- Trạng thái dataset: {_scalar(dataset.get('status'))}",
            "",
            "## Phiên bản VF 9",
            "",
        ]
    )
    for version in current.get("chon_phien_ban", []):
        original = version.get("gia_nguyen_goc") or {}
        lines.extend(
            [
                f"### {_scalar(version.get('ten_phien_ban'))}",
                "",
                f"- Giá thực tế hiện tại: {_scalar(version.get('gia_thuc_te_hien_tai'))}",
                f"- Giá nguyên gốc: {_scalar(original.get('muc_gia'))}",
                f"- Trạng thái hiển thị giá gốc: {_scalar(original.get('trang_thai_hien_thi'))}",
                f"- HTML class của giá gốc: {_scalar(original.get('html_class'))}",
                f"- Tùy chọn pin: {_scalar(version.get('tuy_chon_pin'))}",
                "",
            ]
        )

    exterior = current.get("ngoai_that_VF9", {})
    premium_colors = exterior.get("mau_nang_cao") or {}
    lines.extend(
        [
            "## Ngoại thất VF9",
            "",
            "### Màu cơ bản theo xe",
            "",
            *_bullet_list(exterior.get("mau_co_ban_theo_xe", [])),
            "",
            "### Màu nâng cao",
            "",
            f"- Phụ phí: {_scalar(premium_colors.get('phu_phi'))}",
            *_bullet_list(premium_colors.get("danh_sach_mau", [])),
            "",
        ]
    )

    interior = current.get("noi_that_VF9", {})
    lines.extend(
        [
            "## Nội thất VF9",
            "",
            *_bullet_list(interior.get("danh_sach_mau", [])),
            f"- Ghi chú: {_scalar(interior.get('ghi_chu'))}",
            "",
        ]
    )

    payment = current.get("thong_tin_khach_hang_va_thanh_toan", {})
    member = payment.get("thanh_vien") or {}
    promotion = payment.get("uu_dai") or {}
    province = payment.get("tinh_thanh") or {}
    cost = payment.get("bang_tinh_chi_phi") or {}
    rolling_cost = cost.get("chi_phi_lan_banh_du_kien") or {}
    lines.extend(
        [
            "## Khách hàng và thanh toán",
            "",
            "### Hạng thành viên VinClub",
            "",
            *_bullet_list(member.get("hang_thanh_vien", [])),
            f"- Quyền lợi: {_scalar(member.get('quyen_loi'))}",
            "",
            "### Ưu đãi",
            "",
            f"- Mã khuyến mãi: {_scalar(promotion.get('ma_khuyen_mai'))}",
            f"- Chương trình áp dụng: {_scalar(promotion.get('chuong_trinh_ap_dung'))}",
            "",
            "### Tỉnh thành",
            "",
            *_bullet_list(province.get("lua_chon_tinh_thanh", [])),
            "",
            "### Bảng tính chi phí lăn bánh",
            "",
            _table(
                ["Hạng mục", "Giá trị"],
                [
                    ("Giá xe", cost.get("gia_ca")),
                    ("Phí giảm về ưu đãi", cost.get("phi_giam_ve_uu_dai")),
                    ("Lệ phí trước bạ", rolling_cost.get("le_phi_truoc_ba")),
                    ("Phí đăng ký biển số", rolling_cost.get("phi_dang_ky_bien_so")),
                    ("Phí đăng kiểm", rolling_cost.get("phi_dang_kiem")),
                    ("Phí bảo trì", rolling_cost.get("phi_bao_tri")),
                    ("Bảo hiểm TNDS bắt buộc", rolling_cost.get("bao_hiem_tnds_bat_buoc")),
                    ("Tổng chi phí lăn bánh", rolling_cost.get("tong_chi_phi_lan_banh")),
                ],
            ),
            "",
        ]
    )

    other_models = root.get("cac_xe_VF_khac", {})
    lines.extend(["## Các xe VF khác", "", f"- Mô tả: {_scalar(other_models.get('mo_ta'))}", ""])
    for model in other_models.get("danh_sach_model", []):
        lines.extend(
            [
                f"### {_scalar(model.get('ten_xe'))}",
                "",
                f"- modelId: {_scalar(model.get('modelId'))}",
                "- Vai trò: mẫu xe trong panel điều hướng cập nhật tham số URL.",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _build_homepage_markdown(dataset: dict[str, Any], root: dict[str, Any]) -> str:
    lines = _dataset_header(dataset, "Ground truth trang chủ VinFast")
    navigation = root.get("navigation_menu", {})
    lines.extend(["## Menu điều hướng", ""])
    for key, value in navigation.items():
        lines.extend([f"### {_human_key(key)}", ""])
        if isinstance(value, list):
            lines.extend(_bullet_list(value))
        else:
            lines.append(f"- {_scalar(value)}")
        lines.append("")

    lines.extend(["## Hero banner", ""])
    for index, banner in enumerate(root.get("hero_banner", []), start=1):
        lines.extend(
            [
                f"### Banner {index}: {_scalar(banner.get('tieu_de'))}",
                "",
                f"- Mô tả: {_scalar(banner.get('mo_ta'))}",
                f"- Call to action: {_scalar(banner.get('call_to_action'))}",
                "",
            ]
        )

    featured = root.get("san_pham_noi_bat", {})
    lines.extend(["## Sản phẩm nổi bật", ""])
    for category, products in featured.items():
        lines.extend([f"### {_human_key(category)}", ""])
        for product in products:
            original = product.get("gia_nguyen_goc") or {}
            lines.extend(
                [
                    f"#### {_scalar(product.get('ten_xe'))}",
                    "",
                    f"- Giá thực tế hiện tại: {_scalar(product.get('gia_thuc_te_hien_tai'))}",
                    f"- Giá nguyên gốc: {_scalar(original.get('muc_gia'))}",
                    "- Trạng thái hiển thị giá gốc: "
                    f"{_scalar(original.get('trang_thai_hien_thi'))}",
                    f"- HTML class của giá gốc: {_scalar(original.get('html_class'))}",
                ]
            )
            if product.get("phan_khuc"):
                lines.append(f"- Phân khúc: {_scalar(product.get('phan_khuc'))}")
            lines.append("")

    ecosystem = root.get("he_sinh_thai_toan_dien", {})
    lines.extend(
        [
            "## Hệ sinh thái toàn diện",
            "",
            f"- Tiêu đề: {_scalar(ecosystem.get('tieu_de'))}",
            *_bullet_list(ecosystem.get("cac_diem_chinh", [])),
            "",
        ]
    )

    footer = root.get("footer", {})
    contact = footer.get("lien_he") or {}
    lines.extend(
        [
            "## Footer",
            "",
            f"- Thông tin công ty: {_scalar(footer.get('thong_tin_cong_ty'))}",
            f"- Hotline: {_scalar(contact.get('hotline'))}",
            f"- Email: {_scalar(contact.get('email'))}",
            "### Mạng xã hội",
            "",
            *_bullet_list(footer.get("mang_xa_hoi", [])),
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_generic_markdown(dataset: dict[str, Any], data: dict[str, Any]) -> str:
    lines = _dataset_header(dataset, "Ground truth URL ingestion")
    lines.extend(_generic_node(data, level=2))
    return "\n".join(lines).strip() + "\n"


def _generic_node(value: Any, *, level: int, title: str | None = None) -> list[str]:
    lines: list[str] = []
    if title:
        lines.extend([f"{'#' * level} {_human_key(title)}", ""])
    if isinstance(value, dict):
        scalar_rows = [
            (key, item) for key, item in value.items() if not isinstance(item, (dict, list))
        ]
        if scalar_rows:
            lines.extend([_table(["Trường", "Giá trị"], scalar_rows), ""])
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.extend(_generic_node(item, level=min(level + 1, 6), title=key))
    elif isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            lines.extend(_bullet_list(value))
            lines.append("")
        else:
            for index, item in enumerate(value, start=1):
                label = (
                    item.get("ten_xe") or item.get("ten_phien_ban")
                    if isinstance(item, dict)
                    else None
                )
                lines.extend(
                    _generic_node(item, level=min(level + 1, 6), title=label or f"Mục {index}")
                )
    else:
        lines.extend([f"- {_scalar(value)}", ""])
    return lines


def _build_review_chunks(
    *,
    markdown: str,
    dataset: dict[str, Any],
    source: str,
    max_chars: int,
) -> list[Chunk]:
    title = str(dataset["dataset_id"])
    page_hash = short_hash(normalize_for_content_hash(markdown))
    chunks: list[Chunk] = []
    markdown_chunks = chunk_markdown_by_sections(
        markdown,
        root_title=title,
        max_chars=max_chars,
        overlap_paragraphs=0,
    )
    for index, markdown_chunk in enumerate(markdown_chunks, start=1):
        section = markdown_chunk.section or "main"
        chunk_id = build_chunk_id("url-ground-truth", source, section, index)
        normalized_text = normalize_for_content_hash(markdown_chunk.text)
        dedupe_text = normalize_for_dedupe_hash(markdown_chunk.text)
        diagnostics = _text_diagnostics(markdown_chunk.text)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=markdown_chunk.text,
                metadata={
                    "chunk_id": chunk_id,
                    "source": source,
                    "source_type": "url_ground_truth_json",
                    "title": title,
                    "dataset_id": dataset["dataset_id"],
                    "target_url": dataset.get("target_url"),
                    "section": section,
                    "section_level": markdown_chunk.section_level,
                    "section_path": list(markdown_chunk.section_path),
                    "chunk_index": index,
                    "page_hash": page_hash,
                    "content_hash": short_hash(normalized_text),
                    "dedupe_text": dedupe_text,
                    "dedupe_hash": short_hash(dedupe_text),
                    "normalized_text": normalized_text,
                    "chunk_token_count": markdown_chunk.chunk_token_count,
                    "model_mentions": diagnostics["model_mentions"],
                    "contains_price": diagnostics["contains_price"],
                    "contains_model_id": diagnostics["contains_model_id"],
                    "contains_choices": diagnostics["contains_choices"],
                    "review_purpose": "ground_truth_json_to_markdown_chunk_check",
                    **markdown_chunk.metadata,
                },
            )
        )
    return chunks


def _build_entity_review_chunks(
    *,
    data: dict[str, Any],
    dataset: dict[str, Any],
    source: str,
) -> list[Chunk]:
    if "dat_coc_vinfast" in data:
        nodes = _deposit_entity_nodes(dataset, data["dat_coc_vinfast"])
    elif "vinfast_homepage" in data:
        nodes = _homepage_entity_nodes(dataset, data["vinfast_homepage"])
    else:
        nodes = [("generic", "Ground truth JSON", _build_generic_markdown(dataset, data), {})]
    return _nodes_to_chunks(nodes=nodes, dataset=dataset, source=source)


def _deposit_entity_nodes(
    dataset: dict[str, Any],
    root: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    current = root.get("thong_tin_xe_hien_tai", {})
    nodes: list[tuple[str, str, str, dict[str, Any]]] = [
        (
            "dataset_state",
            "Dataset state",
            "\n".join(_dataset_header(dataset, "Ground truth đặt cọc VinFast")).strip(),
            {},
        ),
        (
            "current_model",
            "Thông tin xe hiện tại",
            "\n".join(
                [
                    "## Thông tin xe hiện tại",
                    "",
                    f"- Mẫu xe đang hiển thị: {_scalar(current.get('model'))}",
                    f"- Trạng thái dataset: {_scalar(dataset.get('status'))}",
                    f"- Target URL: {_scalar(dataset.get('target_url'))}",
                ]
            ),
            {"model": current.get("model")},
        ),
    ]
    for version in current.get("chon_phien_ban", []):
        original = version.get("gia_nguyen_goc") or {}
        title = _scalar(version.get("ten_phien_ban"))
        text = "\n".join(
            [
                f"## {title}",
                "",
                f"- Mẫu xe: {_scalar(current.get('model'))}",
                f"- Phiên bản: {title}",
                f"- Giá thực tế hiện tại: {_scalar(version.get('gia_thuc_te_hien_tai'))}",
                f"- Giá nguyên gốc: {_scalar(original.get('muc_gia'))}",
                f"- Trạng thái hiển thị giá gốc: {_scalar(original.get('trang_thai_hien_thi'))}",
                f"- HTML class của giá gốc: {_scalar(original.get('html_class'))}",
                f"- Tùy chọn pin: {_scalar(version.get('tuy_chon_pin'))}",
            ]
        )
        nodes.append(
            (
                "model_version",
                title,
                text,
                {"model": current.get("model"), "version": title},
            )
        )

    exterior = current.get("ngoai_that_VF9", {})
    premium_colors = exterior.get("mau_nang_cao") or {}
    nodes.append(
        (
            "choices",
            "Ngoại thất VF9",
            "\n".join(
                [
                    "## Ngoại thất VF9",
                    "",
                    "### Màu cơ bản theo xe",
                    *_bullet_list(exterior.get("mau_co_ban_theo_xe", [])),
                    "",
                    "### Màu nâng cao",
                    f"- Phụ phí: {_scalar(premium_colors.get('phu_phi'))}",
                    *_bullet_list(premium_colors.get("danh_sach_mau", [])),
                ]
            ),
            {"model": current.get("model"), "choice_type": "exterior"},
        )
    )
    interior = current.get("noi_that_VF9", {})
    nodes.append(
        (
            "choices",
            "Nội thất VF9",
            "\n".join(
                [
                    "## Nội thất VF9",
                    "",
                    *_bullet_list(interior.get("danh_sach_mau", [])),
                    f"- Ghi chú: {_scalar(interior.get('ghi_chu'))}",
                ]
            ),
            {"model": current.get("model"), "choice_type": "interior"},
        )
    )

    payment = current.get("thong_tin_khach_hang_va_thanh_toan", {})
    member = payment.get("thanh_vien") or {}
    promotion = payment.get("uu_dai") or {}
    province = payment.get("tinh_thanh") or {}
    cost = payment.get("bang_tinh_chi_phi") or {}
    rolling_cost = cost.get("chi_phi_lan_banh_du_kien") or {}
    nodes.extend(
        [
            (
                "customer_choices",
                "Hạng thành viên và ưu đãi",
                "\n".join(
                    [
                        "## Hạng thành viên và ưu đãi",
                        "",
                        "### Hạng thành viên VinClub",
                        *_bullet_list(member.get("hang_thanh_vien", [])),
                        f"- Quyền lợi: {_scalar(member.get('quyen_loi'))}",
                        "",
                        "### Ưu đãi",
                        f"- Mã khuyến mãi: {_scalar(promotion.get('ma_khuyen_mai'))}",
                        f"- Chương trình áp dụng: {_scalar(promotion.get('chuong_trinh_ap_dung'))}",
                    ]
                ),
                {},
            ),
            (
                "customer_choices",
                "Tỉnh thành",
                "\n".join(
                    ["## Tỉnh thành", "", *_bullet_list(province.get("lua_chon_tinh_thanh", []))]
                ),
                {},
            ),
            (
                "pricing",
                "Bảng tính chi phí lăn bánh",
                "\n".join(
                    [
                        "## Bảng tính chi phí lăn bánh",
                        "",
                        _table(
                            ["Hạng mục", "Giá trị"],
                            [
                                ("Giá xe", cost.get("gia_ca")),
                                ("Phí giảm về ưu đãi", cost.get("phi_giam_ve_uu_dai")),
                                ("Lệ phí trước bạ", rolling_cost.get("le_phi_truoc_ba")),
                                ("Phí đăng ký biển số", rolling_cost.get("phi_dang_ky_bien_so")),
                                ("Phí đăng kiểm", rolling_cost.get("phi_dang_kiem")),
                                ("Phí bảo trì", rolling_cost.get("phi_bao_tri")),
                                (
                                    "Bảo hiểm TNDS bắt buộc",
                                    rolling_cost.get("bao_hiem_tnds_bat_buoc"),
                                ),
                                (
                                    "Tổng chi phí lăn bánh",
                                    rolling_cost.get("tong_chi_phi_lan_banh"),
                                ),
                            ],
                        ),
                    ]
                ),
                {"model": current.get("model")},
            ),
        ]
    )

    other_models = root.get("cac_xe_VF_khac", {})
    for model in other_models.get("danh_sach_model", []):
        title = _scalar(model.get("ten_xe"))
        nodes.append(
            (
                "model_navigation",
                title,
                "\n".join(
                    [
                        f"## {title}",
                        "",
                        f"- Tên xe: {title}",
                        f"- modelId: {_scalar(model.get('modelId'))}",
                        f"- Mô tả panel: {_scalar(other_models.get('mo_ta'))}",
                    ]
                ),
                {"model": title, "model_id": model.get("modelId")},
            )
        )
    return nodes


def _homepage_entity_nodes(
    dataset: dict[str, Any],
    root: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    nodes: list[tuple[str, str, str, dict[str, Any]]] = [
        (
            "dataset_state",
            "Dataset state",
            "\n".join(_dataset_header(dataset, "Ground truth trang chủ VinFast")).strip(),
            {},
        )
    ]
    navigation = root.get("navigation_menu", {})
    for key, value in navigation.items():
        title = _human_key(key)
        if isinstance(value, list):
            body = "\n".join([f"## {title}", "", *_bullet_list(value)])
        else:
            body = "\n".join([f"## {title}", "", f"- {_scalar(value)}"])
        nodes.append(("navigation", title, body, {"navigation_group": key}))

    for index, banner in enumerate(root.get("hero_banner", []), start=1):
        title = f"Banner {index}: {_scalar(banner.get('tieu_de'))}"
        nodes.append(
            (
                "hero",
                title,
                "\n".join(
                    [
                        f"## {title}",
                        "",
                        f"- Mô tả: {_scalar(banner.get('mo_ta'))}",
                        f"- Call to action: {_scalar(banner.get('call_to_action'))}",
                    ]
                ),
                {},
            )
        )

    for category, products in root.get("san_pham_noi_bat", {}).items():
        for product in products:
            original = product.get("gia_nguyen_goc") or {}
            title = _scalar(product.get("ten_xe"))
            lines = [
                f"## {title}",
                "",
                f"- Nhóm sản phẩm: {_human_key(category)}",
                f"- Giá thực tế hiện tại: {_scalar(product.get('gia_thuc_te_hien_tai'))}",
                f"- Giá nguyên gốc: {_scalar(original.get('muc_gia'))}",
                f"- Trạng thái hiển thị giá gốc: {_scalar(original.get('trang_thai_hien_thi'))}",
                f"- HTML class của giá gốc: {_scalar(original.get('html_class'))}",
            ]
            if product.get("phan_khuc"):
                lines.append(f"- Phân khúc: {_scalar(product.get('phan_khuc'))}")
            nodes.append(
                (
                    "featured_product",
                    title,
                    "\n".join(lines),
                    {"model": title, "product_group": category},
                )
            )

    ecosystem = root.get("he_sinh_thai_toan_dien", {})
    nodes.append(
        (
            "ecosystem",
            "Hệ sinh thái toàn diện",
            "\n".join(
                [
                    "## Hệ sinh thái toàn diện",
                    "",
                    f"- Tiêu đề: {_scalar(ecosystem.get('tieu_de'))}",
                    *_bullet_list(ecosystem.get("cac_diem_chinh", [])),
                ]
            ),
            {},
        )
    )
    footer = root.get("footer", {})
    contact = footer.get("lien_he") or {}
    nodes.append(
        (
            "footer",
            "Footer",
            "\n".join(
                [
                    "## Footer",
                    "",
                    f"- Thông tin công ty: {_scalar(footer.get('thong_tin_cong_ty'))}",
                    f"- Hotline: {_scalar(contact.get('hotline'))}",
                    f"- Email: {_scalar(contact.get('email'))}",
                    "### Mạng xã hội",
                    *_bullet_list(footer.get("mang_xa_hoi", [])),
                ]
            ),
            {},
        )
    )
    return nodes


def _nodes_to_chunks(
    *,
    nodes: list[tuple[str, str, str, dict[str, Any]]],
    dataset: dict[str, Any],
    source: str,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    page_hash = short_hash(normalize_for_content_hash("\n\n".join(node[2] for node in nodes)))
    for index, (role, title, text, extra_metadata) in enumerate(nodes, start=1):
        normalized_text = normalize_for_content_hash(text)
        dedupe_text = normalize_for_dedupe_hash(text)
        diagnostics = _text_diagnostics(text)
        chunk_id = build_chunk_id("url-ground-truth-entity", source, f"{role}-{title}", index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    "chunk_id": chunk_id,
                    "source": source,
                    "source_type": "url_ground_truth_entity_review",
                    "title": dataset["dataset_id"],
                    "dataset_id": dataset["dataset_id"],
                    "target_url": dataset.get("target_url"),
                    "section": title,
                    "section_level": 2,
                    "section_path": [str(dataset["dataset_id"]), title],
                    "chunk_index": index,
                    "review_role": role,
                    "page_hash": page_hash,
                    "content_hash": short_hash(normalized_text),
                    "dedupe_text": dedupe_text,
                    "dedupe_hash": short_hash(dedupe_text),
                    "normalized_text": normalized_text,
                    "chunk_token_count": len(normalized_text.split()),
                    "model_mentions": diagnostics["model_mentions"],
                    "contains_price": diagnostics["contains_price"],
                    "contains_model_id": diagnostics["contains_model_id"],
                    "contains_choices": diagnostics["contains_choices"],
                    "review_purpose": "entity_aligned_ground_truth_chunk_check",
                    **extra_metadata,
                },
            )
        )
    return chunks


def _chunk_diagnostics(chunk: Chunk) -> dict[str, Any]:
    diagnostics = _text_diagnostics(chunk.text)
    return {
        "chunk_id": chunk.chunk_id,
        "section_path": chunk.metadata.get("section_path", []),
        "review_role": chunk.metadata.get("review_role"),
        "chars": len(chunk.text),
        **diagnostics,
    }


def _text_diagnostics(text: str) -> dict[str, Any]:
    return {
        "model_mentions": sorted({match.group(0) for match in MODEL_RE.finditer(text)}),
        "contains_price": bool(PRICE_RE.search(text)),
        "contains_model_id": "modelId" in text or "Products-Car-" in text,
        "contains_choices": any(
            marker in text.casefold()
            for marker in (
                "phiên bản",
                "tùy chọn",
                "màu",
                "vinclub",
                "ưu đãi",
                "giá",
                "chi phí",
                "pin",
            )
        ),
    }


def _find_missing_values(data: Any, markdown: str) -> list[str]:
    normalized_markdown = _normalize_for_match(markdown)
    values = sorted(
        {_scalar(value) for value in _iter_scalars(data) if _is_important_value(value)},
        key=str.casefold,
    )
    return [value for value in values if _normalize_for_match(value) not in normalized_markdown]


def _iter_scalars(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_scalars(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_scalars(item)
        return
    yield value


def _is_important_value(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    text = _scalar(value).strip()
    if len(text) < 2 or len(text) > 180:
        return False
    return bool(re.search(r"[A-Za-zÀ-ỹ0-9]", text))


def _dataset_header(dataset: dict[str, Any], title: str) -> list[str]:
    lines = [
        f"# {title}: {dataset['dataset_id']}",
        "",
        f"- Dataset ID: {dataset['dataset_id']}",
        f"- Target URL: {dataset.get('target_url')}",
        f"- Status: {dataset.get('status')}",
        "",
    ]
    notes = dataset.get("notes") or []
    if notes:
        lines.extend(["## Ghi chú ground truth", ""])
        lines.extend(_bullet_list(notes))
        lines.append("")
    return lines


def _bullet_list(values: Iterable[Any]) -> list[str]:
    return [f"- {_scalar(value)}" for value in values]


def _table(headers: list[str], rows: Iterable[tuple[Any, ...]]) -> str:
    header = "| " + " | ".join(_escape_table(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_table(item) for item in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _escape_table(value: Any) -> str:
    return _scalar(value).replace("|", "\\|").replace("\n", "<br>")


def _human_key(key: str) -> str:
    return str(key).replace("_", " ").strip().capitalize()


def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# URL ground truth chunk review",
        "",
        f"- Created at: {summary['created_at']}",
        f"- Manifest: {summary['manifest']}",
        "",
        "| Dataset | Chunks | Chunks with model | Chunks with price | "
        "Chunks with choices | Missing values | Output |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for dataset in summary["datasets"]:
        lines.append(
            "| {dataset_id} | {chunk_count} URL / {entity_chunk_count} entity | "
            "{chunks_with_model} URL / {entity_chunks_with_model} entity | "
            "{chunks_with_price} URL / {entity_chunks_with_price} entity | "
            "{chunks_with_choices} URL / {entity_chunks_with_choices} entity | "
            "{missing_count} | {output_dir} |".format(**dataset)
        )
    return "\n".join(lines) + "\n"


def _render_chunks_markdown(
    chunks: list[Chunk],
    diagnostics: list[dict[str, Any]],
    missing_values: list[str],
) -> str:
    lines = [
        "# Chunk review",
        "",
        "| # | Role | Section path | Models | Price | modelId | Choices | Chars | "
        "Chunk ID |",
        "| ---: | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for index, item in enumerate(diagnostics, start=1):
        lines.append(
            "| {index} | {role} | {section} | {models} | {price} | {model_id} | "
            "{choices} | {chars} | `{chunk_id}` |".format(
                index=index,
                role=item.get("review_role") or "url_chunk",
                section=" > ".join(item["section_path"]),
                models=", ".join(item["model_mentions"]) or "-",
                price="yes" if item["contains_price"] else "no",
                model_id="yes" if item["contains_model_id"] else "no",
                choices="yes" if item["contains_choices"] else "no",
                chars=item["chars"],
                chunk_id=item["chunk_id"],
            )
        )
    if missing_values:
        lines.extend(["", "## Missing important values", ""])
        lines.extend(f"- {value}" for value in missing_values)
    else:
        lines.extend(
            [
                "",
                "## Coverage",
                "",
                "- All important scalar values appear in the generated Markdown.",
            ]
        )
    for chunk in chunks:
        lines.extend(
            [
                "",
                f"## {chunk.metadata.get('chunk_index')}. {chunk.metadata.get('section')}",
                "",
                f"- Chunk ID: `{chunk.chunk_id}`",
                f"- Section path: {' > '.join(chunk.metadata.get('section_path', []))}",
                "",
                "```markdown",
                chunk.text,
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def _render_chunks_html(
    chunks: list[Chunk],
    diagnostics: list[dict[str, Any]],
    missing_values: list[str],
) -> str:
    cards = []
    for chunk, item in zip(chunks, diagnostics, strict=True):
        chunk_index = html.escape(str(chunk.metadata.get("chunk_index")))
        section_name = html.escape(str(chunk.metadata.get("section")))
        section_path = html.escape(" > ".join(item["section_path"]))
        models = html.escape(", ".join(item["model_mentions"]) or "-")
        cards.append(
            "<section>"
            f"<h2>{chunk_index}. {section_name}</h2>"
            f"<p><strong>Section:</strong> {section_path}</p>"
            f"<p><strong>Models:</strong> {models} | "
            f"<strong>Price:</strong> {'yes' if item['contains_price'] else 'no'} | "
            f"<strong>modelId:</strong> {'yes' if item['contains_model_id'] else 'no'} | "
            f"<strong>Choices:</strong> {'yes' if item['contains_choices'] else 'no'}</p>"
            f"<pre>{html.escape(chunk.text)}</pre>"
            "</section>"
        )
    missing = (
        "".join(f"<li>{html.escape(value)}</li>" for value in missing_values) or "<li>None</li>"
    )
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>URL ground truth chunk review</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.5; margin: 24px; color: #1f2933; }}
    section {{ border: 1px solid #d6dde5; border-radius: 8px; margin: 18px 0; padding: 16px; }}
    pre {{
      background: #f6f8fa;
      border-radius: 6px;
      overflow-x: auto;
      padding: 12px;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <h1>URL ground truth chunk review</h1>
  <h2>Missing important values</h2>
  <ul>{missing}</ul>
  {"".join(cards)}
</body>
</html>
"""


if __name__ == "__main__":
    main()
