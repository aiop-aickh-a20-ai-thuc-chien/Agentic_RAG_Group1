"""Convert metadata_field_guide.md -> metadata_field_guide.pdf (Vietnamese support)."""

import pathlib
import re

from fpdf import FPDF

FONT_DIR = pathlib.Path("C:/Windows/Fonts")
MD_FILE = pathlib.Path("scripts/analyze/metadata_field_guide.md")
OUT_FILE = pathlib.Path("scripts/analyze/metadata_field_guide.pdf")

# ---------------------------------------------------------------------------
# Parse markdown into structured blocks
# ---------------------------------------------------------------------------


def parse_md(text: str) -> list[dict]:
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # Heading
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            blocks.append({"type": f"h{len(m.group(1))}", "text": m.group(2).strip()})
            i += 1
            continue

        # HR
        if re.match(r"^-{3,}$", line.strip()):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            blocks.append({"type": "quote", "text": line[2:].strip()})
            i += 1
            continue

        # Code block
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({"type": "code", "text": "\n".join(code_lines)})
            i += 1
            continue

        # Table
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|", lines[i + 1]):
            rows = []
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(header)
            i += 2  # skip separator
            while i < len(lines) and "|" in lines[i]:
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row)
                i += 1
            blocks.append({"type": "table", "rows": rows})
            continue

        # Bullet
        if re.match(r"^[-*]\s+", line):
            blocks.append({"type": "bullet", "text": re.sub(r"^[-*]\s+", "", line)})
            i += 1
            continue

        # Paragraph
        if line.strip():
            blocks.append({"type": "para", "text": line.strip()})
        i += 1

    return blocks


_EMOJI_MAP = {
    "🔴": "[Cao]",
    "🟡": "[TB]",
    "🟢": "[Nho]",
    "✅": "[OK]",
    "❌": "[X]",
    "│": "|",
    "├": "+",
    "─": "-",
    "┬": "+",
    "┐": "+",
    "└": "+",
    "┘": "+",
    "┼": "+",
    "┴": "+",
    "▼": "v",
    "▸": ">",
    "∋": "in",
}


def _clean(text: str) -> str:
    for ch, repl in _EMOJI_MAP.items():
        text = text.replace(ch, repl)
    return text


def strip_inline(text: str) -> str:
    """Remove markdown inline markup: **bold**, *italic*, `code`."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return _clean(text)


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------


class MetaPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Segoe", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"Trang {self.page_no()}", align="C")

    # helpers
    def _normal(self, size=11):
        self.set_font("Segoe", size=size)
        self.set_text_color(34, 34, 34)

    def _bold(self, size=11):
        self.set_font("Segoe", style="B", size=size)
        self.set_text_color(34, 34, 34)


def build_pdf(blocks: list[dict]) -> FPDF:
    pdf = MetaPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_font("Segoe", fname=str(FONT_DIR / "segoeui.ttf"))
    pdf.add_font("Segoe", style="B", fname=str(FONT_DIR / "segoeuib.ttf"))

    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    W = pdf.w - 40  # usable width

    for block in blocks:
        t = block.get("type")

        if t == "h1":
            pdf.ln(4)
            pdf.set_font("Segoe", size=18)
            pdf.set_text_color(192, 57, 43)
            pdf.multi_cell(W, 9, strip_inline(block["text"]))
            pdf.set_draw_color(192, 57, 43)
            pdf.set_line_width(0.5)
            pdf.line(20, pdf.get_y(), 20 + W, pdf.get_y())
            pdf.ln(3)

        elif t == "h2":
            pdf.ln(5)
            pdf.set_font("Segoe", size=13)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(W, 7, strip_inline(block["text"]))
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y(), 20 + W, pdf.get_y())
            pdf.ln(2)

        elif t == "h3":
            pdf.ln(4)
            pdf.set_font("Segoe", size=11)
            pdf.set_text_color(41, 128, 185)
            pdf.multi_cell(W, 6, strip_inline(block["text"]))
            pdf.ln(1)

        elif t == "hr":
            pdf.ln(3)
            pdf.set_draw_color(220, 220, 220)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y(), 20 + W, pdf.get_y())
            pdf.ln(3)

        elif t == "quote":
            pdf.ln(2)
            pdf.set_fill_color(248, 249, 250)
            pdf.set_draw_color(231, 76, 60)
            pdf.set_line_width(0.8)
            pdf.line(20, pdf.get_y(), 20, pdf.get_y() + 8)
            pdf.set_x(25)
            pdf.set_font("Segoe", size=10)
            pdf.set_text_color(102, 102, 102)
            pdf.multi_cell(W - 5, 5.5, strip_inline(block["text"]))
            pdf.ln(1)

        elif t == "code":
            pdf.ln(2)
            code_text = block["text"]
            lines = code_text.split("\n")
            row_h = 4.8
            box_h = len(lines) * row_h + 6
            pdf.set_fill_color(244, 244, 244)
            pdf.rect(20, pdf.get_y(), W, box_h, style="F")
            pdf.set_draw_color(52, 152, 219)
            pdf.set_line_width(0.8)
            pdf.line(20, pdf.get_y(), 20, pdf.get_y() + box_h)
            pdf.set_xy(24, pdf.get_y() + 3)
            pdf.set_font("Segoe", size=9)
            pdf.set_text_color(44, 44, 44)
            for cl in lines:
                pdf.set_x(24)
                pdf.cell(W - 4, row_h, cl)
                pdf.ln(row_h)
            pdf.ln(3)

        elif t == "table":
            rows = block["rows"]
            if not rows:
                continue
            pdf.ln(3)
            from fpdf.table import FontFace

            head_style = FontFace(
                emphasis="BOLD",
                color=(255, 255, 255),
                fill_color=(44, 62, 80),
            )
            with pdf.table(
                borders_layout="MINIMAL",
                cell_fill_color=(248, 249, 250),
                cell_fill_mode="ROWS",
                line_height=6,
                text_align="LEFT",
                width=int(W),
            ) as table:
                # header
                hrow = table.row()
                for cell in rows[0]:
                    hrow.cell(strip_inline(cell), style=head_style)
                # data
                for data_row in rows[1:]:
                    drow = table.row()
                    for cell in data_row:
                        drow.cell(strip_inline(cell))
            pdf.ln(3)

        elif t == "bullet":
            pdf.set_font("Segoe", size=11)
            pdf.set_text_color(34, 34, 34)
            pdf.set_x(24)
            pdf.cell(4, 6, "•")
            pdf.set_x(28)
            pdf.multi_cell(W - 8, 6, strip_inline(block["text"]))

        elif t == "para":
            pdf.set_font("Segoe", size=11)
            pdf.set_text_color(34, 34, 34)
            pdf.multi_cell(W, 6, strip_inline(block["text"]))
            pdf.ln(1)

    return pdf


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
md_text = _clean(MD_FILE.read_text(encoding="utf-8"))
blocks = parse_md(md_text)
pdf = build_pdf(blocks)
pdf.output(str(OUT_FILE))
print(f"Saved: {OUT_FILE}  ({OUT_FILE.stat().st_size // 1024} KB,  {pdf.page} trang)")
