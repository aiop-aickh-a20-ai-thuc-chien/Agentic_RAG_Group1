# Model Runtime Configuration

This document is the source of truth for LLM, embedding, and reranker environment
configuration. The public provider values describe where a model runs; LiteLLM
provider prefixes are an internal routing detail.

## Configuration Loading

The runtime reads simple `KEY=VALUE` entries from `.env`. Values already present
in the process environment take precedence over `.env` values. Blank values are
treated as unset.

The checked-in `.env.example` is a runnable keyless sample. It keeps the LLM
provider set to `none`, matching the runtime default when the provider is
omitted. Enable a provider only after configuring a usable model and any
required credentials.

Timeout values must be positive numbers. `EMBEDDING_DIMENSIONS`, when set, must
be a positive integer. Invalid settings raise `ModelRuntimeConfigurationError`
before a provider call is made.

## Provider Semantics

| Provider value | Meaning |
| --- | --- |
| `local` | A model hosted by a separate HTTP backend on infrastructure you control. |
| `sentence_transformers` | An in-process embedding or reranker loaded with `sentence-transformers`. |
| Provider name | A named API provider routed through LiteLLM, such as `openai`, `anthropic`, `cohere`, or `voyage`. |
| `none` | Disable LLM calls. |
| `score` | Use deterministic score sorting instead of a model reranker. |

`local` has a protocol-specific internal LiteLLM mapping:

| Component | Required server contract | Internal LiteLLM routing |
| --- | --- | --- |
| LLM | OpenAI-compatible chat completion API | Model prefix `openai/<model>` |
| Embedding | OpenAI-compatible embeddings API | Model prefix `openai/<model>` |
| Reranker | Jina/vLLM-compatible `/rerank` API | `custom_llm_provider=hosted_vllm`; model remains `<model>` |

`hosted_vllm` is not an environment provider value. The reranker adapter passes
it directly to LiteLLM as an internal routing argument when
`RERANK_PROVIDER=local`.

Every `local` profile requires an explicit model and API base. API keys remain
optional because self-hosted servers may not require authentication.

The legacy embedding values `huggingface` and `local_openai` are rejected. Use
`sentence_transformers` and `local`, respectively.

## LLM Profiles and Inheritance

The global LLM profile uses:

```env
LLM_PROVIDER=
LLM_MODEL=
LLM_API_BASE=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=60
```

The following roles can override each field independently:

- `QUERY_REWRITE_LLM_*`
- `QUERY_TRANSFORM_LLM_*`
- `GENERATION_LLM_*`
- `INGESTION_LLM_*`
- `EVALUATION_LLM_*`

A blank role-specific value inherits the corresponding global `LLM_*` value.
For example, `GENERATION_LLM_MODEL=` inherits `LLM_MODEL`, while a nonblank
`GENERATION_LLM_MODEL` replaces it only for generation.

Blank role-specific values do not clear global values. In particular,
`GENERATION_LLM_API_KEY=` inherits `LLM_API_KEY`; it must not be used to remove
a global credential before calling a different backend. Use a separate complete
runtime profile when a role must use an incompatible provider, API base, or
credential set.

If the resolved provider is `none`, the resolved model is ignored and no
LiteLLM client is created. Generation then uses the deterministic fallback that
returns selected evidence text. Any enabled provider requires a resolved model.
The `local` provider additionally requires a resolved API base.

`sentence_transformers` is not a valid LLM provider. To run an LLM on local
infrastructure, expose it through an OpenAI-compatible HTTP server and use
`LLM_PROVIDER=local`.

## Embedding Configuration

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_DIMENSIONS=
EMBEDDING_TIMEOUT_SECONDS=60
EMBEDDING_DEVICE=auto
```

When `EMBEDDING_PROVIDER` is omitted, it defaults to `sentence_transformers`.
That provider also supplies the multilingual default model when
`EMBEDDING_MODEL` is blank. Install the local dependency group before using it:

```bash
uv sync --extra local-models
```

`EMBEDDING_DEVICE` supports `auto`, `cpu`, `cuda`, and `mps`, but is used only
for `sentence_transformers`. HTTP and named API providers ignore it.

All other providers require `EMBEDDING_MODEL`. The `local` provider also
requires `EMBEDDING_API_BASE`. Set `EMBEDDING_DIMENSIONS` only when the server
supports a dimensions parameter and the expected vector size is known.

Changing embedding provider, model, or dimensions requires a new vector-store
collection or a complete reindex. One collection must not mix embedding
profiles.

## Reranker Configuration

```env
RERANK_PROVIDER=score
RERANK_MODEL=
RERANK_API_BASE=
RERANK_API_KEY=
RERANK_TIMEOUT_SECONDS=60
RERANK_DEVICE=auto
RERANK_PRELOAD=false
```

When `RERANK_PROVIDER` is omitted, it defaults to `score`, which deduplicates
candidates, sorts them by their existing scores, and assigns rerank positions.

`RERANK_PROVIDER=sentence_transformers` loads an in-process cross-encoder. If
`RERANK_MODEL` is blank, it defaults to `BAAI/bge-reranker-v2-m3`.
`RERANK_DEVICE` and `RERANK_PRELOAD` apply only to this in-process provider and
are ignored for `score`, `local`, and named API providers.

All API rerankers require `RERANK_MODEL`. `RERANK_PROVIDER=local` also requires
`RERANK_API_BASE`. The server must implement the Jina/vLLM rerank request and
response shape. The API base may include `/rerank`; pinned LiteLLM normalizes
the final endpoint.

## Validation and Fallback Behavior

Configuration errors fail fast and do not silently select another provider.
Examples include an enabled provider without a model, `local` without an API
base, nonpositive timeouts, and legacy provider values.

Invocation failures are handled at component boundaries:

- LLM invocation failures are raised as `ModelInvocationError`.
- Embedding invocation failures are raised as `ModelInvocationError`.
- Reranker invocation failures are normalized and the retrieval fusion boundary
  falls back to `score`, recording the configured provider and fallback reason.
- `LLM_PROVIDER=none` is an explicit disabled mode, not an invocation failure.

## Example Configurations

### Fully Offline Model Runtime

```env
LLM_PROVIDER=none

EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=auto

RERANK_PROVIDER=sentence_transformers
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_DEVICE=auto
RERANK_PRELOAD=false
```

### Hosted Local HTTP Services

```env
LLM_PROVIDER=local
LLM_MODEL=local-chat-model
LLM_API_BASE=http://127.0.0.1:8000/v1
LLM_API_KEY=

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=local-embedding-model
EMBEDDING_API_BASE=http://127.0.0.1:8001/v1
EMBEDDING_API_KEY=

RERANK_PROVIDER=local
RERANK_MODEL=local-reranker
RERANK_API_BASE=http://127.0.0.1:8002
RERANK_API_KEY=
```

### Named API Providers Through LiteLLM

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_api_key

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=your_api_key

RERANK_PROVIDER=cohere
RERANK_MODEL=rerank-v3.5
RERANK_API_KEY=your_api_key
```

### Role-Specific LLM Override

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_api_key

QUERY_REWRITE_LLM_MODEL=gpt-4o
```

The query rewrite role inherits the global provider and credentials while using
its own model. Use the complete hosted-local profile above when running against
a local HTTP backend so global API credentials are not inherited accidentally.

## Migration from Legacy Values

Replace legacy embedding settings as follows:

```env
# Before
EMBEDDING_PROVIDER=huggingface

# After
EMBEDDING_PROVIDER=sentence_transformers
```

```env
# Before
EMBEDDING_PROVIDER=local_openai

# After
EMBEDDING_PROVIDER=local
EMBEDDING_API_BASE=http://127.0.0.1:8000/v1
```

No environment-variable names are renamed. `RERANK_PROVIDER` remains the
canonical reranker provider variable.
