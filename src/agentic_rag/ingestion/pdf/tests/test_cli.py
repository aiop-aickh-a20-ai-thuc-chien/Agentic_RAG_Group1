import json
from pathlib import Path

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf import (
    LoadedPdfDocument,
    PdfIngestionArtifactManifest,
    PdfMultimodalArtifactManifest,
    cli,
)


def test_parse_cli_help_lists_supported_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["parse", "--help"])

    output = capsys.readouterr().out

    assert exc_info.value.code == 0
    assert "--pipeline PIPELINE_NAME" in output
    assert "  - ocr" in output
    assert "  - vlm" in output
    assert "--strategy STRATEGY_NAME" in output
    assert "  - docling" in output
    assert "  - mineru" in output
    assert "--chunker CHUNKER_NAME" in output
    assert "  - deterministic" in output
    assert "  - docling-hybrid" in output
    assert "  - docling-page-aware" in output
    assert "--write-multimodal-artifacts" in output


def test_parse_cli_emits_json_and_forwards_arguments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str | None] = {}
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_load_pdf_with_markdown(path: str, **kwargs: str | None) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        assert path == str(pdf_path)
        return LoadedPdfDocument(
            markdown="# Intro\nNoi dung parser.",
            chunks=[
                Chunk(
                    chunk_id="pdf_source_c0001",
                    text="Noi dung parser.",
                    metadata={
                        "source": str(pdf_path),
                        "source_type": "internal",
                        "file_name": "source.pdf",
                        "section": "Intro",
                    },
                )
            ],
            parser="docling",
            pipeline="ocr",
            strategy="docling",
            chunker="deterministic",
        )

    monkeypatch.setattr(cli, "load_pdf_with_markdown", fake_load_pdf_with_markdown)

    exit_code = cli.main(
        [
            "parse",
            str(pdf_path),
            "--pipeline",
            "ocr",
            "--strategy",
            "docling",
            "--chunker",
            "deterministic",
            "--include-markdown",
            "--output-json",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert seen_kwargs == {
        "parser_name": None,
        "pipeline_name": "ocr",
        "strategy_name": "docling",
        "chunker_name": "deterministic",
    }
    assert payload["path"] == str(pdf_path)
    assert payload["pipeline"] == "ocr"
    assert payload["strategy"] == "docling"
    assert payload["parser"] == "docling"
    assert payload["chunker"] == "deterministic"
    assert payload["markdown_chars"] == 24
    assert payload["markdown"] == "# Intro\nNoi dung parser."
    assert payload["chunk_count"] == 1
    assert payload["chunks"][0]["chunk_id"] == "pdf_source_c0001"


def test_parse_cli_uses_env_defaults_and_writes_standard_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str | None] = {}
    seen_artifact_args: dict[str, object] = {}
    pdf_path = tmp_path / "source.pdf"
    output_root = tmp_path / "artifacts"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("LOCAL_PDF_PIPELINE", "ocr")
    monkeypatch.setenv("LOCAL_PDF_STRATEGY", "docling")
    monkeypatch.setenv("LOCAL_PDF_CHUNKER", "deterministic")

    def fake_load_pdf_with_markdown(path: str, **kwargs: str | None) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        return LoadedPdfDocument(
            markdown="# Intro\nNoi dung.",
            chunks=[],
            parser="docling",
            pipeline="ocr",
            strategy="docling",
            chunker="deterministic",
        )

    monkeypatch.setattr(cli, "load_pdf_with_markdown", fake_load_pdf_with_markdown)

    def fake_save_loaded_pdf_ingestion_artifacts(
        path: Path,
        loaded: LoadedPdfDocument,
        **kwargs: object,
    ) -> PdfIngestionArtifactManifest:
        seen_artifact_args["path"] = path
        seen_artifact_args["loaded"] = loaded
        seen_artifact_args.update(kwargs)
        return PdfIngestionArtifactManifest(
            input_path=str(path),
            parser=loaded.parser,
            pipeline=loaded.pipeline,
            strategy=loaded.strategy,
            chunker=loaded.chunker,
            run_id="cli_run",
            created_at="2026-06-03T00:00:00+00:00",
            artifact_root=str(output_root),
            run_dir=str(output_root / "source" / "cli_run"),
            markdown_path=str(output_root / "source" / "cli_run" / "parsed.md"),
            chunks_path=str(output_root / "source" / "cli_run" / "chunks.jsonl"),
            chunks_markdown_path=str(output_root / "source" / "cli_run" / "chunks.md"),
            manifest_path=str(output_root / "source" / "cli_run" / "manifest.json"),
            chunk_count=0,
        )

    monkeypatch.setattr(
        cli,
        "save_loaded_pdf_ingestion_artifacts",
        fake_save_loaded_pdf_ingestion_artifacts,
    )

    exit_code = cli.main(
        [
            "parse",
            str(pdf_path),
            "--write-artifacts",
            "--output-root",
            str(output_root),
            "--run-id",
            "cli-run",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert stdout.strip() == f"Wrote parser artifacts to {output_root / 'source' / 'cli_run'}"
    assert seen_kwargs == {
        "parser_name": None,
        "pipeline_name": "ocr",
        "strategy_name": "docling",
        "chunker_name": "deterministic",
    }
    assert seen_artifact_args["path"] == pdf_path
    assert isinstance(seen_artifact_args["loaded"], LoadedPdfDocument)
    assert seen_artifact_args["output_root"] == output_root
    assert seen_artifact_args["run_id"] == "cli-run"


def test_parse_cli_artifact_only_output_does_not_build_json_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    output_root = tmp_path / "artifacts"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    loaded = LoadedPdfDocument(
        markdown="# Intro\nNoi dung.",
        chunks=[
            Chunk(
                chunk_id="pdf_source_c0001",
                text="Noi dung.",
                metadata={"source": str(pdf_path), "source_type": "internal"},
            )
        ],
        parser="docling",
        pipeline="ocr",
        strategy="docling",
        chunker="deterministic",
    )

    monkeypatch.setattr(cli, "load_pdf_with_markdown", lambda *_args, **_kwargs: loaded)

    def fail_payload_build(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("artifact-only CLI output should not build JSON payload")

    monkeypatch.setattr(cli, "_loaded_pdf_payload", fail_payload_build)

    def fake_save_loaded_pdf_ingestion_artifacts(
        path: Path,
        loaded_pdf: LoadedPdfDocument,
        **_kwargs: object,
    ) -> PdfIngestionArtifactManifest:
        return PdfIngestionArtifactManifest(
            input_path=str(path),
            parser=loaded_pdf.parser,
            pipeline=loaded_pdf.pipeline,
            strategy=loaded_pdf.strategy,
            chunker=loaded_pdf.chunker,
            run_id="cli_run",
            created_at="2026-06-03T00:00:00+00:00",
            artifact_root=str(output_root),
            run_dir=str(output_root / "source" / "cli_run"),
            markdown_path=str(output_root / "source" / "cli_run" / "parsed.md"),
            chunks_path=str(output_root / "source" / "cli_run" / "chunks.jsonl"),
            chunks_markdown_path=str(output_root / "source" / "cli_run" / "chunks.md"),
            manifest_path=str(output_root / "source" / "cli_run" / "manifest.json"),
            chunk_count=1,
        )

    monkeypatch.setattr(
        cli,
        "save_loaded_pdf_ingestion_artifacts",
        fake_save_loaded_pdf_ingestion_artifacts,
    )

    exit_code = cli.main(
        [
            "parse",
            str(pdf_path),
            "--write-artifacts",
            "--output-root",
            str(output_root),
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert stdout.strip() == f"Wrote parser artifacts to {output_root / 'source' / 'cli_run'}"


def test_parse_cli_writes_multimodal_artifacts_without_building_standard_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    output_root = tmp_path / "artifacts"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    seen_artifact_args: dict[str, object] = {}

    def fail_load_pdf_with_markdown(*_args: object, **_kwargs: object) -> LoadedPdfDocument:
        raise AssertionError("multimodal artifact CLI should call multimodal helper directly")

    monkeypatch.setattr(cli, "load_pdf_with_markdown", fail_load_pdf_with_markdown)

    def fake_save_pdf_multimodal_artifacts(
        path: str,
        **kwargs: object,
    ) -> PdfMultimodalArtifactManifest:
        seen_artifact_args["path"] = path
        seen_artifact_args.update(kwargs)
        return PdfMultimodalArtifactManifest(
            input_path=path,
            parser="docling",
            run_id="image_run",
            created_at="2026-06-05T00:00:00+00:00",
            artifact_root=str(output_root),
            run_dir=str(output_root / "source" / "image_run"),
            markdown_path=str(output_root / "source" / "image_run" / "parsed.md"),
            chunks_path=str(output_root / "source" / "image_run" / "chunks.jsonl"),
            chunks_markdown_path=str(output_root / "source" / "image_run" / "chunks.md"),
            manifest_path=str(output_root / "source" / "image_run" / "manifest.json"),
            elements_path=str(output_root / "source" / "image_run" / "elements.jsonl"),
            assets_dir=str(output_root / "source" / "image_run" / "assets"),
            chunk_count=1,
            element_count=1,
            image_count=1,
            table_count=0,
            chart_count=0,
        )

    monkeypatch.setattr(
        cli,
        "save_pdf_multimodal_artifacts",
        fake_save_pdf_multimodal_artifacts,
    )

    exit_code = cli.main(
        [
            "parse",
            str(pdf_path),
            "--write-multimodal-artifacts",
            "--output-root",
            str(output_root),
            "--run-id",
            "image-run",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert stdout.strip() == (
        f"Wrote multimodal parser artifacts to {output_root / 'source' / 'image_run'}"
    )
    assert seen_artifact_args == {
        "path": str(pdf_path),
        "output_root": output_root,
        "run_id": "image-run",
    }
