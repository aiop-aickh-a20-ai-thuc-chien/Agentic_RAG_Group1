"""Rule-based clarification detection and question building for the VinFast RAG agent.

This module is intentionally free of LangGraph imports so it can be unit-tested
independently.  The node itself lives in nodes.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain vocabulary
# ---------------------------------------------------------------------------

# Lower-case canonical names; display names are obtained via .upper() or
# a lookup table below.
VINFAST_MODELS: list[str] = [
    "vf3", "vf5", "vf6", "vf7", "vf8", "vf9",
    "vfe34", "vf e34", "vf34",
]

# Human-readable display names used in clarification messages.
_MODEL_DISPLAY: dict[str, str] = {
    "vf3": "VF3",
    "vf5": "VF5",
    "vf6": "VF6",
    "vf7": "VF7",
    "vf8": "VF8",
    "vf9": "VF9",
    "vfe34": "VFe34",
    "vf e34": "VFe34",
    "vf34": "VFe34",
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "price": [
        # English
        "price", "cost", "how much", "vnd", "million", "expensive", "cheap",
        # Vietnamese
        "giá", "bao nhiêu", "chi phí", "triệu", "tỷ", "đắt", "rẻ",
        "mua", "giá bán", "giá xe",
    ],
    "battery_range": [
        # English
        "battery", "range", "km", "distance", "mileage",
        # Vietnamese
        "pin", "tầm hoạt động", "quãng đường", "ắc quy", "bao xa",
        "chạy được", "đi được",
    ],
    "charging": [
        # English
        "charge", "charging", "fast charge", "charger",
        # Vietnamese
        "sạc", "nhanh", "thời gian sạc", "cổng sạc", "trạm sạc",
    ],
    "specs": [
        # English
        "spec", "specification", "motor", "dimension", "size", "weight",
        "horsepower", "torque", "acceleration",
        # Vietnamese
        "thông số", "động cơ", "kích thước", "cấu hình", "tốc độ",
        "khối lượng", "chiều dài", "chiều rộng",
    ],
    "warranty": [
        # English
        "warranty", "guarantee", "service",
        # Vietnamese
        "bảo hành", "bảo đảm", "bảo dưỡng", "dịch vụ",
    ],
    "comparison": [
        # English
        "compare", "comparison", "difference", "vs", "versus", "better",
        "worse", "between",
        # Vietnamese
        "so sánh", "khác nhau", "hơn", "tốt hơn", "thua", "giữa",
        "hay là", "hay không",
    ],
    "safety": [
        # English
        "safety", "adas", "airbag", "autonomous", "brake", "crash",
        # Vietnamese
        "an toàn", "túi khí", "phanh", "hỗ trợ lái", "tự lái",
        "va chạm", "đánh giá an toàn",
    ],
}

# Short phrases that signal a vague follow-up
_VAGUE_PHRASES: list[str] = [
    # English
    "is it good", "what about it", "tell me more", "details", "more info",
    # Vietnamese
    "thế nào", "như thế nào", "tốt không", "hay không", "được không",
    "kể thêm", "thêm thông tin", "cho biết thêm",
]

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def detect_entities(question: str) -> list[str]:
    """Return a list of VinFast model canonical names found in *question*.

    Matching is case-insensitive.  The returned list preserves the order in
    which models appear in the question.
    """
    q = question.lower()
    found: list[str] = []
    for model in VINFAST_MODELS:
        if model in q and model not in found:
            found.append(model)
    return found


def detect_intents(question: str) -> list[str]:
    """Return a list of intent labels found in *question*.

    Each intent appears at most once.  Order follows the INTENT_KEYWORDS
    definition order, not occurrence order.
    """
    q = question.lower()
    return [
        intent
        for intent, keywords in INTENT_KEYWORDS.items()
        if any(kw in q for kw in keywords)
    ]


# ---------------------------------------------------------------------------
# Clarification decision
# ---------------------------------------------------------------------------


def should_clarify(
    question: str,
    history: list[dict[str, str]],
) -> tuple[bool, str]:
    """Return *(needs_clarification, reason)*.

    *reason* is one of:
      - ``"entity_without_intent"``
      - ``"intent_without_entity"``
      - ``"comparison_missing_entities"``
      - ``"vague_question"``
      - ``""``  (no clarification needed)

    The function first checks whether the question is a clarification reply
    to a previous bot message; if so, it does **not** trigger clarification
    again (to avoid infinite loops).
    """
    # --- Guard: skip if the question was already resolved from history -----
    # If the last assistant message was a clarification question AND the
    # current question is a short reply, we let preprocess handle resolution
    # rather than triggering another clarification round.
    if _is_reply_to_clarification(question, history):
        return False, ""

    q = question.strip().lower()
    entities = detect_entities(q)
    intents = detect_intents(q)
    word_count = len(q.split())

    # Case 1: user typed only a model name ("vf3", "vf8 nào")
    if entities and not intents and word_count <= 4:
        return True, "entity_without_intent"

    # Case 2: user typed only an intent keyword ("price", "pin", "sạc")
    if intents and not entities and word_count <= 4:
        return True, "intent_without_entity"

    # Case 3: comparison without enough models
    if "comparison" in intents and len(entities) < 2:
        return True, "comparison_missing_entities"

    # Case 4: vague follow-up phrase without an entity
    if not entities and any(phrase in q for phrase in _VAGUE_PHRASES):
        return True, "vague_question"

    return False, ""


def _is_reply_to_clarification(
    question: str,
    history: list[dict[str, str]],
) -> bool:
    """Return True if the last assistant message was a clarification question.

    This prevents the node from re-triggering clarification on the user's
    reply turn.
    """
    # Find the most recent assistant message
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            # Heuristic: clarification questions contain these phrases
            clarification_markers = [
                "what would you like to know",
                "which vinfast model",
                "which model",
                "bạn muốn biết gì về",
                "bạn hỏi về model nào",
                "model nào",
                "you want to compare",
                "muốn so sánh",
                "could you clarify",
                "bạn có thể làm rõ",
            ]
            if any(marker in content for marker in clarification_markers):
                return True
            break  # Only check the most recent assistant message
    return False


# ---------------------------------------------------------------------------
# Clarification question builder
# ---------------------------------------------------------------------------


def build_clarification_question(
    reason: str,
    entities: list[str],
    intents: list[str],
) -> str:
    """Return a natural-language clarification question in Vietnamese.

    The chatbot's tone matches the rest of the agent: polite, informative,
    VinFast-specific.
    """
    display_models = ", ".join(_MODEL_DISPLAY.get(e, e.upper()) for e in entities)

    if reason == "entity_without_intent":
        model = _MODEL_DISPLAY.get(entities[0], entities[0].upper()) if entities else "mẫu xe đó"
        return (
            f"Bạn muốn biết gì về {model}? "
            "Mình có thể hỗ trợ về giá, pin/tầm xa, thông số, sạc, "
            "bảo hành, an toàn, hoặc so sánh với các mẫu khác."
        )

    if reason == "intent_without_entity":
        intent_map = {
            "price": "giá",
            "battery": "pin/tầm xa",
            "charging": "sạc",
            "specs": "thông số",
            "warranty": "bảo hành",
            "comparison": "so sánh",
            "safety": "an toàn",
        }
        intent_label = intent_map.get(intents[0], intents[0].replace("_", " ")) if intents else "vấn đề đó"
        return (
            f"Bạn đang hỏi về {intent_label} của mẫu xe VinFast nào? "
            "Ví dụ: VF3, VF5, VF6, VF7, VF8, hoặc VF9."
        )

    if reason == "comparison_missing_entities":
        if display_models:
            return (
                f"Bạn muốn so sánh {display_models} với mẫu xe nào? "
                "Ví dụ: VF3 vs VF5, hoặc VF8 vs VF9."
            )
        return (
            "Bạn muốn so sánh những mẫu xe VinFast nào với nhau? "
            "Ví dụ: VF3 vs VF5, hoặc VF8 vs VF9."
        )

    if reason == "vague_question":
        return (
            "Bạn có thể nói rõ hơn muốn biết điều gì không? "
            "Bạn có thể hỏi về giá, thông số, pin/tầm xa, sạc, "
            "bảo hành, an toàn, hoặc so sánh cho một mẫu xe VinFast cụ thể."
        )

    # Fallback
    return (
        "Bạn có thể nói rõ hơn câu hỏi được không? "
        "Vui lòng cho biết mẫu xe VinFast (ví dụ: VF3, VF8) và thông tin bạn cần."
    )


# ---------------------------------------------------------------------------
# Pending-clarification builder
# ---------------------------------------------------------------------------


def build_pending_clarification(
    reason: str,
    entities: list[str],
    intents: list[str],
) -> dict[str, str] | None:
    """Encode the missing-slot context for the next turn's resolution.

    Returns ``None`` when there is nothing actionable to store.
    """
    if reason == "entity_without_intent" and entities:
        return {"entity": _MODEL_DISPLAY.get(entities[0], entities[0].upper()), "missing": "intent"}

    if reason == "intent_without_entity" and intents:
        return {"intent": intents[0], "missing": "entity"}

    if reason == "comparison_missing_entities" and entities:
        return {
            "entity": _MODEL_DISPLAY.get(entities[0], entities[0].upper()),
            "missing": "comparison_model",
        }

    return None


# ---------------------------------------------------------------------------
# Reply resolution
# ---------------------------------------------------------------------------


def resolve_clarification_reply(
    new_question: str,
    history: list[dict[str, str]],
) -> str | None:
    """Attempt to resolve a short reply using the pending-clarification context
    stored in the conversation history.

    Returns a fully-formed query string when resolution succeeds, or ``None``
    when the question should be processed as-is (letting the LLM handle it).

    This is a rule-based best-effort resolver.  The LLM-based ``preprocess_query``
    in grading.py is the primary resolver; this runs first as a cheap fast-path.
    """
    # Only attempt resolution for short replies
    if len(new_question.strip().split()) > 6:
        return None

    # Recover pending context from the most recent assistant clarification message
    pending = _extract_pending_from_history(history)
    if not pending:
        return None

    new_entities = detect_entities(new_question)
    new_intents = detect_intents(new_question)

    missing = pending.get("missing")

    # Previous turn had model, reply provides intent → "What is the <intent> of <model>?"
    if missing == "intent" and pending.get("entity") and new_intents:
        intent_label = new_intents[0].replace("_", " ")
        model = pending["entity"]
        return f"What is the {intent_label} of {model}?"

    # Previous turn had intent, reply provides model → "What is the <intent> of <model>?"
    if missing == "entity" and pending.get("intent") and new_entities:
        intent_label = pending["intent"].replace("_", " ")
        model = _MODEL_DISPLAY.get(new_entities[0], new_entities[0].upper())
        return f"What is the {intent_label} of {model}?"

    # Comparison: we have one model, reply provides the second
    if missing == "comparison_model" and pending.get("entity") and new_entities:
        model1 = pending["entity"]
        model2 = _MODEL_DISPLAY.get(new_entities[0], new_entities[0].upper())
        return f"Compare {model1} and {model2}"

    return None


def _extract_pending_from_history(
    history: list[dict[str, str]],
) -> dict[str, str] | None:
    """Parse the last assistant clarification message to infer what was pending."""
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "").lower()

        # Detect entity_without_intent pattern
        if "what would you like to know about" in content:
            for model_key, model_display in _MODEL_DISPLAY.items():
                if model_key in content or model_display.lower() in content:
                    return {"entity": model_display, "missing": "intent"}

        # Detect intent_without_entity pattern
        if "which vinfast model are you asking about for" in content:
            for intent in INTENT_KEYWORDS:
                if intent.replace("_", " ") in content:
                    return {"intent": intent, "missing": "entity"}

        # Detect comparison_missing_entities pattern
        if "which model would you like to compare" in content or "which vinfast models would you like to compare" in content:
            for model_key, model_display in _MODEL_DISPLAY.items():
                if model_key in content or model_display.lower() in content:
                    return {"entity": model_display, "missing": "comparison_model"}

        break  # Only inspect the most recent assistant message
    return None
