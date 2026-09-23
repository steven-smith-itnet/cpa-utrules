#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_sources.py - download the official Utah CPA laws and rules.

Everything is pulled straight from the two authoritative State of Utah
publishers:

  * le.utah.gov         - the official electronic Utah Code, published by the
                          Office of Legislative Research and General Counsel.
                          Each chapter offers an official PDF download.
  * adminrules.utah.gov - the Utah Administrative Code (eRules), published by
                          the Office of Administrative Rules.  Its public API
                          exposes the current codified PDF for each rule.

Files land in documents/official/.  Run build_reference.py afterwards to
typeset them into the single combined study PDF.

    python3 fetch_sources.py
    python3 fetch_sources.py --check     # report what is on disk, download nothing
"""

import argparse
import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL = os.path.join(HERE, "documents", "official")

UA = "cpa-utrules study app (python-urllib)"
CODE_BASE = "https://le.utah.gov/xcode/Title58"
RULES_BASE = "https://adminrules.utah.gov"

# Utah Code chapters: (output stem, chapter path, chapter version id)
CODE_CHAPTERS = [
    ("Utah_Code_58-1", "Chapter1", "C58-1_1800010118000101"),
    ("Utah_Code_58-26a", "Chapter26A", "C58-26a_1800010118000101"),
]

# Utah Administrative Code rules: (output stem, rule number, eRules rule id).
# The numeric id is what /api/public/ruleversioninfo/<id> answers to; it is
# stable and is how the current codified PDF is located.
RULES = [
    ("UAC_R156-1", "R156-1", 250),
    ("UAC_R156-26a", "R156-26a", 263),
]


def get(url, binary=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", "replace")


def save(stem, data):
    path = os.path.join(OFFICIAL, stem + ".pdf")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def rule_info(rule_id):
    """Current-version metadata for an eRules rule, including its PDF path."""
    raw = get("%s/api/public/ruleversioninfo/%d" % (RULES_BASE, rule_id),
              binary=False)
    if not raw.strip():
        raise RuntimeError("eRules returned no version info for id %d" % rule_id)
    return json.loads(raw)


def fetch_all():
    os.makedirs(OFFICIAL, exist_ok=True)
    manifest = []

    for stem, chapter, version in CODE_CHAPTERS:
        url = "%s/%s/%s.pdf" % (CODE_BASE, chapter, version)
        print("Utah Code  %-22s <- %s" % (stem, url))
        data = get(url)
        if not data.startswith(b"%PDF"):
            raise RuntimeError("not a PDF: %s" % url)
        save(stem, data)
        manifest.append({"file": stem + ".pdf", "source": url,
                         "publisher": "le.utah.gov (Office of Legislative "
                                      "Research and General Counsel)"})

    for stem, number, rule_id in RULES:
        info = rule_info(rule_id)
        if info.get("referenceNumber") != number:
            raise RuntimeError("eRules id %d is %s, expected %s"
                               % (rule_id, info.get("referenceNumber"), number))
        pdf_path = info["pdfDownload"]
        url = "%s/api/public/getfile/%s/%s" % (
            RULES_BASE, pdf_path.replace("/", "%2F"), info["pdfDownloadName"])
        print("Admin Rule %-22s <- %s  (effective %s)"
              % (stem, number, info.get("effectiveDate", "?")))
        data = get(url)
        if not data.startswith(b"%PDF"):
            raise RuntimeError("not a PDF: %s" % url)
        save(stem, data)
        manifest.append({
            "file": stem + ".pdf",
            "source": "%s/public/rule/%s/Current%%20Rules" % (RULES_BASE, number),
            "publisher": "adminrules.utah.gov (Office of Administrative Rules)",
            "effective_date": info.get("effectiveDate"),
            "rule_name": info.get("name"),
        })

    with open(os.path.join(OFFICIAL, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print("\nSaved %d documents to %s"
          % (len(manifest), os.path.relpath(OFFICIAL, HERE)))
    print("Next: python3 build_reference.py")


def check():
    if not os.path.isdir(OFFICIAL):
        print("documents/official does not exist yet")
        return
    for name in sorted(os.listdir(OFFICIAL)):
        path = os.path.join(OFFICIAL, name)
        print("  %-28s %8.1f KB" % (name, os.path.getsize(path) / 1024.0))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--check", action="store_true",
                    help="list what is already downloaded and exit")
    args = ap.parse_args()
    if args.check:
        check()
        return
    try:
        fetch_all()
    except (urllib.error.URLError, RuntimeError) as exc:
        raise SystemExit("download failed: %s" % exc)


if __name__ == "__main__":
    main()
