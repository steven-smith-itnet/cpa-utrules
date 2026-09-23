# -*- coding: utf-8 -*-
"""
pdfgen - a tiny, dependency-free PDF writer (Python standard library only).

Just enough of the PDF 1.4 spec to typeset a long, text-only legal document:

  * Base-14 fonts (Helvetica / Helvetica-Bold / Helvetica-Oblique / Courier)
    with real Adobe glyph-width metrics, so line breaking is accurate.
  * WinAnsi text encoding.
  * Flate-compressed content streams.
  * Word wrapping with hanging indents (for statutory subsection numbering).
  * Cover page, running header/footer, page numbers.
  * A generated table of contents and real PDF outline bookmarks.

Used by build_reference.py to assemble the official Utah CPA laws and rules
into a single study PDF.  Nothing here is CPA-specific.
"""

import zlib

# --------------------------------------------------------------------------
# Font metrics (Adobe standard widths, units of 1/1000 em)
# --------------------------------------------------------------------------

_HELV = {
    32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
    40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
    48: 556, 49: 556, 50: 556, 51: 556, 52: 556, 53: 556, 54: 556, 55: 556,
    56: 556, 57: 556, 58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556,
    64: 1015, 65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778,
    72: 722, 73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778,
    80: 667, 81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944,
    88: 667, 89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556,
    96: 333, 97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278,
    103: 556, 104: 556, 105: 222, 106: 222, 107: 500, 108: 222, 109: 833,
    110: 556, 111: 556, 112: 556, 113: 556, 114: 333, 115: 500, 116: 278,
    117: 556, 118: 500, 119: 722, 120: 500, 121: 500, 122: 500, 123: 334,
    124: 260, 125: 334, 126: 584,
    145: 222, 146: 222, 147: 333, 148: 333, 149: 350, 150: 556, 151: 1000,
    167: 556, 169: 737, 176: 400, 183: 278,
}

_HELV_BOLD = {
    32: 278, 33: 333, 34: 474, 35: 556, 36: 556, 37: 889, 38: 722, 39: 238,
    40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
    48: 556, 49: 556, 50: 556, 51: 556, 52: 556, 53: 556, 54: 556, 55: 556,
    56: 556, 57: 556, 58: 333, 59: 333, 60: 584, 61: 584, 62: 584, 63: 611,
    64: 975, 65: 722, 66: 722, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778,
    72: 722, 73: 278, 74: 556, 75: 722, 76: 611, 77: 833, 78: 722, 79: 778,
    80: 667, 81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944,
    88: 667, 89: 667, 90: 611, 91: 333, 92: 278, 93: 333, 94: 584, 95: 556,
    96: 333, 97: 556, 98: 611, 99: 556, 100: 611, 101: 556, 102: 333,
    103: 611, 104: 611, 105: 278, 106: 278, 107: 556, 108: 278, 109: 889,
    110: 611, 111: 611, 112: 611, 113: 611, 114: 389, 115: 556, 116: 333,
    117: 611, 118: 556, 119: 778, 120: 556, 121: 556, 122: 500, 123: 389,
    124: 280, 125: 389, 126: 584,
    145: 278, 146: 278, 147: 500, 148: 500, 149: 350, 150: 556, 151: 1000,
    167: 556, 169: 737, 176: 400, 183: 278,
}

# Font key -> (BaseFont name, width table, default width)
FONTS = {
    "R": ("Helvetica", _HELV, 556),
    "B": ("Helvetica-Bold", _HELV_BOLD, 556),
    "I": ("Helvetica-Oblique", _HELV, 556),
    "M": ("Courier", None, 600),          # monospace: every glyph is 600
}
_FONT_ORDER = ["R", "B", "I", "M"]
_FONT_RES = {k: "/F%d" % (i + 1) for i, k in enumerate(_FONT_ORDER)}

# Characters that have no WinAnsi equivalent get folded to something printable.
_FOLD = {
    "‘": "\x91", "’": "\x92", "“": "\x93", "”": "\x94",
    "•": "\x95", "–": "\x96", "—": "\x97", "§": "\xa7",
    " ": " ", "…": "...", "′": "'", "″": '"',
    "ﬁ": "fi", "ﬂ": "fl", "−": "-", "­": "-",
}


def _to_winansi(text):
    """Fold a unicode string down to a WinAnsi-safe byte string."""
    out = []
    for ch in text:
        if ch in _FOLD:
            ch = _FOLD[ch]
        for c in ch:
            o = ord(c)
            if o < 256:
                out.append(c)
            else:
                out.append("?")
    return "".join(out)


def text_width(text, font, size):
    """Width of `text` in points when set in `font` at `size`."""
    _, table, default = FONTS[font]
    if table is None:
        return len(text) * default * size / 1000.0
    total = 0
    for ch in _to_winansi(text):
        total += table.get(ord(ch), default)
    return total * size / 1000.0


def _pdf_escape(text):
    s = _to_winansi(text)
    s = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return s


# --------------------------------------------------------------------------
# Line breaking
# --------------------------------------------------------------------------

def wrap(text, font, size, width):
    """Greedy word wrap.  Returns a list of lines that each fit in `width`."""
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if text_width(trial, font, size) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    # A single word longer than the column must still be broken somewhere.
    out = []
    for line in lines:
        while text_width(line, font, size) > width and len(line) > 1:
            cut = len(line) - 1
            while cut > 1 and text_width(line[:cut], font, size) > width:
                cut -= 1
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


# --------------------------------------------------------------------------
# Document model
# --------------------------------------------------------------------------

class Document(object):
    """A paginated, text-only PDF document."""

    def __init__(self, title="", subject="", author="", page=(612.0, 792.0),
                 margin_left=58.0, margin_right=58.0,
                 margin_top=62.0, margin_bottom=58.0,
                 body_font="R", body_size=9.4, leading=12.2,
                 running_header=""):
        self.title = title
        self.subject = subject
        self.author = author
        self.pw, self.ph = page
        self.ml, self.mr = margin_left, margin_right
        self.mt, self.mb = margin_top, margin_bottom
        self.body_font = body_font
        self.body_size = body_size
        self.leading = leading
        self.running_header = running_header
        self.blocks = []

    # -- content -----------------------------------------------------------

    @property
    def column_width(self):
        return self.pw - self.ml - self.mr

    def cover(self, lines):
        """`lines` is a list of (text, font, size, gap_after) tuples."""
        self.blocks.append({"t": "cover", "lines": lines})

    def page_break(self):
        self.blocks.append({"t": "break"})

    def heading(self, text, level=1, bookmark=True, new_page=False):
        self.blocks.append({"t": "head", "text": text, "level": level,
                            "bookmark": bookmark, "new_page": new_page})

    def para(self, text, indent=0.0, hang=0.0, font=None, size=None,
             space_before=0.0, space_after=2.4, color=None):
        self.blocks.append({"t": "para", "text": text, "indent": indent,
                            "hang": hang, "font": font or self.body_font,
                            "size": size or self.body_size,
                            "sb": space_before, "sa": space_after,
                            "color": color})

    def pre(self, lines, size=7.6, indent=0.0):
        """Preformatted monospace lines (used for the statutory fine table)."""
        self.blocks.append({"t": "pre", "lines": lines, "size": size,
                            "indent": indent})

    def rule(self, space_before=4.0, space_after=6.0):
        self.blocks.append({"t": "rule", "sb": space_before, "sa": space_after})

    def spacer(self, height):
        self.blocks.append({"t": "spacer", "h": height})

    def toc_placeholder(self):
        """Reserve room for the table of contents at this point."""
        self.blocks.append({"t": "toc"})

    # -- layout ------------------------------------------------------------

    def _head_style(self, level):
        if level == 0:
            return ("B", 17.0, 20.0, 12.0)      # font, size, space_before, after
        if level == 1:
            return ("B", 11.6, 12.0, 4.5)
        return ("B", 9.8, 8.0, 3.0)

    def _layout(self, blocks, toc_lines):
        """Turn blocks into pages.  Returns (pages, headings).

        pages    : list of pages; each page is a list of draw operations
        headings : list of (level, text, page_index)
        """
        pages, headings = [], []
        page, y = [], None
        top = self.ph - self.mt
        bottom = self.mb

        def new_page():
            nonlocal page, y
            page = []
            pages.append(page)
            y = top

        def need(h):
            if y - h < bottom:
                new_page()

        new_page()

        def emit_lines(lines, font, size, x0, x_hang, lead):
            nonlocal y
            for i, line in enumerate(lines):
                need(lead)
                x = x0 if i == 0 else x_hang
                page.append(("t", x, y - size * 0.86, font, size, line, None))
                y -= lead

        for b in blocks:
            kind = b["t"]

            if kind == "cover":
                if page:
                    new_page()
                yy = self.ph * 0.70
                for text, font, size, gap in b["lines"]:
                    for line in wrap(text, font, size, self.column_width):
                        w = text_width(line, font, size)
                        page.append(("t", (self.pw - w) / 2.0, yy, font, size,
                                     line, None))
                        yy -= size * 1.32
                    yy -= gap
                page.append(("cover", None, None, None, None, None, None))
                new_page()

            elif kind == "break":
                if page:
                    new_page()

            elif kind == "toc":
                if page:
                    new_page()
                page.append(("t", self.ml, top - 16.0, "B", 15.0,
                             "Table of Contents", None))
                y = top - 40.0
                for level, text, pno in toc_lines:
                    lead = (15.0, 12.6, 11.4)[min(level, 2)]
                    need(lead)
                    font = "B" if level == 0 else "R"
                    size = (10.4, 9.2, 8.5)[min(level, 2)]
                    x = self.ml + (0.0, 16.0, 32.0)[min(level, 2)]
                    label = str(pno) if pno else ""
                    avail = self.column_width - 34.0 - (x - self.ml)
                    line = text
                    while text_width(line, font, size) > avail and len(line) > 4:
                        line = line[:-2]
                    if line != text:
                        line = line.rstrip() + "..."
                    page.append(("t", x, y - size * 0.86, font, size, line, None))
                    if label:
                        w = text_width(label, font, size)
                        page.append(("t", self.pw - self.mr - w,
                                     y - size * 0.86, font, size, label, None))
                    y -= lead
                new_page()

            elif kind == "head":
                font, size, sb, sa = self._head_style(b["level"])
                if b["new_page"] and page:
                    new_page()
                lines = wrap(b["text"], font, size, self.column_width)
                block_h = sb + len(lines) * (size * 1.24) + sa
                # keep a heading with at least two lines of the text below it
                if y - block_h - self.leading * 2 < bottom:
                    new_page()
                else:
                    y -= sb
                headings.append((b["level"], b["text"], len(pages) - 1,
                                 b["bookmark"]))
                for line in lines:
                    page.append(("t", self.ml, y - size * 0.9, font, size,
                                 line, None))
                    y -= size * 1.24
                y -= sa

            elif kind == "para":
                font, size = b["font"], b["size"]
                lead = max(self.leading, size * 1.24)
                y -= b["sb"]
                x0 = self.ml + b["indent"]
                x_hang = x0 + b["hang"]
                if b["hang"]:
                    # the first line starts left of the wrapped remainder
                    lines = _rewrap_hanging(b["text"], font, size,
                                            self.pw - self.mr - x0,
                                            self.pw - self.mr - x_hang)
                else:
                    lines = wrap(b["text"], font, size,
                                 self.pw - self.mr - x0)
                emit_lines(lines, font, size, x0, x_hang, lead)
                y -= b["sa"]

            elif kind == "pre":
                size = b["size"]
                lead = size * 1.30
                for line in b["lines"]:
                    need(lead)
                    page.append(("t", self.ml + b["indent"], y - size * 0.86,
                                 "M", size, line, None))
                    y -= lead
                y -= 4.0

            elif kind == "rule":
                y -= b["sb"]
                need(2.0)
                page.append(("r", self.ml, y, self.pw - self.mr, y, None, None))
                y -= b["sa"]

            elif kind == "spacer":
                need(b["h"])
                y -= b["h"]

        return pages, headings

    # -- output ------------------------------------------------------------

    def render(self, path):
        # Pass 1: lay out with an empty TOC so we learn each heading's page.
        toc_headings = [(b["level"], b["text"]) for b in self.blocks
                        if b["t"] == "head" and b["bookmark"]]
        placeholder = [(lv, tx, 0) for lv, tx in toc_headings]
        _, headings = self._layout(self.blocks, placeholder)
        head_pages = {}
        for level, text, pidx, bm in headings:
            head_pages.setdefault((level, text), pidx)

        toc_lines = [(lv, tx, head_pages.get((lv, tx), 0) + 1)
                     for lv, tx in toc_headings]

        # Pass 2: real TOC.  Page numbers can shift if the TOC grew, so repeat
        # until the numbering is stable (converges in one or two rounds).
        for _ in range(4):
            pages, headings = self._layout(self.blocks, toc_lines)
            head_pages = {}
            for level, text, pidx, bm in headings:
                head_pages.setdefault((level, text), pidx)
            new_toc = [(lv, tx, head_pages.get((lv, tx), 0) + 1)
                       for lv, tx in toc_headings]
            if new_toc == toc_lines:
                break
            toc_lines = new_toc

        return self._write(path, pages, headings)

    def _page_stream(self, ops, page_no, total, is_cover):
        out = []
        for op in ops:
            if op[0] == "t":
                _, x, y, font, size, text, _ = op
                out.append("BT %s %.2f Tf %.2f %.2f Td (%s) Tj ET"
                           % (_FONT_RES[font], size, x, y, _pdf_escape(text)))
            elif op[0] == "r":
                _, x1, y1, x2, y2, _, _ = op
                out.append("0.72 0.72 0.75 RG 0.6 w %.2f %.2f m %.2f %.2f l S "
                           "0 0 0 RG" % (x1, y1, x2, y2))
        if not is_cover:
            if self.running_header:
                out.append("0.45 0.45 0.48 rg BT %s 7.6 Tf %.2f %.2f Td (%s) "
                           "Tj ET 0 0 0 rg"
                           % (_FONT_RES["R"], self.ml, self.ph - self.mt + 22.0,
                              _pdf_escape(self.running_header)))
                out.append("0.80 0.80 0.83 RG 0.5 w %.2f %.2f m %.2f %.2f l S "
                           "0 0 0 RG"
                           % (self.ml, self.ph - self.mt + 17.0,
                              self.pw - self.mr, self.ph - self.mt + 17.0))
            label = "%d / %d" % (page_no, total)
            w = text_width(label, "R", 7.6)
            out.append("0.45 0.45 0.48 rg BT %s 7.6 Tf %.2f %.2f Td (%s) Tj ET "
                       "0 0 0 rg"
                       % (_FONT_RES["R"], (self.pw - w) / 2.0, self.mb - 26.0,
                          _pdf_escape(label)))
        return "\n".join(out).encode("latin-1", "replace")

    def _write(self, path, pages, headings):
        objs = {}          # number -> bytes body (without "n 0 obj"/"endobj")
        nxt = [1]

        def alloc():
            n = nxt[0]
            nxt[0] += 1
            return n

        catalog_no = alloc()
        pages_no = alloc()
        info_no = alloc()
        font_nos = {}
        for key in _FONT_ORDER:
            font_nos[key] = alloc()

        cover_pages = set()
        for i, ops in enumerate(pages):
            if any(op[0] == "cover" for op in ops):
                cover_pages.add(i)

        page_nos, content_nos = [], []
        for _ in pages:
            page_nos.append(alloc())
            content_nos.append(alloc())

        total = len(pages)
        for i, ops in enumerate(pages):
            raw = self._page_stream(ops, i + 1, total, i in cover_pages)
            comp = zlib.compress(raw, 9)
            objs[content_nos[i]] = (
                b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp)
                + comp + b"\nendstream")
            res = " ".join("%s %d 0 R" % (_FONT_RES[k], font_nos[k])
                           for k in _FONT_ORDER)
            objs[page_nos[i]] = (
                "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                "/Resources << /Font << %s >> >> /Contents %d 0 R >>"
                % (pages_no, self.pw, self.ph, res, content_nos[i])
            ).encode("latin-1")

        for key in _FONT_ORDER:
            base = FONTS[key][0]
            objs[font_nos[key]] = (
                "<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                "/Encoding /WinAnsiEncoding >>" % base).encode("latin-1")

        kids = " ".join("%d 0 R" % n for n in page_nos)
        objs[pages_no] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                          % (len(page_nos), kids)).encode("latin-1")

        # ---- outline bookmarks ------------------------------------------
        marks = [(lv, tx, pi) for lv, tx, pi, bm in headings if bm and lv <= 2]
        outline_root = alloc()
        item_nos = [alloc() for _ in marks]

        # Nest by heading level; a level that appears without a parent one
        # level up simply attaches to the nearest shallower ancestor.
        parent_of, stack = {}, []       # stack of (level, index)
        for i, (lv, _tx, _pi) in enumerate(marks):
            while stack and stack[-1][0] >= lv:
                stack.pop()
            parent_of[i] = item_nos[stack[-1][1]] if stack else outline_root
            stack.append((lv, i))

        def children_of(idx):
            return [j for j in range(len(marks))
                    if parent_of[j] == item_nos[idx]]

        siblings = {}
        for i in range(len(marks)):
            siblings.setdefault(parent_of[i], []).append(i)

        for i, (lv, tx, pi) in enumerate(marks):
            sibs = siblings[parent_of[i]]
            pos = sibs.index(i)
            parts = ["/Title (%s)" % _pdf_escape(tx),
                     "/Parent %d 0 R" % parent_of[i],
                     "/Dest [%d 0 R /XYZ 0 %.2f 0]" % (page_nos[pi], self.ph)]
            if pos > 0:
                parts.append("/Prev %d 0 R" % item_nos[sibs[pos - 1]])
            if pos < len(sibs) - 1:
                parts.append("/Next %d 0 R" % item_nos[sibs[pos + 1]])
            kids_i = children_of(i)
            if kids_i:
                parts.append("/First %d 0 R" % item_nos[kids_i[0]])
                parts.append("/Last %d 0 R" % item_nos[kids_i[-1]])
                parts.append("/Count %d" % len(kids_i))
            objs[item_nos[i]] = ("<< %s >>" % " ".join(parts)).encode("latin-1")

        root_kids = siblings.get(outline_root, [])
        if root_kids:
            objs[outline_root] = (
                "<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>"
                % (item_nos[root_kids[0]], item_nos[root_kids[-1]],
                   len(root_kids))).encode("latin-1")
        else:
            objs[outline_root] = b"<< /Type /Outlines /Count 0 >>"

        objs[catalog_no] = (
            "<< /Type /Catalog /Pages %d 0 R /Outlines %d 0 R "
            "/PageMode /UseOutlines >>" % (pages_no, outline_root)
        ).encode("latin-1")

        objs[info_no] = (
            "<< /Title (%s) /Subject (%s) /Author (%s) /Creator (pdfgen.py) >>"
            % (_pdf_escape(self.title), _pdf_escape(self.subject),
               _pdf_escape(self.author))).encode("latin-1")

        # ---- serialise ---------------------------------------------------
        buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for num in sorted(objs):
            offsets[num] = len(buf)
            buf += b"%d 0 obj\n" % num
            buf += objs[num]
            buf += b"\nendobj\n"

        xref_at = len(buf)
        count = max(objs) + 1
        buf += b"xref\n0 %d\n" % count
        buf += b"0000000000 65535 f \n"
        for num in range(1, count):
            buf += b"%010d 00000 n \n" % offsets.get(num, 0)
        buf += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\n"
                % (count, catalog_no, info_no))
        buf += b"startxref\n%d\n%%%%EOF\n" % xref_at

        with open(path, "wb") as fh:
            fh.write(bytes(buf))
        return len(pages)


def _rewrap_hanging(text, font, size, first_width, rest_width):
    """Wrap `text` where the first line is `first_width` wide and every
    following line is `rest_width` wide (hanging indent)."""
    words = text.split()
    if not words:
        return [""]
    lines, cur, width = [], words[0], first_width
    for w in words[1:]:
        trial = cur + " " + w
        if text_width(trial, font, size) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            width = rest_width
    lines.append(cur)
    return lines
