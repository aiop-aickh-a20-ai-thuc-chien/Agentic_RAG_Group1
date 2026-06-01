# PDF Ingestion Debug Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit PDF ingestion debug helper that saves parsed Markdown, chunk JSONL, and a manifest JSON for evaluation without adding side effects to `load_pdf_chunks(path: str) -> list[Chunk]`.

**Architecture:** Keep `load_pdf_chunks()` as the pure in-memory ingestion API. Add a separate artifact module that reuses the same parser and chunk-mapping pipeline, then writes output under an ignored `.data/artifacts/<pdf-stem>/<run-id>/` folder. Use Pydantic v2 for artifact metadata and fake parser boundaries in tests so CI never runs real Docling conversion.

**Tech Stack:** Python 3.12, uv, Pydantic v2, Docling parser boundary, Ruff, mypy, pytest.

---

## Context

- Current branch: `feature/pdf-parser-implementation`.
- Existing public PDF API: `from agentic_rag.ingestion.pdf import load_pdf_chunks`.
- Existing `load_pdf_chunks(path: str) -> list[Chunk]` must remain side-effect free.
- Existing PDF artifact/cache path policy: `src/agentic_rag/ingestion/pdf/.gitignore` ignores `.data/`.
- Existing local untracked plan files under `docs/superpowers/plans/` must not be staged accidentally.
- Documentation should remain Vietnamese for repo-facing docs.

## File Structure

- Create: `src/agentic_rag/ingestion/pdf/artifacts.py`
  - Owns artifact run-folder creation, JSONL writing, manifest writing, default artifact root, and Pydantic metadata model.
- Modify: `src/agentic_rag/ingestion/pdf/loader.py`
  - Extracts shared validation and Markdown-to-`Chunk` mapping helpers so the artifact helper and `load_pdf_chunks()` use the same chunk behavior.
- Modify: `src/agentic_rag/ingestion/pdf/__init__.py`
  - Exports the new explicit artifact helper and manifest model.
- Create: `src/agentic_rag/ingestion/pdf/tests/test_artifacts.py`
  - Tests artifact persistence with a fake parser and deterministic run ID.
- Modify: `src/agentic_rag/ingestion/pdf/tests/test_loader.py`
  - Adds a regression test that loader execution does not create debug files next to the input PDF.
- Modify: `src/agentic_rag/ingestion/pdf/README.md`
  - Documents the debug artifact helper, saved files, ignored `.data/` path, and the purity of `load_pdf_chunks()`.

## Public Contract

Keep this API unchanged:

```python
from agentic_rag.ingestion.pdf import load_pdf_chunks

chunks = load_pdf_chunks("path/to/file.pdf")
```

Add this explicit API:

```python
from agentic_rag.ingestion.pdf import save_pdf_ingestion_artifacts

manifest = save_pdf_ingestion_artifacts("path/to/file.pdf")
```

Default output layout:

```text
src/agentic_rag/ingestion/pdf/.data/artifacts/<safe-pdf-stem>/<run-id>/
  parsed.md
  chunks.jsonl
  manifest.json
```

`chunks.jsonl` must contain one serialized shared `Chunk` object per line. `manifest.json` must be generated from a Pydantic model and include at least:

```python
artifact_schema_version: int
input_path: str
parser: str
run_id: str
created_at: str
artifact_root: str
run_dir: str
markdown_path: str
chunks_path: str
manifest_path: str
chunk_count: int
```

## Task 1: Add Artifact Persistence Tests

**Files:**

- Create: `src/agentic_rag/ingestion/pdf/tests/test_artifacts.py`
- Modify: `src/agentic_rag/ingestion/pdf/tests/test_loader.py`

- [ ] **Step 1: Create the fake parser and artifact write test**

Add `src/agentic_rag/ingestion/pdf/tests/test_artifacts.py`:

```python
import json
from pathlib import Path

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.artifacts import _save_pdf_ingestion_artifacts


class FakeParser:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.seen_path: Path | None = None

    def parse_to_markdown(self, path: Path) -> str:
        self.seen_path = path
        return self.markdown


def test_save_pdf_ingestion_artifacts_writes_markdown_chunks_and_manifest(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "VinFast Warranty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "artifacts"
    parser = FakeParser("# Warranty\nPin duoc bao hanh 8 nam.\n\n## Battery\nDieu kien ap dung.")

    manifest = _save_pdf_ingestion_artifacts(
        pdf_path,
        parser,
        output_root=output_root,
        run_id="manual-run",
    )

    run_dir = output_root / "vinfast_warranty" / "manual_run"
    assert manifest.run_dir == str(run_dir)
    assert manifest.markdown_path == str(run_dir / "parsed.md")
    assert manifest.chunks_path == str(run_dir / "chunks.jsonl")
    assert manifest.manifest_path == str(run_dir / "manifest.json")
    assert manifest.chunk_count == 2
    assert manifest.parser == "docling"
    assert parser.seen_path == pdf_path

    assert (run_dir / "parsed.md").read_text(encoding="utf-8") == parser.markdown

    chunk_lines = (run_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    chunks = [Chunk.model_validate(json.loads(line)) for line in chunk_lines]
    assert [chunk.chunk_id for chunk in chunks] == [
        "pdf_vinfast_warranty_c0001",
        "pdf_vinfast_warranty_c0002",
    ]
    assert chunks[0].metadata["section"] == "Warranty"
    assert chunks[1].metadata["section"] == "Battery"

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload == manifest.model_dump(mode="json")
```

- [ ] **Step 2: Add the side-effect regression test**

Append to `src/agentic_rag/ingestion/pdf/tests/test_loader.py`:

```python
def test_load_pdf_chunks_does_not_write_debug_files_next_to_input(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    chunks = _load_pdf_chunks(pdf_path, FakeParser("# Intro\nNoi dung."))

    assert len(chunks) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source.pdf"]
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest src/agentic_rag/ingestion/pdf/tests/test_artifacts.py src/agentic_rag/ingestion/pdf/tests/test_loader.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'agentic_rag.ingestion.pdf.artifacts'
```

## Task 2: Share Loader Validation and Chunk Mapping

**Files:**

- Modify: `src/agentic_rag/ingestion/pdf/loader.py`

- [ ] **Step 1: Extract validation and Markdown mapping helpers**

Refactor `src/agentic_rag/ingestion/pdf/loader.py` so `_load_pdf_chunks()` delegates to helpers:

```python
def _load_pdf_chunks(path: Path, parser: PdfMarkdownParser) -> list[Chunk]:
    _validate_pdf_path(path)
    markdown = parser.parse_to_markdown(path)
    return _chunks_from_markdown(path, markdown)


def _validate_pdf_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file path, got: {path}")


def _chunks_from_markdown(path: Path, markdown: str) -> list[Chunk]:
    markdown_chunks = chunk_markdown(markdown)
    safe_file_stem = _safe_chunk_id_part(path.stem)

    chunks: list[Chunk] = []
    for index, markdown_chunk in enumerate(markdown_chunks, start=1):
        chunks.append(
            Chunk(
                chunk_id=f"pdf_{safe_file_stem}_c{index:04d}",
                text=markdown_chunk.text,
                metadata={
                    "source": str(path),
                    "source_type": "pdf",
                    "file_name": path.name,
                    "page": None,
                    "section": markdown_chunk.section,
                    "parser": "docling",
                    "chunk_index": index,
                },
            )
        )
    return chunks
```

- [ ] **Step 2: Run existing loader tests**

Run:

```bash
uv run pytest src/agentic_rag/ingestion/pdf/tests/test_loader.py -q
```

Expected:

```text
5 passed
```

## Task 3: Implement Artifact Helper

**Files:**

- Create: `src/agentic_rag/ingestion/pdf/artifacts.py`
- Modify: `src/agentic_rag/ingestion/pdf/__init__.py`

- [ ] **Step 1: Create the artifact module**

Add `src/agentic_rag/ingestion/pdf/artifacts.py`:

```python
"""Debug artifact persistence for PDF ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.pdf.loader import (
    _chunks_from_markdown,
    _safe_chunk_id_part,
    _validate_pdf_path,
)
from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser, PdfMarkdownParser

DEFAULT_PDF_ARTIFACT_ROOT = Path(__file__).resolve().parent / ".data" / "artifacts"


class _PdfArtifactModel(BaseModel):
    """Base config for PDF artifact metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfIngestionArtifactManifest(_PdfArtifactModel):
    """Metadata describing one persisted PDF ingestion artifact run."""

    artifact_schema_version: int = 1
    input_path: str
    parser: str
    run_id: str
    created_at: str
    artifact_root: str
    run_dir: str
    markdown_path: str
    chunks_path: str
    manifest_path: str
    chunk_count: int


def save_pdf_ingestion_artifacts(
    path: str,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    """Parse a PDF, chunk it, and save debug artifacts for evaluation."""

    return _save_pdf_ingestion_artifacts(
        Path(path),
        DoclingMarkdownParser(),
        output_root=output_root,
        run_id=run_id,
    )


def _save_pdf_ingestion_artifacts(
    path: Path,
    parser: PdfMarkdownParser,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    _validate_pdf_path(path)

    markdown = parser.parse_to_markdown(path)
    chunks = _chunks_from_markdown(path, markdown)

    artifact_root = Path(output_root) if output_root is not None else DEFAULT_PDF_ARTIFACT_ROOT
    resolved_run_id = _safe_run_id(run_id)
    run_dir = artifact_root / _safe_chunk_id_part(path.stem) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(markdown, encoding="utf-8")
    with chunks_path.open("w", encoding="utf-8") as chunks_file:
        for chunk in chunks:
            chunks_file.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            chunks_file.write("\n")

    manifest = PdfIngestionArtifactManifest(
        input_path=str(path),
        parser="docling",
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        manifest_path=str(manifest_path),
        chunk_count=len(chunks),
    )
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _safe_run_id(run_id: str | None) -> str:
    if run_id is None:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return _safe_chunk_id_part(run_id)
```

- [ ] **Step 2: Export the public helper and model**

Modify `src/agentic_rag/ingestion/pdf/__init__.py`:

```python
"""PDF ingestion package."""

from agentic_rag.ingestion.pdf.artifacts import (
    PdfIngestionArtifactManifest,
    save_pdf_ingestion_artifacts,
)
from agentic_rag.ingestion.pdf.loader import load_pdf_chunks

__all__ = [
    "PdfIngestionArtifactManifest",
    "load_pdf_chunks",
    "save_pdf_ingestion_artifacts",
]
```

- [ ] **Step 3: Run focused artifact tests**

Run:

```bash
uv run pytest src/agentic_rag/ingestion/pdf/tests/test_artifacts.py src/agentic_rag/ingestion/pdf/tests/test_loader.py -q
```

Expected:

```text
6 passed
```

## Task 4: Update Vietnamese PDF Documentation

**Files:**

- Modify: `src/agentic_rag/ingestion/pdf/README.md`

- [ ] **Step 1: Document explicit debug artifact saving**

Add a section after `## Chạy PDF ingestion baseline`:

````markdown
## Lưu artifact để debug và đánh giá

`load_pdf_chunks()` chỉ trả về `Chunk` trong memory và không tự ghi file. Khi cần
kiểm tra output parser hoặc so sánh chất lượng chunking, dùng helper rõ ràng:

```bash
uv run python -c "from agentic_rag.ingestion.pdf import save_pdf_ingestion_artifacts; print(save_pdf_ingestion_artifacts('path/to/file.pdf').model_dump())"
```

Mặc định helper ghi vào thư mục đã được ignore:

```text
src/agentic_rag/ingestion/pdf/.data/artifacts/<pdf-stem>/<run-id>/
  parsed.md
  chunks.jsonl
  manifest.json
```

Ý nghĩa các file:

- `parsed.md`: Markdown do Docling export từ PDF gốc.
- `chunks.jsonl`: mỗi dòng là một shared `Chunk` sau bước chunking.
- `manifest.json`: metadata của lần chạy, gồm input path, parser, run id, đường
  dẫn artifact và số lượng chunk.

Không commit nội dung trong `.data/`; đây chỉ là dữ liệu phục vụ debug và
evaluation cục bộ.
````

- [ ] **Step 2: Run docs-adjacent format checks**

Run:

```bash
uv run ruff format --check src/agentic_rag/ingestion/pdf
uv run ruff check src/agentic_rag/ingestion/pdf
```

Expected:

```text
All checks passed!
```

## Task 5: Verify Full Quality Gates

**Files:**

- No source edits unless a gate reports a real issue.

- [ ] **Step 1: Verify root environment lock**

Run:

```bash
uv sync --locked
```

Expected: command exits `0`.

- [ ] **Step 2: Verify root quality gate**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Expected:

```text
ruff format: unchanged
ruff check: All checks passed!
mypy: Success
pytest: all tests passed
```

- [ ] **Step 3: Verify PDF subproject lock**

Run:

```bash
uv --directory src/agentic_rag/ingestion/pdf sync --locked
```

Expected: command exits `0`.

- [ ] **Step 4: Verify PDF subproject quality gate**

Run:

```bash
uv --directory src/agentic_rag/ingestion/pdf run ruff format --check .
uv --directory src/agentic_rag/ingestion/pdf run ruff check .
uv --directory src/agentic_rag/ingestion/pdf run mypy
uv --directory src/agentic_rag/ingestion/pdf run pytest -q
```

Expected:

```text
ruff format: unchanged
ruff check: All checks passed!
mypy: Success
pytest: all tests passed
```

## Task 6: Commit Only Intended Files

**Files:**

- Stage: `docs/superpowers/plans/2026-05-31-pdf-ingestion-debug-artifacts.md`
- Stage: `src/agentic_rag/ingestion/pdf/artifacts.py`
- Stage: `src/agentic_rag/ingestion/pdf/loader.py`
- Stage: `src/agentic_rag/ingestion/pdf/__init__.py`
- Stage: `src/agentic_rag/ingestion/pdf/tests/test_artifacts.py`
- Stage: `src/agentic_rag/ingestion/pdf/tests/test_loader.py`
- Stage: `src/agentic_rag/ingestion/pdf/README.md`

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short
```

Expected: only the intended files above plus pre-existing untracked plan files.

- [ ] **Step 2: Stage exact files**

Run:

```bash
git add docs/superpowers/plans/2026-05-31-pdf-ingestion-debug-artifacts.md
git add src/agentic_rag/ingestion/pdf/artifacts.py
git add src/agentic_rag/ingestion/pdf/loader.py
git add src/agentic_rag/ingestion/pdf/__init__.py
git add src/agentic_rag/ingestion/pdf/tests/test_artifacts.py
git add src/agentic_rag/ingestion/pdf/tests/test_loader.py
git add src/agentic_rag/ingestion/pdf/README.md
```

- [ ] **Step 3: Confirm staging excludes unrelated plans**

Run:

```bash
git diff --cached --name-only
```

Expected:

```text
docs/superpowers/plans/2026-05-31-pdf-ingestion-debug-artifacts.md
src/agentic_rag/ingestion/pdf/README.md
src/agentic_rag/ingestion/pdf/__init__.py
src/agentic_rag/ingestion/pdf/artifacts.py
src/agentic_rag/ingestion/pdf/loader.py
src/agentic_rag/ingestion/pdf/tests/test_artifacts.py
src/agentic_rag/ingestion/pdf/tests/test_loader.py
```

- [ ] **Step 4: Commit**

Run:

```bash
git commit -m "feat(pdf): save ingestion debug artifacts"
```

Expected: commit succeeds and commit message contains no `Co-Authored-By` trailer.

## Self-Review Checklist

- [ ] The plan keeps `load_pdf_chunks(path: str) -> list[Chunk]` unchanged and side-effect free.
- [ ] Artifact saving is explicit via `save_pdf_ingestion_artifacts()`.
- [ ] Parsed Markdown, chunk JSONL, and manifest JSON are all covered by tests.
- [ ] Pydantic is used for artifact metadata.
- [ ] Tests use fake parser boundaries and do not run real Docling conversion.
- [ ] Vietnamese README documents the new workflow.
- [ ] Quality gates cover both root project and PDF subproject.
- [ ] Commit staging excludes unrelated existing plan files.
