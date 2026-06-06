# Guide

This folder is a working guide area for project onboarding, AI collaboration, and research notes.

## Contents

- `starting-point.md`: current starting point for creating code.
- `docs/`: copy of the project documentation from the root `docs/` folder.
- `research/`: place research copied from ChatGPT, Gemini, Claude, and Perplexity.

## How to Use

1. Read `starting-point.md` to know where new code work should begin.
2. Start with `docs/` to understand project workflow, coding standards, module contracts, and AI collaboration rules.
3. Add external research notes into the matching folder under `research/`.
4. Keep research notes source-labeled so the team can compare outputs and trace where each idea came from.
5. When research becomes an accepted project decision, move or summarize it into the official documentation in `docs/`.

## Changing the Starting Point

When the coding focus changes, update only `starting-point.md`. Keep the path specific to the package, module, or file where new implementation should begin.

## Suggested Research Layout

Use one Markdown file per topic, for example:

```text
research/
  chatgpt/
    rag-evaluation.md
  gemini/
    vector-database-options.md
  claude/
    ingestion-pipeline-review.md
  perplexity/
    current-rag-best-practices.md
```

Prefer Markdown notes with:

- topic title
- source name
- date copied
- key findings
- links or citations, when available
- project decision or follow-up action
