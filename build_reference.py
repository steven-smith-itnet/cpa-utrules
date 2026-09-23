#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_reference.py - assemble the official Utah CPA laws and rules into one PDF.

Inputs  : documents/official/*.pdf  (downloaded verbatim from le.utah.gov and
          adminrules.utah.gov - see fetch_sources.py)
Output  : documents/Utah_CPA_Laws_and_Rules.pdf

The official PDFs are text extracted with `pdftotext -layout` (poppler), which
is also what produces documents/official/*.txt.  If the .txt files are already
present this script needs no external tools at all.

    python3 build_reference.py
"""

import os
import re
import subprocess

import pdfgen

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "documents")
OFFICIAL = os.path.join(DOCS, "official")
OUT_PDF = os.path.join(DOCS, "Utah_CPA_Laws_and_Rules.pdf")

RETRIEVED = "August 9, 2026"

# (file stem, part title, short label, kind, source URL, currency note)
SOURCES = [
    ("Utah_Code_58-1",
     "Utah Code Title 58, Chapter 1 - Division of Professional Licensing Act",
     "Utah Code 58-1", "code",
     "https://le.utah.gov/xcode/Title58/Chapter1/58-1.html",
     "Official electronic Utah Code published by the Office of Legislative "
     "Research and General Counsel."),
    ("Utah_Code_58-26a",
     "Utah Code Title 58, Chapter 26a - Certified Public Accountant Licensing Act",
     "Utah Code 58-26a", "code",
     "https://le.utah.gov/xcode/Title58/Chapter26A/58-26a.html",
     "Official electronic Utah Code published by the Office of Legislative "
     "Research and General Counsel."),
    ("UAC_R156-1",
     "Utah Administrative Code R156-1 - General Rule of the Division of "
     "Professional Licensing",
     "R156-1", "rule",
     "https://adminrules.utah.gov/public/rule/R156-1/Current%20Rules",
     "Effective December 24, 2024."),
    ("UAC_R156-26a",
     "Utah Administrative Code R156-26a - Certified Public Accountant "
     "Licensing Act Rule",
     "R156-26a", "rule",
     "https://adminrules.utah.gov/public/rule/R156-26a/Current%20Rules",
     "Date of last change: July 8, 2026."),
]

# --------------------------------------------------------------------------
# Text extraction / cleanup
# --------------------------------------------------------------------------

CODE_SECTION = re.compile(r"^(58-\d+[a-z]?-\d+(?:\.\d+)?)\s+(.*)$")
RULE_SECTION = re.compile(r"^(R\d+-[\w.-]+?-[\w.]+)\.\s*(.*)$")
PART_HEAD = re.compile(r"^(Part|Chapter)\s+([\w.-]+)$", re.I)
ENACT = re.compile(r"^(Enacted|Amended|Renumbered|Repealed|Revisor)\b.*"
                   r"(Session|Instructions).*$")
# The Utah Code prints future/superseded versions of a section side by side,
# each introduced by an effective-date marker.
VERSION = re.compile(r"^(Effective|Superseded)\s+\d{1,2}/\d{1,2}/\d{4}\s*$")
NUMBERED = re.compile(r"^\((?:[0-9]{1,3}|[a-z]{1,3}|[A-Z]{1,3}|[ivxlIVXL]{1,6})\)")


def extract_text(stem):
    """Return the plain text of documents/official/<stem>.pdf."""
    txt_path = os.path.join(OFFICIAL, stem + ".txt")
    pdf_path = os.path.join(OFFICIAL, stem + ".pdf")
    if not os.path.exists(txt_path):
        if not os.path.exists(pdf_path):
            raise SystemExit("missing source: %s (run fetch_sources.py first)"
                             % pdf_path)
        try:
            subprocess.run(["pdftotext", "-layout", pdf_path, txt_path],
                           check=True)
        except (OSError, subprocess.CalledProcessError):
            raise SystemExit(
                "pdftotext (poppler-utils) is required the first time this "
                "runs, to extract text from %s" % pdf_path)
    with open(txt_path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _is_heading(title):
    """True if `title` looks like a section heading rather than a wrapped
    cross-reference that happens to begin with a section number."""
    title = title.strip()
    if not title or not title[0].isupper():
        return False
    first = title.split()[0].rstrip(",.;:")
    return first.lower() not in ("and", "or", "through", "of", "the", "as")


def clean_lines(raw, kind):
    """Drop page furniture and normalise whitespace, keeping indentation."""
    out = []
    for line in raw.replace("\f", "\n").split("\n"):
        line = line.replace("\t", "    ").rstrip()
        s = line.strip()
        if not s:
            out.append("")
            continue
        if kind == "code":
            if s == "Utah Code" or re.fullmatch(r"Page \d+", s):
                continue
        if re.fullmatch(r"-?\s*\d+\s*-?", s) and len(s) <= 5:
            continue
        out.append(line)
    return out


def paragraphs(lines, kind):
    """Group physical lines into logical paragraphs.

    Yields dicts: {"type": "section"|"part"|"note"|"body"|"table",
                   "text"/"lines", "indent"}
    """
    buf, buf_indent = [], 0
    table_mode, table_lines = False, []
    pending_version = []

    def flush():
        nonlocal buf, buf_indent
        if buf:
            text = " ".join(x.strip() for x in buf)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                yield_val = {"type": "body", "text": text, "indent": buf_indent}
                buf, buf_indent = [], 0
                return yield_val
            buf, buf_indent = [], 0
        return None

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        # --- the R156-26a-501 fine schedule is a real table; keep it fixed ---
        if s.startswith("TABLE ") or (table_mode and s):
            if not table_mode:
                got = flush()
                if got:
                    yield got
                table_mode, table_lines = True, []
            table_lines.append(line.strip("\n"))
            i += 1
            if i >= len(lines) or not lines[i].strip():
                yield {"type": "table", "lines": table_lines}
                table_mode = False
            continue

        if not s:
            got = flush()
            if got:
                yield got
            i += 1
            continue

        if VERSION.match(s):
            got = flush()
            if got:
                yield got
            pending_version.append(s)
            i += 1
            continue

        m_sec = (CODE_SECTION if kind == "code" else RULE_SECTION).match(s)
        if m_sec and not _is_heading(m_sec.group(2)):
            m_sec = None          # a wrapped citation, not a section heading
        m_part = PART_HEAD.match(s)

        if m_sec:
            got = flush()
            if got:
                yield got
            title = m_sec.group(2).strip()
            j = i + 1
            if kind == "code":
                # a code heading can run onto the next line at the same indent
                while (j < len(lines) and lines[j].strip()
                       and not NUMBERED.match(lines[j].strip())
                       and not CODE_SECTION.match(lines[j].strip())
                       and len(lines[j]) - len(lines[j].lstrip(" ")) <= indent + 1
                       and not ENACT.match(lines[j].strip())):
                    title += " " + lines[j].strip()
                    j += 1
            else:
                # a rule heading continues until the title reaches its period
                while (not title.rstrip().endswith(".")
                       and j < len(lines) and lines[j].strip()
                       and not NUMBERED.match(lines[j].strip())
                       and not RULE_SECTION.match(lines[j].strip())):
                    title += " " + lines[j].strip()
                    j += 1
            i = j
            title = re.sub(r"\s+", " ", title).strip().rstrip(".")
            if pending_version:
                title += " (%s)" % "; ".join(pending_version)
                pending_version = []
            yield {"type": "section", "num": m_sec.group(1), "title": title}
            continue

        if m_part and kind == "code":
            got = flush()
            if got:
                yield got
            label = s
            j = i + 1
            sub = lines[j].strip() if j < len(lines) else ""
            if sub and not NUMBERED.match(sub) and not CODE_SECTION.match(sub):
                label += " - " + sub
                j += 1
            i = j
            yield {"type": "part", "text": label}
            continue

        if ENACT.match(s):
            got = flush()
            if got:
                yield got
            yield {"type": "note", "text": s}
            i += 1
            continue

        if NUMBERED.match(s) or not buf:
            got = flush()
            if got:
                yield got
            buf_indent = indent
        buf.append(s)
        i += 1

    got = flush()
    if got:
        yield got


def indent_points(kind, indent_spaces, text):
    """Map source indentation to a rendered left indent, in points."""
    if kind == "code":
        base = max(0, indent_spaces - 4)
        return min(base, 26) * 5.4
    # Rule text is not reliably indented; derive depth from the numbering.
    m = re.match(r"^\(([0-9]{1,3}|[a-z]{1,3}|[A-Z]{1,3})\)", text)
    if not m:
        return 0.0
    tok = m.group(1)
    if tok.isdigit():
        return 0.0
    if tok.isupper():
        return 40.0
    if tok in ("ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii",
               "xiii", "xiv", "xv"):
        return 27.0
    if len(tok) == 1:
        return 13.5
    return 27.0


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build():
    doc = pdfgen.Document(
        title="Utah CPA Laws and Rules - Complete Reference",
        subject="Utah Code Title 58 Chapters 1 and 26a; Utah Administrative "
                "Code R156-1 and R156-26a",
        author="Compiled from official State of Utah sources",
        running_header="Utah CPA Laws & Rules - Complete Reference",
    )

    doc.cover([
        ("Utah CPA", "B", 30, 2),
        ("Laws & Rules", "B", 30, 16),
        ("Complete Reference for the Utah Laws and Rules Examination",
         "R", 13, 26),
        ("Utah Code Title 58, Chapter 1 - Division of Professional Licensing Act",
         "R", 10.5, 3),
        ("Utah Code Title 58, Chapter 26a - Certified Public Accountant "
         "Licensing Act", "R", 10.5, 3),
        ("Utah Administrative Code R156-1 and R156-26a",
         "R", 10.5, 30),
        ("Compiled verbatim from official State of Utah sources", "I", 9.5, 3),
        ("Retrieved " + RETRIEVED, "I", 9.5, 0),
    ])

    # ---- front matter ----------------------------------------------------
    doc.heading("About This Compilation", level=0, new_page=True)
    doc.para(
        "This document gathers, in one place, the primary legal authority "
        "tested by the Utah Laws and Rules Examination that every applicant "
        "for a Utah CPA license must pass. Nothing has been summarized, "
        "paraphrased or abridged: each part below is the full official text "
        "of the statute or rule as published by the State of Utah on the "
        "retrieval date shown on the cover.",
        space_after=8)
    doc.heading("Sources", level=1)
    for _stem, title, _label, _kind, url, note in SOURCES:
        doc.para(title, font="B", space_before=4, space_after=1)
        doc.para(url, font="I", indent=12, space_after=1)
        doc.para(note, indent=12, space_after=2)
    doc.spacer(8)
    doc.heading("How the two bodies of law fit together", level=1)
    doc.para(
        "Title 58, Chapter 1 (the Division of Professional Licensing Act) "
        "applies uniformly to every profession the Division regulates - "
        "boards, license terms, renewal, reinstatement, unlawful and "
        "unprofessional conduct, discipline and penalties. Chapter 26a is the "
        "CPA-specific practice act, and under Section 58-1-107 it supplements "
        "or alters Chapter 1 where the two differ. Rule R156-1 is the "
        "Division's general rule; R156-26a is the CPA-specific rule adopted "
        "under Subsection 58-1-106(1)(a).")
    doc.spacer(10)
    doc.heading("Disclaimer", level=1)
    doc.para(
        "This compilation is a study aid. The official, controlling versions "
        "of these materials are the electronic Utah Code published at "
        "le.utah.gov and the Utah Administrative Code published at "
        "adminrules.utah.gov. Both are amended regularly. Verify any provision "
        "you intend to rely on against the current official text.")

    doc.toc_placeholder()

    # ---- the law itself --------------------------------------------------
    for stem, title, label, kind, url, note in SOURCES:
        raw = extract_text(stem)
        lines = clean_lines(raw, kind)
        doc.heading(title, level=0, new_page=True)
        doc.para("Source: " + url, font="I", size=8.2, space_after=1)
        doc.para(note, font="I", size=8.2, space_after=6)
        doc.rule(space_before=0, space_after=8)

        for p in paragraphs(lines, kind):
            t = p["type"]
            if t == "part":
                doc.heading(p["text"], level=1)
            elif t == "section":
                doc.heading("%s. %s" % (p["num"], p["title"]),
                            level=2 if kind == "code" else 1)
            elif t == "note":
                doc.para(p["text"], font="I", size=8.4, indent=0,
                         space_before=2, space_after=8)
            elif t == "table":
                doc.pre([ln for ln in p["lines"]], size=7.2, indent=6)
            else:
                ind = indent_points(kind, p["indent"], p["text"])
                doc.para(p["text"], indent=ind, hang=13.0, space_after=1.6)

    n = doc.render(OUT_PDF)
    return n


def main():
    if not os.path.isdir(OFFICIAL):
        raise SystemExit("no documents/official directory - run "
                         "fetch_sources.py first")
    pages = build()
    size = os.path.getsize(OUT_PDF)
    print("Wrote %s" % os.path.relpath(OUT_PDF, HERE))
    print("  %d pages, %.1f KB" % (pages, size / 1024.0))


if __name__ == "__main__":
    main()
