# Metadata Filtering Improvements for RAG Retrieval

## Purpose

This document explores advanced methods and improvements for metadata filtering in the RAG ingestion and retrieval pipeline, going beyond basic pre- and post-filtering strategies. The goal is to enhance retrieval precision, recall, and overall relevance, ultimately leading to higher quality answers and a more efficient system.

## Current State and Implicit Filtering

The existing documentation (`metadata_explained.md`, `duplicate_detection_latency_relevance_strategy.md`) already highlights the importance of metadata for various purposes:

-   **Pre-filtering for duplicate detection**: Grouping chunks by `(canonical_domain, page_type, entity_type, entity_name, attribute_group, language)` before running expensive similarity comparisons.
-   **Quality gating**: Using `url_quality_gate` to accept or reject chunks for indexing.
-   **Ranking hints**: `is_noise` and `retrieval_weight` are used to drop or downrank low-value content.
-   **Citation and grouping**: Fields like `source_type`, `domain`, `language`, `page_type`, `entity_type`, `product_specs` are intended for filtering and grouping.

While these are effective, they primarily represent static or rule-based filtering. This report focuses on more dynamic, integrated, and intelligent approaches.

## Proposed Improvements and Advanced Filtering Methods

### 1. Dynamic/Adaptive Filtering based on Query Intent

Instead of applying a fixed set of filters, dynamically adjust them based on the interpreted intent of the user's query.

-   **Mechanism**:
    -   Use an LLM or rule-based intent classifier to determine the user's primary goal (e.g., "price inquiry", "comparison", "warranty details", "technical specifications").
    -   Map detected intents to specific metadata filters. For a "price inquiry" about a `VF8`, automatically filter for `entity_name="VF 8"` and `attribute_group="pricing_specs"`.
    -   Consider conversational history to refine filters (e.g., if the user previously asked about `VF8`, subsequent queries might implicitly carry that `entity_name` filter).
-   **Benefits**: Improves precision by focusing retrieval on highly relevant document subsets, reduces noise.
-   **Implementation Considerations**: Requires robust intent classification and a mapping layer from intents to metadata filters.

### 2. Hierarchical and Faceted Filtering

Leverage the hierarchical nature of some metadata (e.g., `section_path`, product categories) and allow for multi-dimensional filtering.

-   **Mechanism**:
    -   **Hierarchical**: For `section_path` (e.g., `["Ô tô", "Dòng xe D-SUV", "VF 8"]`), a query about "Dòng xe D-SUV" would retrieve chunks from all sub-sections. Users could "drill down" into specific sub-sections.
    -   **Faceted**: Allow combining multiple filters (e.g., `page_type="product"` AND `entity_type="car"` AND `language="vi"`). This is common in e-commerce search.
-   **Benefits**: Provides granular control for users (or internal agents) to refine search, improves discoverability of specific information.
-   **Implementation Considerations**: Requires a structured metadata schema that supports hierarchies and an efficient indexing mechanism (e.g., Qdrant's payload indexing) for multiple filter combinations.

### 3. Relevance-Integrated Filtering (Soft Filtering)

Instead of binary "include/exclude" filtering, integrate metadata values directly into the retrieval scoring function.

-   **Mechanism**:
    -   Assign relevance scores or boosts based on metadata matches. For example, if a query is about `VF8`, chunks with `entity_name="VF 8"` receive a higher boost than those with `entity_type="car"` but no specific model.
    -   Use `retrieval_weight` (already present) more dynamically, adjusting it based on query context.
    -   Consider "decay" functions for temporal metadata (`published_at`, `fetched_at`), giving newer documents a slight advantage unless explicitly overridden.
-   **Benefits**: Allows for more nuanced ranking, prevents hard cut-offs that might exclude marginally relevant but important information.
-   **Implementation Considerations**: Requires a flexible scoring engine in the retrieval component that can combine lexical, dense, and metadata-based scores.

### 4. LLM-Assisted Filter Generation and Refinement

Utilize LLMs to infer appropriate metadata filters directly from natural language queries, especially for complex or ambiguous requests.

-   **Mechanism**:
    -   The LLM analyzes the user's query and suggests a set of metadata key-value pairs (e.g., `{"page_type": "policy", "language": "vi"}`).
    -   This can be used to augment or replace rule-based intent classification.
    -   For ambiguous queries, the LLM could even suggest clarifying questions that lead to better filter selection.
-   **Benefits**: Handles more complex and varied natural language queries, reduces reliance on rigid keyword matching for filters.
-   **Implementation Considerations**: Requires careful prompt engineering for the LLM, validation of generated filters, and potentially a feedback loop to refine the LLM's performance. Guardrails are crucial to prevent the LLM from inventing filters or misinterpreting intent.

### 5. Negative Filtering / Exclusion Lists

Explicitly define metadata values or patterns that should *never* be retrieved for certain query types or contexts.

-   **Mechanism**:
    -   Maintain a list of `is_noise=true` chunks (already present).
    -   Extend this to exclude specific `attribute_group` (e.g., "legal_disclaimers" for general product queries) or `page_type` (e.g., "404_page").
    -   This can be dynamic, for instance, excluding "out-of-stock" product pages unless the query explicitly asks about availability.
-   **Benefits**: Directly addresses noise reduction, improves precision by removing irrelevant content.
-   **Implementation Considerations**: Requires clear definitions of what constitutes "noise" or "exclusion-worthy" content, and efficient filtering mechanisms in the retrieval layer.

### 6. Contextual Filtering (User/Session-Aware)

Filter results based on external context such as the user's role, permissions, location, or current session state.

-   **Mechanism**:
    -   If the user is an "employee", include internal documents (`source_type="internal"`).
    -   If the user is in "Vietnam", prioritize `language="vi"` and `domain="vinfastauto.com/vn_vi"`.
    -   If the session is for a specific "product configuration", filter for chunks related to that configuration.
-   **Benefits**: Personalizes retrieval, ensures compliance with access controls, improves relevance for specific user segments.
-   **Implementation Considerations**: Requires integration with user management systems, session state, and a robust security model for access control.

## Impact on Latency and Relevance

These advanced filtering methods primarily aim to improve **relevance** by ensuring that the retrieved chunks are highly pertinent to the user's specific need. By focusing the search space, they can also indirectly improve **latency**:

-   **Reduced Search Space**: More precise filters mean the underlying vector database or lexical search engine has fewer documents/chunks to consider, speeding up initial retrieval.
-   **Fewer Reranking Candidates**: A more relevant initial set of candidates means the reranker has less noise to process, leading to faster reranking and better final ranking.
-   **Optimized LLM Context**: The LLM receives a cleaner, more focused context, reducing token usage, generation time, and the likelihood of hallucination from irrelevant information.

## Implementation Considerations

1.  **Metadata Quality**: The effectiveness of any filtering strategy hinges on the richness and accuracy of the metadata itself. Continuous improvement of URL ingestion's metadata extraction (e.g., `entity_type`, `product_specs`) is paramount.
2.  **Indexing**: Ensure that all metadata fields intended for filtering are properly indexed in the vector database (e.g., Qdrant payload indexing) for efficient querying.
3.  **Performance Overhead**: Dynamic and LLM-assisted filtering introduce their own computational overhead. This needs to be balanced against the gains in relevance and downstream efficiency.
4.  **Configurability**: Filtering logic should be configurable, allowing for easy adjustments of thresholds, boosts, and rule sets without code changes.
5.  **Evaluation**: Robust evaluation metrics are needed to measure the impact of different filtering strategies on precision, recall, and answer quality. This includes A/B testing and human judgment.

## Conclusion

Moving beyond simple pre- and post-filtering, adopting dynamic, hierarchical, relevance-integrated, and LLM-assisted metadata filtering techniques can significantly elevate the performance of the RAG system. These methods enable a more intelligent and context-aware retrieval process, directly contributing to higher quality, more trustworthy answers, and a more efficient overall pipeline. The foundation for these improvements lies in the continuous enhancement of metadata extraction during the ingestion phase.