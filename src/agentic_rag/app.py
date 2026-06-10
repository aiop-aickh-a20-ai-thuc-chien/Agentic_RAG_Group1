"""Application entry boundary for the generation API."""

from __future__ import annotations


def run_app(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI backend used by the Next.js frontend."""

    import uvicorn

    uvicorn.run("agentic_rag.api:api", host=host, port=port)


if __name__ == "__main__":
    run_app()
