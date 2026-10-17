#!/usr/bin/env python3
"""Restyle the Midterm report docx: layout, headings, tables, figures, appendices.

The report was written in Google Docs, which left every paragraph with direct
formatting (and an invalid non-integer ``w:line`` spacing value that makes Word
render the section headings wrongly). This script rewrites the paragraph and
table properties, renumbers the tables and figures after two uncaptioned tables
and one new chart are added, and appends the appendices.

This is a one-shot migration, not a formatter: the renumbering pass assumes the
original numbering, so it must run against the docx as it stood before the
restyle (commit a65b549). It refuses to run on its own output.

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
# A code identifier or URL this long cannot be broken across lines, and
# justifying the line before it stretches the spaces visibly. Those paragraphs
# are set flush left instead.
LONG_TOKEN = re.compile(r"\S{16,}")
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
    keep_lines=False,
):
    """Replace a paragraph's properties wholesale with clean, valid ones."""
    old = p._p.find(qn("w:pPr"))
    if old is not None:
        rpr = old.find(qn("w:rPr"))
        p._p.remove(old)
    else:
        rpr = None

    ppr = el("w:pPr")
    if keep_next:
        ppr.append(el("w:keepNext"))
    if keep_lines:
        ppr.append(el("w:keepLines"))
    if page_break:
        ppr.append(el("w:pageBreakBefore"))
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


# One decimal list definition, instantiated once per list so each restarts at 1.
NUM_IDS = {"objectives": "90", "workflow": "91", "preprocessing": "92"}


def ensure_decimal_numbering(doc) -> dict:
    """Add a decimal list definition to numbering.xml; one numId per list."""
    numbering = doc.part.numbering_part.element
    if any(num.get(qn("w:numId")) == "90" for num in numbering.findall(qn("w:num"))):
        return NUM_IDS

    abstract = el("w:abstractNum", abstractNumId="90")
    abstract.append(el("w:multiLevelType", val="multilevel"))
    for level in range(3):
        lvl = el("w:lvl", ilvl=level)
        lvl.append(el("w:start", val=1))
        lvl.append(el("w:numFmt", val="decimal"))
        lvl.append(el("w:lvlText", val="%%%d." % (level + 1)))
        lvl.append(el("w:lvlJc", val="left"))
        ppr = el("w:pPr")
        ppr.append(el("w:ind", left=720 + level * 720, hanging=360))
        lvl.append(ppr)
        abstract.append(lvl)

    # abstractNum elements must precede num elements
    first_num = numbering.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(abstract)
    else:
        numbering.append(abstract)

    for num_id in NUM_IDS.values():
        num = el("w:num", numId=num_id)
        num.append(el("w:abstractNumId", val="90"))
        override = el("w:lvlOverride", ilvl=0)
        override.append(el("w:startOverride", val=1))
        num.append(override)
        numbering.append(num)
    return NUM_IDS


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
        keep_lines=True,
        **kwargs,
    )


def justification(text: str) -> str:
    return "left" if LONG_TOKEN.search(text) else "both"


def body(doc, parts, **kwargs):
    joined = "".join(part[0] if isinstance(part, tuple) else part for part in parts)
    kwargs.setdefault("align", justification(joined))
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

    # a short table stays whole, with its caption; a long one may break, but
    # its header repeats and its last row still travels with the caption
    keep_whole = len(table.rows) <= 10
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
            # the last row keeps with the caption that follows the table
            last_row = keep_whole or row_index == len(table.rows) - 1
            for p in cell.paragraphs:
                nodes = [n for n in p._p.iter(qn("w:t"))]
                if nodes:          # Google Docs left stray padding in some cells
                    nodes[0].text = (nodes[0].text or "").lstrip()
                    nodes[-1].text = (nodes[-1].text or "").rstrip()
                set_ppr(p, align="left", before=20, after=20, line=240,
                        keep_next=last_row, keep_lines=True)
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
    if any(p.text.strip() == "APPENDICES" for p in doc.paragraphs):
        raise SystemExit(
            f"{in_path} has already been restyled. Run this against the original "
            "Google Docs export (the docx at commit a65b549) instead."
        )
    num_ids = ensure_decimal_numbering(doc)

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
    # Vertical rhythm of the cover, in twips, keyed by the start of each line.
    # The whole block must fit on page 1, which it did not before.
    spacing = [
        ("A Computer Vision Project Report", 1250, 1250),
        ("MIDTERM PROJECT REPORT", 0, 950),
        ("Submitted as a requirement", 0, 1350),
        ("Group Project Specialization", 0, 0),
        ("Object Sorting", 0, 1500),
        ("Prepared by:", 0, 160),
        ("Alba, John Raymond S.", 0, 260),
        ("BS Computer Science", 0, 1500),
        ("Submitted to:", 0, 160),
    ]
    for p in cover:
        text = paragraph_text(p).strip()
        before, after = 0, 120
        for prefix, b, a in spacing:
            if text.startswith(prefix):
                before, after = b, a
                break
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
                    keep_next=True, keep_lines=True, page_break=True)
            set_run_props(p, size=H1_SIZE, bold=True)
        elif H2_RE.match(text):
            set_ppr(p, align="left", before=240, after=80, line=240,
                    keep_next=True, keep_lines=True)
            set_run_props(p, size=H2_SIZE, bold=False)
        elif re.match(r"^(Table|Figure) \d+\.", text):
            set_ppr(p, align="center", before=0, after=200, line=240,
                    keep_next=True, keep_lines=True)
            set_run_props(p, size=CAPTION_SIZE, bold=True)
        elif text in {"General objective:", "Specific objectives:"}:
            set_ppr(p, align="left", before=120, after=60, line=240, keep_next=True)
            set_run_props(p, size=BODY_SIZE, bold=True)
        else:
            num_pr = p._p.find(qn("w:pPr"))
            has_num = num_pr is not None and num_pr.find(qn("w:numPr")) is not None
            if has_num:
                num_id = num_pr.find(qn("w:numPr")).find(qn("w:numId")).get(qn("w:val"))
                set_ppr(p, align=justification(text), before=0, after=60, line=240,
                        left=720, hanging=360, num_id=num_id)
            elif p._p.findall(".//" + qn("w:drawing")):
                set_ppr(p, align="center", before=120, after=60, line=240, keep_next=True)
            else:
                set_ppr(p, align=justification(text), before=0, after=140, line=240)
            set_run_props(p, size=BODY_SIZE)

    # -- 3. renumber the in-text table and figure references ---------------
    # Two uncaptioned tables gain captions and one chart is added, so the
    # numbering shifts. Every replacement keeps the same string length, so the
    # characters go straight back into the runs they came from.
    table_ref = re.compile(r"\bTable (\d+)\b")
    figure_ref = re.compile(r"\bFigure (\d+)\b")
    for p in paragraphs[cover_end:]:
        text = paragraph_text(p)
        if re.match(r"^\s*(Table|Figure) \d+\.", text):
            continue  # captions are rewritten below, not patched
        replace_same_length(p, table_ref,
                            lambda m: f"Table {TABLE_MAP.get(int(m.group(1)), int(m.group(1)))}")
        replace_same_length(p, figure_ref,
                            lambda m: f"Figure {FIGURE_MAP.get(int(m.group(1)), int(m.group(1)))}")
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    replace_same_length(p, table_ref,
                                        lambda m: f"Table {TABLE_MAP.get(int(m.group(1)), int(m.group(1)))}")

    # -- 4. rewrite the captions with their new numbers --------------------
    def set_text(p, parts):
        for child in list(p._p):
            if child.tag != qn("w:pPr"):
                p._p.remove(child)
        for part in parts:
            text, bold, italic = (part if isinstance(part, tuple) else (part, False, False))
            run = p.add_run(text)
            run.bold = bold
            run.italic = italic

    for p in paragraphs[cover_end:]:
        text = paragraph_text(p).strip()
        m = re.match(r"^(Table|Figure) (\d+)\.(.*)$", text, re.S)
        if not m:
            continue
        kind, number, rest = m.group(1), int(m.group(2)), m.group(3)
        mapping = TABLE_MAP if kind == "Table" else FIGURE_MAP
        set_text(p, [(f"{kind} {mapping.get(number, number)}.{rest}", True, False)])
        set_run_props(p, size=CAPTION_SIZE, bold=True)

    # -- 5. caption the two tables that had none ---------------------------
    def table_after(heading_text):
        """The first table following the given heading."""
        node = find_paragraph(paragraphs, lambda t: t.strip().startswith(heading_text))._p
        while node is not None:
            node = node.getnext()
            if node is not None and node.tag == qn("w:tbl"):
                return node
        return None

    existing = {paragraph_text(p).strip() for p in paragraphs}
    hardware_tbl = table_after("2.3 Hardware Components")
    software_tbl = table_after("2.4 Software and Development Tools")

    new_captions = [
        (hardware_tbl,
         "Table 2. Hardware used by the Computer Vision prototype.",
         "The prototype runs on ordinary equipment. One laptop or PC does the "
         "preprocessing and inference for every connected camera, and the phones listed "
         "as remote camera clients only capture and send pictures."),
        (software_tbl,
         "Table 3. Software and development tools, with the versions used.",
         "These are the versions used for the training run and the demonstration "
         "reported here. One row is not software: the RealWaste dataset is listed with "
         "its DOI and license because the whole pipeline depends on it."),
    ]
    for anchor, cap_text, note in new_captions:
        if anchor is None or cap_text in existing:
            continue
        cap = caption(doc, cap_text)
        note_p = body(doc, [note])
        insert_after(anchor, cap, note_p)

    # -- 6. figures: real architecture diagram, text-width sizing ----------
    def figure_paragraph_before(caption_prefix):
        cap = find_paragraph(paragraphs, lambda t: t.strip().startswith(caption_prefix))
        if cap is None:
            return None
        node = cap._p.getprevious()
        while node is not None:
            if node.tag == qn("w:p") and node.findall(".//" + qn("w:drawing")):
                return Paragraph(node, doc)
            node = node.getprevious()
        return None

    arch_p = figure_paragraph_before("Figure 1.")
    arch_png = ROOT / "docs" / "images" / "system-architecture.png"
    if arch_p is not None and arch_png.exists():
        for child in list(arch_p._p):
            if child.tag != qn("w:pPr"):
                arch_p._p.remove(child)
        arch_p.add_run().add_picture(str(arch_png), width=TEXT_WIDTH_EMU)
        set_ppr(arch_p, align="center", before=120, after=60, keep_next=True)

    # -- 7. the dataset distribution chart, generated by the notebook ------
    dist_png = ROOT / "results" / "dataset_distribution.png"
    dist_caption = "Figure 2. Images per class in the selected RealWaste subset, split into training, validation and testing sets."
    anchor = find_paragraph(
        paragraphs, lambda t: t.startswith("The selected 5-class subset is imbalanced")
    )
    if anchor is not None and dist_png.exists() and dist_caption not in {
        paragraph_text(p).strip() for p in paragraphs
    }:
        pic = Paragraph(el("w:p"), doc)
        pic.add_run().add_picture(str(dist_png), width=TEXT_WIDTH_EMU)
        set_ppr(pic, align="center", before=120, after=60, keep_next=True)
        cap = caption(doc, dist_caption)
        note = body(doc, [
            "Plastic is the largest class with 921 images and Glass the smallest with 420, "
            "about 2.2 times fewer. The stratified split keeps that same proportion inside "
            "each of the three sets, so the imbalance is spread evenly across training, "
            "validation and testing rather than concentrated in one of them."
        ])
        insert_after(anchor._p, pic, cap, note)

    # every remaining figure is scaled to the text width, capped so that the
    # figure and its caption still fit on one page
    from PIL import Image as _Image

    for p in [Paragraph(c, doc) for c in body_el.iterchildren() if c.tag == qn("w:p")]:
        blips = p._p.findall(".//" + qn("a:blip"))
        if not blips:
            continue
        for shape in p._p.findall(".//" + qn("wp:inline")) + p._p.findall(
            ".//" + qn("wp:anchor")
        ):
            extent = shape.find(qn("wp:extent"))
            if extent is None:
                continue
            cx, cy = int(extent.get("cx")), int(extent.get("cy"))
            scale = TEXT_WIDTH_EMU / cx
            new_cx, new_cy = TEXT_WIDTH_EMU, int(cy * scale)
            max_cy = int(7.1 * 914400)
            if new_cy > max_cy:
                new_cx = int(new_cx * max_cy / new_cy)
                new_cy = max_cy
            extent.set("cx", str(int(new_cx)))
            extent.set("cy", str(int(new_cy)))
            for ext in shape.findall(".//" + qn("a:ext")):
                ext.set("cx", str(int(new_cx)))
                ext.set("cy", str(int(new_cy)))

    # -- 8. numbered lists -------------------------------------------------
    objectives = find_paragraph(paragraphs, lambda t: t.strip() == "Specific objectives:")
    if objectives is not None:
        node = objectives._p.getnext()
        while node is not None and node.tag == qn("w:p"):
            p = Paragraph(node, doc)
            ppr = p._p.find(qn("w:pPr"))
            num_pr = ppr.find(qn("w:numPr")) if ppr is not None else None
            if num_pr is None:
                break
            set_ppr(p, align=justification(paragraph_text(p)), before=0, after=60,
                    line=240, left=720, hanging=360, num_id=num_ids["objectives"])
            set_run_props(p, size=BODY_SIZE)
            node = node.getnext()

    # Section 2.2 typed its numbers as text; make it a real numbered list
    for p in [Paragraph(c, doc) for c in body_el.iterchildren() if c.tag == qn("w:p")]:
        runs = p._p.findall(qn("w:r"))
        if not runs:
            continue
        first = runs[0]
        texts = first.findall(qn("w:t"))
        # the number was typed as its own run, "2." followed by a tab
        if (len(texts) != 1 or not re.fullmatch(r"\d+\.", (texts[0].text or "").strip())
                or first.find(qn("w:tab")) is None):
            continue
        p._p.remove(first)
        set_ppr(p, align=justification(paragraph_text(p)), before=0, after=60,
                line=240, left=720, hanging=360, num_id=num_ids["workflow"])
        set_run_props(p, size=BODY_SIZE)

    # 3.6 becomes numbered steps with a bold step name, like Section 2.2
    prep = find_paragraph(
        paragraphs, lambda t: t.startswith("Images are decoded as RGB with tf.io.decode_image")
    )
    if prep is not None:
        steps = [
            ("Decoding.",
             " Images are decoded as RGB with tf.io.decode_image."),
            ("Resizing.",
             " Every image is resized to 224×224 with antialiasing (tf.image.resize)."),
            ("Rescaling.",
             " Pixel values are kept as float32 in the notebook's data pipeline; the "
             "rescaling to the [-1, 1] range MobileNetV2 expects is performed inside the "
             "model itself (a Rescaling(1/127.5, offset=-1) layer), so the same raw-pixel "
             "input works for both training and the recognize() demo function."),
            ("Augmentation (training set only).",
             " Random horizontal and vertical flip, rotation (±15%), zoom (±15%), "
             "brightness (±20%) and contrast (±20%) are applied to the training set "
             "only, so the model sees more lighting and viewing-angle variation without "
             "changing the validation and testing data used for evaluation."),
        ]
        anchor_el = prep._p
        new_steps = []
        for label, rest in steps:
            step = make_paragraph(doc, [(label, True, False), (rest, False, False)],
                                  align=justification(label + rest),
                                  before=0, after=60, line=240,
                                  left=720, hanging=360, num_id=num_ids["preprocessing"])
            set_run_props(step, size=BODY_SIZE)
            for run in step._p.iter(qn("w:r")):
                pass
            new_steps.append(step)
        # keep the bold label bold, body text regular
        for step, (label, _rest) in zip(new_steps, steps):
            runs = step._p.findall(qn("w:r"))
            set_run_props(Paragraph(step._p, doc), size=BODY_SIZE)
            rpr = runs[0].find(qn("w:rPr"))
            for tag in ("w:b", "w:bCs"):
                for node in rpr.findall(qn(tag)):
                    rpr.remove(node)
                rpr.append(el(tag, val="1"))
        insert_after(anchor_el, *new_steps)
        anchor_el.getparent().remove(anchor_el)

    # -- 9. small accuracy fixes --------------------------------------------
    all_paragraphs = lambda: [Paragraph(c, doc) for c in body_el.iterchildren()
                              if c.tag == qn("w:p")]

    # The 500-image unseen set has 100 images per class, not 20; the header was
    # left over from the earlier 100-image set.
    for table in tables:
        for cell in table.rows[0].cells:
            if cell.text.strip() == "Accuracy (correct/20)":
                set_text(cell.paragraphs[0], [("Accuracy (correct / 100)", True, False)])

    # Section 6.4 claimed no misclassified examples were available; Figure 11 shows ten.
    stale = find_paragraph(all_paragraphs(), lambda t: "only aggregate counts were available" in t)
    if stale is not None:
        text = paragraph_text(stale)
        keep = text.split("Individual misclassified example images")[0].rstrip()
        set_text(stale, [
            keep + " Ten of those misclassified images are shown in Figure 11 "
            "(Section 7.3), each captioned with its true class, the predicted class, and "
            "the confidence of the wrong prediction. Screenshots of the demonstration "
            "program's recognition output are in Appendix D."
        ])
        set_run_props(stale, size=BODY_SIZE)

    # "Training set (2,164 images). used to ..." -> sentence case after the period
    for p in all_paragraphs():
        text = paragraph_text(p)
        m = re.match(r"^((?:Training|Validation|Testing) set \([\d,]+ images\)\. )([a-z])", text)
        if m:
            replace_same_length(p, re.compile(re.escape(m.group(0))),
                                lambda mm: m.group(1) + m.group(2).upper())

    # -- 10. move each figure's explanation below its caption ---------------
    moves = [
        ("ROC AUC (Figure 6) summarizes", "Figure 6."),
        ("Figure 7 shows the validation data behind", "Figure 7."),
        ("The global fallback threshold (0.59) was selected this way", "Figure 8."),
        ("Expected Calibration Error on the test set", "Figure 9."),
        ("Figure 11 shows ten misclassified test images", "Figure 11."),
    ]
    for lead, cap_prefix in moves:
        src = find_paragraph(all_paragraphs(), lambda t, l=lead: t.strip().startswith(l))
        cap = find_paragraph(all_paragraphs(), lambda t, c=cap_prefix: t.strip().startswith(c))
        if src is None or cap is None:
            continue
        src._p.getparent().remove(src._p)
        cap._p.addnext(src._p)

    # -- 11. an explanation under every table and figure that lacked one ----
    explanations = [
        ("Figure 1.",
         "The dashed box marks the processing computer: every step of Part A happens "
         "there, including the per-class threshold that decides between a class label "
         "and \u201cUncertain\u201d. The phone and the relay below it only move the picture."),
        ("Table 9.",
         "Cardboard holds up best on these images at 78%, while Paper falls to 37% "
         "and Plastic to 39%."),
        ("Table 1.",
         "The subset is uneven: Plastic contributes 921 images and Glass 420. The "
         "stratified split keeps each class in the same proportion inside the training, "
         "validation and testing sets, so no split is made easier or harder than the "
         "others by the imbalance."),
        ("Table 4.",
         "The five classes are the RealWaste categories a sorting robot would have to "
         "separate, and every one of them is far above the Midterm minimum of 100 images: "
         "the smallest, Glass, has 420."),
        ("Figure 3.",
         "The samples show why the task is not trivial. Items appear crushed, torn, dirty "
         "or partly transparent, and several classes share the same muted colors and "
         "textures, which is the visual similarity described in Section 1.2."),
        ("Figure 4.",
         "Each augmented copy is the same training image under a different flip, rotation, "
         "zoom, brightness or contrast, so the model sees more lighting and viewing-angle "
         "variation than the dataset itself contains. The validation and testing images are "
         "left untouched."),
    ]
    existing_text = {paragraph_text(p).strip() for p in all_paragraphs()}
    for cap_prefix, note in explanations:
        if note in existing_text:
            continue
        cap = find_paragraph(all_paragraphs(), lambda t, c=cap_prefix: t.strip().startswith(c))
        if cap is None:
            continue
        note_p = body(doc, [note])
        cap._p.addnext(note_p._p)

    # a lead-in between the configuration table and the threshold table
    lead_text = ("The confidence threshold in the last row is not a single number: each "
                 "class has its own, listed below.")
    if lead_text not in existing_text:
        cap = find_paragraph(all_paragraphs(), lambda t: t.strip().startswith("Table 6."))
        if cap is not None:
            cap._p.addnext(body(doc, [lead_text])._p)

    # -- 12. break the threshold rationale into readable paragraphs ---------
    long_p = find_paragraph(all_paragraphs(), lambda t: t.startswith("A reject option, allowing"))
    if long_p is not None:
        full = paragraph_text(long_p)
        marks = ["Per-class confidence thresholds were then selected",
                 "Calibration mattered for interpreting these thresholds"]
        cuts = [0] + [full.index(m) for m in marks if m in full] + [len(full)]
        chunks = [full[cuts[i]:cuts[i + 1]].strip() for i in range(len(cuts) - 1)]
        chunks[-1] += (" The validation sweep and the selection rule behind these "
                       "thresholds are reproduced in Appendix A.")
        set_text(long_p, [chunks[0]])
        set_run_props(long_p, size=BODY_SIZE)
        anchor = long_p._p
        for chunk in chunks[1:]:
            p = body(doc, [chunk])
            set_run_props(p, size=BODY_SIZE)
            anchor.addnext(p._p)
            anchor = p._p

    # -- 13. appendix pointers in the body ----------------------------------
    pointers = [
        ("The live demonstration extends Part A with remote camera input",
         " Figure 1 is repeated on a page of its own in Appendix E."),
        ("Most common mistakes (true class misread as predicted class",
         " This confusion matrix is repeated on a page of its own in Appendix B."),
        ("The drop from 87.93% to 56.00% is domain shift",
         " This confusion matrix is repeated on a page of its own in Appendix C."),
    ]
    for prefix, extra in pointers:
        p = find_paragraph(all_paragraphs(), lambda t, pre=prefix: t.strip().startswith(pre))
        if p is None or extra.strip() in paragraph_text(p):
            continue
        run = p.add_run(extra)
        set_run_props(p, size=BODY_SIZE)

    # -- 14. Section 9.2: bold only the label of the first recommendation ---
    rec = find_paragraph(all_paragraphs(),
                         lambda t: t.strip().startswith("Close the generalization gap"))
    if rec is not None:
        text = paragraph_text(rec).strip()
        head, _, tail = text.partition(".")
        set_text(rec, [(head + ".", True, False), (" " + tail.strip(), False, False)])
        set_run_props(rec, size=BODY_SIZE)
        for run in rec._p.findall(qn("w:r"))[1:]:
            rpr = run.find(qn("w:rPr"))
            for tag in ("w:b", "w:bCs"):
                for node in rpr.findall(qn(tag)):
                    rpr.remove(node)
                rpr.append(el(tag, val="0"))

    # -- 15. clickable URLs ------------------------------------------------
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    url_re = re.compile(r"https?://\S+")

    def url_end(text, start, end):
        """Trim trailing sentence punctuation, and a closing bracket we never opened."""
        while end > start:
            last = text[end - 1]
            if last in ".,;:":
                end -= 1
            elif last == ")" and text.count(")", start, end) > text.count("(", start, end):
                end -= 1
            else:
                break
        return end

    def hyperlink_el(url, segments):
        """A w:hyperlink wrapping runs built from (text, italic) segments."""
        rid = doc.part.relate_to(url, RT.HYPERLINK, is_external=True)
        link = el("w:hyperlink")
        link.set(qn("r:id"), rid)
        for text, italic in segments:
            run = el("w:r")
            rpr = el("w:rPr")
            rpr.append(el("w:color", val="0563C1"))
            rpr.append(el("w:u", val="single"))
            if italic:
                rpr.append(el("w:i", val="1"))
                rpr.append(el("w:iCs", val="1"))
            rpr.append(el("w:sz", val=BODY_SIZE))
            rpr.append(el("w:szCs", val=BODY_SIZE))
            run.append(rpr)
            t = el("w:t")
            t.set(qn("xml:space"), "preserve")
            t.text = text
            run.append(t)
            link.append(run)
        return link

    def plain_run(text, italic, size=BODY_SIZE):
        run = el("w:r")
        rpr = el("w:rPr")
        if italic:
            rpr.append(el("w:i", val="1"))
            rpr.append(el("w:iCs", val="1"))
        rpr.append(el("w:sz", val=size))
        rpr.append(el("w:szCs", val=size))
        run.append(rpr)
        t = el("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        run.append(t)
        return run

    def linkify(p):
        """Turn every URL into a hyperlink, keeping the italics already there."""
        chars = []
        for run in p._p.findall(qn("w:r")):
            rpr = run.find(qn("w:rPr"))
            italic = rpr is not None and rpr.find(qn("w:i")) is not None and \
                rpr.find(qn("w:i")).get(qn("w:val"), "1") not in ("0", "false")
            for t in run.findall(qn("w:t")):
                for ch in (t.text or ""):
                    chars.append((ch, italic))
        text = "".join(c for c, _ in chars)
        spans = [(m.start(), url_end(text, m.start(), m.end()))
                 for m in url_re.finditer(text)]
        if not spans:
            return False
        for child in list(p._p):
            if child.tag != qn("w:pPr"):
                p._p.remove(child)

        def emit(lo, hi, url=None):
            segments, start = [], lo
            for i in range(lo, hi + 1):
                if i == hi or chars[i][1] != chars[start][1]:
                    segments.append((text[start:i], chars[start][1]))
                    start = i
            if url:
                p._p.append(hyperlink_el(url, segments))
            else:
                for seg_text, italic in segments:
                    p._p.append(plain_run(seg_text, italic))

        cursor = 0
        for start, end in spans:
            if start > cursor:
                emit(cursor, start)
            emit(start, end, url=text[start:end])
            cursor = end
        if cursor < len(text):
            emit(cursor, len(text))
        return True

    # -- 16. the reference list: APA hanging indent, clickable DOIs ---------
    refs_heading = find_paragraph(all_paragraphs(), lambda t: t.strip() == "REFERENCES")
    node = refs_heading._p.getnext()
    while node is not None:
        if node.tag == qn("w:p"):
            p = Paragraph(node, doc)
            if paragraph_text(p).strip():
                set_ppr(p, align="left", before=0, after=120, line=240,
                        left=720, hanging=720)
                set_run_props(p, size=BODY_SIZE)
                linkify(p)
        node = node.getnext()

    # -- 17. the project links move off the cover into Section 5.1 ----------
    impl = find_paragraph(all_paragraphs(),
                          lambda t: t.startswith("The demonstration pipeline is implemented"))
    if impl is not None and "Appendix F" not in paragraph_text(impl):
        text = paragraph_text(impl)
        github = "https://github.com/J4ve/cv-object-sorting"
        colab = ("https://colab.research.google.com/drive/"
                 "1Uunfl1tFrYVt09Iig5-hYnvL3mn288m5?usp=sharing")
        head, _, tail = text.partition(github)
        for child in list(impl._p):
            if child.tag != qn("w:pPr"):
                impl._p.remove(child)
        impl._p.append(plain_run(head, False))
        impl._p.append(hyperlink_el(github, [(github, False)]))
        impl._p.append(plain_run(tail, False))
        impl._p.append(plain_run(" The notebook can also be opened directly as a ", False))
        impl._p.append(hyperlink_el(colab, [("Google Colab copy", False)]))
        impl._p.append(plain_run(". Both links are repeated in Appendix F.", False))

    # -- 18. appendices -----------------------------------------------------
    import json as _json

    def load(name):
        return _json.loads((ROOT / "results" / name).read_text())

    sweep = load("threshold_sweep.json")
    selection = load("threshold_selection.json")

    # Everything below goes at the end of the body but before w:sectPr, which
    # must stay the last child.
    section = body_el.find(qn("w:sectPr"))

    def emit(element):
        section.addprevious(element)
        return element

    def appendix_heading(text, *, page_break):
        p = make_paragraph(doc, [text], align="left", before=240, after=120,
                           line=240, keep_next=True, keep_lines=True,
                           page_break=page_break)
        set_run_props(p, size=H2_SIZE, bold=False)
        emit(p._p)
        return p

    def appendix_body(text):
        p = body(doc, [text])
        set_run_props(p, size=BODY_SIZE)
        emit(p._p)
        return p

    def appendix_caption(text):
        p = caption(doc, text)
        emit(p._p)
        return p

    def appendix_figure(image_path: Path):
        p = Paragraph(el("w:p"), doc)
        p.add_run().add_picture(str(image_path), width=TEXT_WIDTH_EMU)
        set_ppr(p, align="center", before=120, after=60, keep_next=True)
        emit(p._p)
        return p

    def appendix_table(rows):
        table = doc.add_table(rows=len(rows), cols=len(rows[0]))
        emit(table._tbl)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = table.cell(r, c)
                cell.text = ""
                set_text(cell.paragraphs[0], [str(value)])
        return table

    if find_paragraph(all_paragraphs(), lambda t: t.strip() == "APPENDICES") is None:
        head = make_paragraph(doc, [("APPENDICES", True, False)], align="left",
                              before=0, after=240, line=240, keep_next=True,
                              keep_lines=True, page_break=True)
        set_run_props(head, size=H1_SIZE, bold=True)
        emit(head._p)

        # Appendix A ---------------------------------------------------------
        appendix_heading("Appendix A. Threshold sweep and threshold selection", page_break=False)
        appendix_body(
            "Section 4.5 explains why the classifier is allowed to answer “Uncertain” "
            "instead of forcing a label, and Section 4.6 applies one threshold per predicted "
            "class. The two tables below are the validation evidence behind those numbers."
        )
        rows = [["Threshold", "Coverage", "Accuracy on covered predictions",
                 "Wrong predictions caught"]]
        for row in sweep["validation_sweep"]:
            rows.append([
                f"{row['threshold']:.2f}",
                f"{row['coverage'] * 100:.2f}%",
                f"{row['accuracy_on_covered'] * 100:.2f}%",
                f"{row['pct_wrong_caught_as_uncertain'] * 100:.2f}%",
            ])
        appendix_table(rows)
        appendix_caption("Table 10. Confidence threshold sweep on the 464-image validation "
                         "set, the data plotted in Figure 7.")
        appendix_body(
            "Raising the threshold buys accuracy with coverage. At 0.40 the classifier "
            "answers for almost every image but is right on 86.40% of them; at 0.90 it "
            "answers for 59.48% and is right on 98.55% of those. The thresholds in Table 7 "
            "sit in between, where most images still get an answer."
        )

        chosen = selection["chosen_threshold"]
        val_row = selection["validation_row_at_chosen_t"]
        test_row = selection["test_row_at_chosen_t"]
        appendix_table([
            ["Measure", "Value"],
            ["Selection rule", selection["selection_rule"].replace(">=", "\u2265")],
            ["Chosen global fallback threshold", f"{chosen:.2f}"],
            ["Validation coverage at that threshold", f"{val_row['coverage'] * 100:.2f}%"],
            ["Validation accuracy on covered predictions",
             f"{val_row['selective_accuracy'] * 100:.2f}%"],
            ["Test coverage at that threshold", f"{test_row['coverage'] * 100:.2f}%"],
            ["Test accuracy on covered predictions",
             f"{test_row['accuracy_on_covered'] * 100:.2f}%"],
            ["Test errors caught as Uncertain",
             f"{test_row['n_errors_caught']} of {test_row['n_errors_total']}"],
        ])
        appendix_caption("Table 11. The global fallback threshold, chosen on the validation "
                         "set and then applied once to the test set.")
        appendix_body(
            "The fallback threshold is used only for a class with too few validation "
            "predictions to estimate its own threshold reliably (Section 4.5). Applied to "
            "the test set it keeps 87.72% of the predictions and is right on 93.37% of "
            "them, catching 29 of the 56 test errors instead of reporting them as "
            "confident answers."
        )

        # Appendix B ---------------------------------------------------------
        appendix_heading("Appendix B. Confusion matrix on the RealWaste test set",
                         page_break=True)
        appendix_figure(ROOT / "results" / "confusion_matrix.png")
        appendix_caption("Figure 12. The confusion matrix on the 464-image test set, repeated "
                         "from Figure 5 (counts, left; row-normalized, right).")
        appendix_body(
            "The diagonal holds the correct predictions. The off-diagonal cells show that "
            "the mistakes cluster on visually similar materials rather than spreading "
            "evenly: Metal read as Plastic, Plastic read as Glass or Metal, and Cardboard "
            "read as Paper."
        )

        # Appendix C ---------------------------------------------------------
        appendix_heading("Appendix C. Confusion matrix on the unseen TrashNet test set",
                         page_break=True)
        appendix_figure(ROOT / "results" / "unseen_trashnet_confusion_matrix.png")
        appendix_caption("Figure 13. The confusion matrix on the 500-image unseen TrashNet "
                         "test set, repeated from Figure 10.")
        appendix_body(
            "The error pattern is different from the one in Appendix B. On images from "
            "outside RealWaste the model falls back on Cardboard for every other class, "
            "most sharply for Paper, which is the domain shift discussed in Section 6.5."
        )

        # Appendix D ---------------------------------------------------------
        appendix_heading("Appendix D. Recognition output of the demonstration program",
                         page_break=True)
        appendix_figure(ROOT / "docs" / "images" / "demo-presenter-grid.png")
        appendix_caption("Figure 14. Presenter view of the demonstration program, "
                         "captured during a user-interface check with three devices "
                         "connected.")
        appendix_body(
            "Each card holds one connected device, the image that device sent, and the "
            "class and confidence the model returned for it: Cardboard 83.6%, Glass 97.6% "
            "and Metal 99.7%. This is a capture of the interface described in Sections 5.2 "
            "and 5.3, not a record of the Midterm demonstration itself."
        )
        appendix_figure(ROOT / "docs" / "images" / "demo-uncertain.png")
        appendix_caption("Figure 15. The reject option: a prediction below its threshold "
                         "is reported as Uncertain together with the best guess.")
        appendix_body(
            "Rather than forcing a label, the program names the best guess and the "
            "confidence it fell short by. Both captures come from an earlier build that "
            "compared every prediction against one threshold of 0.60; the program now "
            "compares each prediction against that class's own threshold from Table 7."
        )

        # Appendix E ---------------------------------------------------------
        appendix_heading("Appendix E. System architecture diagram", page_break=True)
        appendix_figure(ROOT / "docs" / "images" / "system-architecture.png")
        appendix_caption("Figure 16. The system architecture, repeated from Figure 1: the "
                         "recognition pipeline, the live demonstration path, and the "
                         "offline training pipeline.")
        appendix_body(
            "Part A is what happens to one image at demonstration time and Part B is the "
            "offline run that produced the model it uses. Every step of Part A runs on the "
            "processing computer: a connected phone and the relay only move the picture."
        )

        # Appendix F ---------------------------------------------------------
        appendix_heading("Appendix F. Project materials", page_break=True)
        appendix_body(
            "The notebook, the trained model, the live demonstration program, and the "
            "figures and metrics cited in this report are all published in the project "
            "repository."
        )
        github = "https://github.com/J4ve/cv-object-sorting"
        colab = ("https://colab.research.google.com/drive/"
                 "1Uunfl1tFrYVt09Iig5-hYnvL3mn288m5?usp=sharing")
        for label, url in [("GitHub repository: ", github),
                           ("Training and evaluation notebook (Google Colab copy): ", colab)]:
            p = make_paragraph(doc, [], align="left", before=0, after=80, line=240,
                               left=720, hanging=360, num_id="1")
            p._p.append(plain_run(label, False))
            p._p.append(hyperlink_el(url, [(url, False)]))
            emit(p._p)
        appendix_body(
            "Inside the repository, the notebook is "
            "src/training/Midterm_Object_Sorting_RealWaste.ipynb, the trained model is "
            "models/waste_classifier.keras, and the metrics and figures cited here are in "
            "results/."
        )

    # -- 19. every table gets the same compact look ------------------------
    for tbl_el in body_el.findall(qn("w:tbl")):
        style_table(Table(tbl_el, doc))

    # -- 20. make the file schema-clean for Word ---------------------------
    # Word is stricter than LibreOffice: a property element out of order, or a
    # decimal where the schema wants an integer, can make it refuse the file.
    # The Google Docs export shipped hundreds of cell margins like w:w="100.0",
    # and the helpers above append properties in whatever order they run.
    CHILD_ORDER = {
        "pPr": ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
                "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
                "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
                "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
                "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
                "suppressOverlap", "jc", "textDirection", "textAlignment",
                "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
                "pPrChange"],
        "rPr": ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
                "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
                "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
                "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
                "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
                "specVanish", "oMath", "rPrChange"],
        "tblPr": ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
                  "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
                  "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
                  "tblDescription", "tblPrChange"],
        "tcPr": ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
                 "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
                 "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange"],
        "trPr": ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
                 "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden",
                 "ins", "del", "trPrChange"],
    }

    decimal_value = re.compile(r"^-?\d+\.\d+$")

    def normalize(root):
        for element in root.iter():
            for name, value in list(element.attrib.items()):
                if decimal_value.match(value or ""):
                    element.set(name, str(int(round(float(value)))))
            tag = element.tag.split("}")[1]
            order = CHILD_ORDER.get(tag)
            if not order:
                continue
            children = list(element)
            index = {name: i for i, name in enumerate(order)}
            children.sort(key=lambda c: index.get(c.tag.split("}")[1], len(order)))
            for child in children:
                element.append(child)

    normalize(doc.element)
    normalize(doc.part.numbering_part.element)
    normalize(doc.styles.element)

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
