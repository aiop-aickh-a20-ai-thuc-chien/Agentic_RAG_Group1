"""[1] EXTRACT — open triple extraction (free-form predicate + type) per chunk.

This is the "mở" step. The LLM emits raw triples in the document's own wording;
NO normalization happens here (that is stage [3]'s job). `gleanings` is the
GraphRAG multi-pass recall trick: ask the model whether it missed anything and
merge the new triples. With the mock it is a no-op; with a real LLM it raises recall.
"""

from __future__ import annotations

import json

from kg.llm import LLMClient
from kg.schema import Chunk, OpenTriple

EXTRACT_SYSTEM = (
    "Bạn là bộ trích xuất tri thức cho hệ thống RAG tiếng Việt. "
    "Chỉ trả về JSON đúng schema, không giải thích."
)


def _main_entity_hint(chunk: Chunk) -> str:
    """Best guess at the entity the chunk is about — used to anchor spec/attribute lines."""
    if chunk.heading:
        return chunk.heading
    for line in chunk.text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s
    return ""


def build_extract_prompt(chunk: Chunk, prior: list[OpenTriple] | None = None) -> str:
    payload = {"chunk_id": chunk.chunk_id}
    hint = _main_entity_hint(chunk)
    glean = ""
    if prior:
        glean = (
            "\n<gleaning>Một số quan hệ CÓ THỂ đã bị bỏ sót ở lần trước. "
            "Hãy bổ sung các quan hệ còn thiếu (đừng lặp lại cái đã có).</gleaning>"
        )
    return f"""[[KG_TASK=extract]]
<task>
Trích xuất bộ ba (subject, predicate, object) MỞ từ đoạn dưới đây.

QUY TẮC:
1. CHỦ THỂ (subject) của các dòng thông số/đặc điểm/giá phải là THỰC THỂ CHÍNH mà đoạn
   mô tả (xem gợi ý bên dưới hoặc tiêu đề/câu đầu) — TUYỆT ĐỐI KHÔNG lấy tên thuộc tính
   làm chủ thể. Vd "Minio Green ... Công suất tối đa 30 kW. Tốc độ tối đa 80 km/h":
     ĐÚNG → (Minio Green, công suất tối đa, 30 kW) ; (Minio Green, tốc độ tối đa, 80 km/h)
     SAI  → (Công suất tối đa, ..., 30 kW)
2. predicate = tên quan hệ/thuộc tính, GIỮ NGUYÊN cách diễn đạt tài liệu (không tự chuẩn hoá).
3. object = giá trị/đối tượng NGẮN GỌN (số + đơn vị, tên riêng). KHÔNG đưa cả câu dài làm object.
4. BỎ QUA khẩu hiệu/marketing chung chung không có giá trị cụ thể
   (vd "mang trong mình tinh thần đổi mới", "biểu tượng của sự mạnh mẽ").
5. subject_type/object_type: đoán tự do (product, org, spec, value, feature, price, location...).
6. evidence: trích NGUYÊN VĂN cụm chứa quan hệ (PHẢI nằm trong đoạn). Cấm suy diễn.
</task>{glean}
<entity_chinh>{hint}</entity_chinh>
<context>heading: {chunk.heading or ""} | section: {" > ".join(chunk.section_path)}</context>
<content>{chunk.text}</content>
Trả JSON list các object {{"subject","predicate","object","subject_type","object_type","evidence"}}.
[[PAYLOAD]]{json.dumps(payload, ensure_ascii=False)}[[/PAYLOAD]]"""


def parse_triples(text: str) -> list[OpenTriple]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[OpenTriple] = []
    if not isinstance(data, list):
        return out
    for d in data:
        if not isinstance(d, dict):
            continue
        if d.get("subject") and d.get("predicate") and d.get("object"):
            out.append(
                OpenTriple(
                    subject=str(d["subject"]).strip(),
                    predicate=str(d["predicate"]).strip(),
                    object=str(d["object"]).strip(),
                    subject_type=str(d.get("subject_type", "")).strip(),
                    object_type=str(d.get("object_type", "")).strip(),
                    evidence=str(d.get("evidence", "")).strip(),
                )
            )
    return out


def extract_chunk(chunk: Chunk, llm: LLMClient, gleanings: int = 1) -> list[OpenTriple]:
    triples = parse_triples(llm.complete(build_extract_prompt(chunk), EXTRACT_SYSTEM))

    seen = {(t.subject, t.predicate, t.object) for t in triples}
    for _ in range(max(0, gleanings)):
        more = parse_triples(
            llm.complete(build_extract_prompt(chunk, prior=triples), EXTRACT_SYSTEM)
        )
        added = 0
        for t in more:
            key = (t.subject, t.predicate, t.object)
            if key not in seen:
                seen.add(key)
                triples.append(t)
                added += 1
        if added == 0:
            break
    return triples
