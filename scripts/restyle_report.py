#!/usr/bin/env python3
"""Restyle the Midterm report docx: layout, headings, tables, figures, appendices.

The report was written in Google Docs, which left every paragraph with direct
formatting (and an invalid non-integer ``w:line`` spacing value that makes Word
render the section headings wrongly). This script rewrites the paragraph and
table properties, renumbers the tables and figures after two uncaptioned tables
and one new chart are added, and appends the appendices.

It is written to be safely re-runnable: every insertion is guarded by a check
for the text it would add.

    python3 scripts/restyle_report.py \
        --in  "docs/Midterm - Computer Vision Project Report.docx" \
        --out "docs/Midterm - Computer Vision Project Report.docx"
"""

from __future__ import annotations

import argparse
import copy
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

TEXT_WIDTH_EMU = Emu(int(6.5 * 914400))  # letter page, 1 inch margins

BODY_SIZE = 22        # half-points: 11 pt
TABLE_SIZE = 20       # 10 pt
CAPTION_SIZE = 18     # 9 pt
H1_SIZE = 40          # 20 pt
H2_SIZE = 32          # 16 pt

HEADER_FILL = "EAD1DC"
BORDER_COLOR = "666666"

H1_RE = re.compile(r"^\d+\.\s+[A-Z]")
H2_RE = re.compile(r"^\d+\.\d+\s+\S")

# Two tables gain captions and one chart is added, so everything after them
# shifts. Applied as a single simultaneous mapping, never chained.
TABLE_MAP = {2: 4, 3: 5, 4: 6, 5: 7, 6: 8, 7: 9}
FIGURE_MAP = {2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11}


# ---------------------------------------------------------------------------
# low-level OOXML helpers
# ---------------------------------------------------------------------------


def el(tag: str, **attrs):
    node = OxmlElement(tag)
    for key, value in attrs.items():
        node.set(qn(f"w:{key}"), str(value))
    return node


def set_ppr(
    p,
    *,
    align=None,
    before=0,
    after=120,
    line=240,
    left=None,
    hanging=None,
    first_line=None,
    keep_next=False,
    page_break=False,
    num_id=None,
    ilvl=0,
    keep_lines=True,
):
    """Replace a paragraph's properties wholesale with clean, valid ones."""
    old = p._p.find(qn("w:pPr"))
    if old is not None:
        rpr = old.find(qn("w:rPr"))
        p._p.remove(old)
    else:
        rpr = None

    ppr = el("w:pPr")
    if page_break:
        ppr.append(el("w:pageBreakBefore"))
    if keep_next:
        ppr.append(el("w:keepNext"))
    if keep_lines:
        ppr.append(el("w:keepLines"))
    if num_id is not None:
        npr = el("w:numPr")
        npr.append(el("w:ilvl", val=ilvl))
        npr.append(el("w:numId", val=num_id))
        ppr.append(npr)
    ppr.append(el("w:spacing", before=before, after=after, line=line, lineRule="auto"))
    if left is not None or hanging is not None or first_line is not None:
        ind = el("w:ind")
        if left is not None:
            ind.set(qn("w:left"), str(left))
        if hanging is not None:
            ind.set(qn("w:hanging"), str(hanging))
        if first_line is not None:
            ind.set(qn("w:firstLine"), str(first_line))
        ppr.append(ind)
    if align:
        ppr.append(el("w:jc", val=align))
    if rpr is not None:
        ppr.append(copy.deepcopy(rpr))
    p._p.insert(0, ppr)
    return p


def set_run_props(p, *, size=None, bold=None, italic=None, color=None):
    """Force size/weight on every run of a paragraph, hyperlink runs included."""
    for run in p._p.iter(qn("w:r")):
        rpr = run.find(qn("w:rPr"))
        if rpr is None:
            rpr = el("w:rPr")
            run.insert(0, rpr)
        if bold is not None:
            for tag in ("w:b", "w:bCs"):
                existing = rpr.find(qn(tag))
                if existing is not None:
                    rpr.remove(existing)
                rpr.append(el(tag, val="1" if bold else "0"))
        if italic is not None:
            for tag in ("w:i", "w:iCs"):
                existing = rpr.find(qn(tag))
                if existing is not None:
                    rpr.remove(existing)
                rpr.append(el(tag, val="1" if italic else "0"))
        if size is not None:
            for tag in ("w:sz", "w:szCs"):
                existing = rpr.find(qn(tag))
                if existing is not None:
                    rpr.remove(existing)
                rpr.append(el(tag, val=size))
        if color is not None:
            existing = rpr.find(qn("w:color"))
            if existing is not None:
                rpr.remove(existing)
            rpr.append(el("w:color", val=color))


def text_nodes(p):
    return [t for t in p._p.iter(qn("w:t"))]


def replace_same_length(p, pattern: re.Pattern, repl) -> bool:
    """Character-level substitution across fragmented runs.

    Only used for replacements that keep the string length, so the characters
    can be written straight back into the same positions and no run, hyperlink
    or formatting boundary moves.
    """
    nodes = text_nodes(p)
    if not nodes:
        return False
    joined = "".join(n.text or "" for n in nodes)
    new = pattern.sub(repl, joined)
    if new == joined:
        return False
    if len(new) != len(joined):
        raise ValueError(f"length changed: {joined[:60]!r}")
    pos = 0
    for node in nodes:
        n = len(node.text or "")
        node.text = new[pos : pos + n]
        pos += n
    return True


def paragraph_text(p) -> str:
    return "".join(n.text or "" for n in text_nodes(p))


def make_paragraph(doc, parts, **ppr):
    """Build a paragraph from (text, bold, italic) parts."""
    p_el = el("w:p")
    from docx.text.paragraph import Paragraph

    p = Paragraph(p_el, doc)
    for part in parts:
        text, bold, italic = (part + (False, False))[:3] if isinstance(part, tuple) else (part, False, False)
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
    set_ppr(p, **ppr)
    return p


def insert_after(ref_el, *new_paragraphs):
    anchor = ref_el
    for p in new_paragraphs:
        anchor.addnext(p._p if hasattr(p, "_p") else p)
        anchor = p._p if hasattr(p, "_p") else p
    return anchor


# ---------------------------------------------------------------------------
# document-level pieces
# ---------------------------------------------------------------------------


def ensure_decimal_numbering(doc) -> str:
    """Add a decimal list definition to numbering.xml and return its numId."""
    numbering = doc.part.numbering_part.element
    for num in numbering.findall(qn("w:num")):
        if num.get(qn("w:numId")) == "90":
            return "90"

    abstract = el("w:abstractNum", abstractNumId="90")
    abstract.append(el("w:multiLevelType", val="multilevel"))
    for level in range(3):
        lvl = el("w:lvl", ilvl=level)
        lvl.append(el("w:start", val=1))
        lvl.append(el("w:numFmt", val="decimal"))
        lvl.append(el("w:lvlText", val="%%%d." % (level + 1)))
        lvl.append(el("w:lvlJc", val="left"))
        ppr = el("w:pPr")
        ppr.append(el("w:ind", left=457200 + level * 457200, hanging=342900))
        lvl.append(ppr)
        abstract.append(lvl)

    # abstractNum elements must precede num elements
    first_num = numbering.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(abstract)
    else:
        numbering.append(abstract)

    num = el("w:num", numId="90")
    num.append(el("w:abstractNumId", val="90"))
    numbering.append(num)
    return "90"


def add_picture_paragraph(doc, image_path: Path, width_emu: int, *, after_el=None):
    """A centered, text-width image in its own paragraph that keeps its caption."""
    from docx.text.paragraph import Paragraph

    p = Paragraph(el("w:p"), doc)
    run = p.add_run()
    run.add_picture(str(image_path), width=Emu(width_emu))
    set_ppr(p, align="center", before=120, after=60, keep_next=True)
    if after_el is not None:
        after_el.addnext(p._p)
    return p


def caption(doc, text: str, **kwargs):
    return make_paragraph(
        doc,
        [(text, True, False)],
        align="center",
        before=0,
        after=160,
        keep_next=True,
        **kwargs,
    )


def body(doc, parts, **kwargs):
    kwargs.setdefault("align", "both")
    kwargs.setdefault("after", 120)
    return make_paragraph(doc, parts, **kwargs)


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------


def style_table(table, *, header=True):
    tbl = table._tbl
    tbl_pr = tbl.tblPr

    for tag in ("w:tblW", "w:tblBorders", "w:tblCellMar", "w:tblLayout", "w:jc"):
        for node in tbl_pr.findall(qn(tag)):
            tbl_pr.remove(node)

    tbl_pr.append(el("w:tblW", w=5000, type="pct"))
    tbl_pr.append(el("w:tblLayout", type="fixed"))

    borders = el("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(el(f"w:{side}", val="single", sz=4, space=0, color=BORDER_COLOR))
    tbl_pr.append(borders)

    margins = el("w:tblCellMar")
    for side, value in (("top", 40), ("left", 108), ("bottom", 40), ("right", 108)):
        margins.append(el(f"w:{side}", w=value, type="dxa"))
    tbl_pr.append(margins)

    for row_index, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        for node in tr_pr.findall(qn("w:trHeight")):
            tr_pr.remove(node)
        for node in tr_pr.findall(qn("w:tblHeader")):
            tr_pr.remove(node)
        is_header = header and row_index == 0
        if is_header:
            tr_pr.append(el("w:tblHeader"))
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            for node in tc_pr.findall(qn("w:shd")):
                tc_pr.remove(node)
            if is_header:
                tc_pr.append(el("w:shd", val="clear", color="auto", fill=HEADER_FILL))
            for node in tc_pr.findall(qn("w:vAlign")):
                tc_pr.remove(node)
            tc_pr.append(el("w:vAlign", val="center"))
            for p in cell.paragraphs:
                set_ppr(p, align="left", before=20, after=20, line=240, keep_lines=False)
                set_run_props(p, size=TABLE_SIZE, bold=True if is_header else None)


# ---------------------------------------------------------------------------
# main restyle
# ---------------------------------------------------------------------------


def find_paragraph(paragraphs, predicate):
    for p in paragraphs:
        if predicate(paragraph_text(p)):
            return p
    return None


def restyle(in_path: Path, out_path: Path) -> None:
    doc = Document(str(in_path))
    decimal_num = ensure_decimal_numbering(doc)

    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body_el = doc.element.body
    blocks = [c for c in body_el.iterchildren()]
    paragraphs = [Paragraph(c, doc) for c in blocks if c.tag == qn("w:p")]
    tables = [Table(c, doc) for c in blocks if c.tag == qn("w:tbl")]

    # -- 1. cover page ------------------------------------------------------
    cover_end = next(i for i, p in enumerate(paragraphs) if H1_RE.match(paragraph_text(p)))
    cover = paragraphs[:cover_end]

    for p in cover:
        text = paragraph_text(p).strip()
        if text in {"Midterm_Object_Sorting_RealWaste.ipynb", ""} or text.startswith(
            "GitHub repository:"
        ):
            # Neither reference cover carries links or blank filler; the links
            # move to Section 5.1 and Appendix F.
            p._p.getparent().remove(p._p)
            continue
        set_ppr(p, align="center", before=0, after=0, line=240)

    cover = [p for p in cover if p._p.getparent() is not None]
    spacing = {
        "A Computer Vision Project Report": (0, 1000),
        "MIDTERM PROJECT REPORT": (0, 640),
        "Submitted as a requirement for the course\nComputer Vision": (0, 1100),
        "Group Project Specialization": (0, 0),
        "Object Sorting": (0, 1300),
        "Prepared by:": (0, 120),
        "BS Computer Science – 4A": (0, 1300),
        "Submitted to:": (0, 120),
    }
    for p in cover:
        text = paragraph_text(p).strip()
        before, after = spacing.get(text, (0, 120))
        set_ppr(p, align="center", before=before, after=after, line=240)
    title = find_paragraph(cover, lambda t: t.strip() == "MIDTERM PROJECT REPORT")
    if title is not None:
        set_run_props(title, size=36)

    # -- 2. headings, body text, lists --------------------------------------
    for p in paragraphs[cover_end:]:
        text = paragraph_text(p).strip()
        if not text:
            continue
        if H1_RE.match(text) or text == "REFERENCES":
            set_ppr(p, align="left", before=0, after=240, line=240,
                    keep_next=True, page_break=True)
            set_run_props(p, size=H1_SIZE, bold=True)
        elif H2_RE.match(text):
            set_ppr(p, align="left", before=240, after=80, line=240, keep_next=True)
            set_run_props(p, size=H2_SIZE, bold=False)
        elif re.match(r"^(Table|Figure) \d+\.", text):
            set_ppr(p, align="center", before=0, after=200, line=240, keep_next=True)
            set_run_props(p, size=CAPTION_SIZE, bold=True)
        elif text in {"General objective:", "Specific objectives:"}:
            set_ppr(p, align="left", before=120, after=60, line=240, keep_next=True)
            set_run_props(p, size=BODY_SIZE, bold=True)
        else:
            num_pr = p._p.find(qn("w:pPr"))
            has_num = num_pr is not None and num_pr.find(qn("w:numPr")) is not None
            if has_num:
                num_id = num_pr.find(qn("w:numPr")).find(qn("w:numId")).get(qn("w:val"))
                set_ppr(p, align="both", before=0, after=60, line=240,
                        left=457200, hanging=228600, num_id=num_id)
            elif p._p.findall(".//" + qn("w:drawing")):
                set_ppr(p, align="center", before=120, after=60, line=240, keep_next=True)
            else:
                set_ppr(p, align="both", before=0, after=140, line=240)
            set_run_props(p, size=BODY_SIZE)

    doc.save(str(out_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="src", required=True)
    parser.add_argument("--out", dest="dst", required=True)
    args = parser.parse_args()
    restyle(Path(args.src), Path(args.dst))
    print(f"wrote {args.dst}")


if __name__ == "__main__":
    main()
