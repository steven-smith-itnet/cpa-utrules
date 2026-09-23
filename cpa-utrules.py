#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utah CPA Laws & Rules - Study Web App
=====================================
A zero-dependency (Python standard library only) local web app for studying for
the Utah CPA Law & Rules Examination (Title 58 Ch. 1 & 26a; R156-1 and
R156-26a).

Features
  - Landing page listing every study topic with live item counts, plus a
    "Documents & links" section linking every PDF in ./documents and every
    external page saved there as a .url shortcut.
  - Four mock exams: fixed 35-question papers on a 60-minute pausable clock,
    21 questions from the CPA Licensing Act and Rules and 14 from the DOPL Act
    and General Rules, scored against the 26 of 35 pass mark.
  - Two study modes:
      * Flashcards   - question on the front, flip for the answer and the exact
                       statutory or rule citation; mark each card known or
                       "review again" and the app remembers.
      * Quiz         - multiple choice with instant feedback, an end-of-quiz
                       score, and a one-click retry of only the missed items.
  - Filter a session by topic, cap its length, and search the whole bank.
  - Runs locally or on the LAN.

Content lives in content.py.  The single-page front end lives in index.html.
The official source documents and the combined reference PDF live in
./documents (see fetch_sources.py and build_reference.py).

Usage
  python3 cpa-utrules.py                 # http://localhost:8090 (this machine only)
  python3 cpa-utrules.py --lan           # http://<lan-ip>:8090  (whole LAN)
  python3 cpa-utrules.py --port 9000     # custom port
  python3 cpa-utrules.py --host 0.0.0.0  # explicit bind address
  python3 cpa-utrules.py --no-browser    # do not auto-open a browser
  python3 cpa-utrules.py --lan --log     # log every request with the client IP

DISCLAIMER: Study aid only. Verify every answer against the current official
Utah Code and Utah Administrative Code before relying on it.
"""

import argparse
import http.server
import json
import os
import posixpath
import socket
import socketserver
import threading
import time
import urllib.parse
import webbrowser

import content

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(HERE, "index.html")
DOCS_DIR = os.path.join(HERE, "documents")
REFERENCE_PDF = "Utah_CPA_Laws_and_Rules.pdf"
PORT = 8090

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def lan_addresses():
    """Every non-loopback IPv4 address this host answers on, best effort."""
    found = []
    # The address used to reach the outside world is the one that matters most.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        found.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127.") and addr not in found:
                found.append(addr)
    except OSError:
        pass
    return found or ["127.0.0.1"]


CATEGORY_ORDER = {"reference": 0, "official": 1, "other": 2, "link": 3}
MANIFEST = os.path.join(DOCS_DIR, "official", "manifest.json")


def read_url_shortcut(path):
    """Return the http(s) target of a Windows .url internet shortcut, or None.

    Other schemes (file:, javascript:, ...) are rejected - these end up as
    hyperlinks on a page served to the whole LAN.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if raw[:4].upper() == "URL=":
                    url = raw[4:].strip()
                    scheme = urllib.parse.urlparse(url).scheme.lower()
                    return url if scheme in ("http", "https") else None
    except OSError:
        return None
    return None


def official_source_urls():
    """file name -> upstream URL, from the manifest fetch_sources.py writes."""
    try:
        with open(MANIFEST, "r", encoding="utf-8") as fh:
            return {row["file"]: row.get("source")
                    for row in json.load(fh) if row.get("file")}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def list_documents():
    """Everything in ./documents worth linking to, grouped by provenance.

    Covers the two things that are actually openable - PDF files and .url
    internet shortcuts.  Extracted .txt sidecars are deliberately skipped.

    reference - the combined study PDF built by build_reference.py
    official  - the untouched State of Utah downloads in documents/official
    other     - any other PDF sitting in ./documents
    link      - an external URL saved as a .url shortcut
    """
    if not os.path.isdir(DOCS_DIR):
        return []
    sources = official_source_urls()
    docs = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for name in sorted(files):
            lower = name.lower()
            full = os.path.join(root, name)
            rel = os.path.relpath(full, DOCS_DIR).replace(os.sep, "/")

            if lower.endswith(".url"):
                url = read_url_shortcut(full)
                if not url:
                    continue
                docs.append({
                    "kind": "link",
                    "name": name[:-4].replace(" _ ", " - "),
                    "url": url,
                    "host": urllib.parse.urlparse(url).netloc,
                    "category": "link",
                    "primary": False,
                })
                continue

            if not lower.endswith(".pdf"):
                continue
            if name == REFERENCE_PDF and "/" not in rel:
                category = "reference"
            elif rel.startswith("official/"):
                category = "official"
            else:
                category = "other"
            docs.append({
                "kind": "pdf",
                "name": name,
                "path": "/documents/" + urllib.parse.quote(rel),
                "bytes": os.path.getsize(full),
                "category": category,
                "primary": category == "reference",
                "source": sources.get(name) if category == "official" else None,
            })
    docs.sort(key=lambda d: (CATEGORY_ORDER[d["category"]], d["name"].lower()))
    return docs


def safe_document_path(url_path):
    """Map /documents/<rel> onto a real file inside DOCS_DIR, or None."""
    rel = urllib.parse.unquote(url_path[len("/documents/"):])
    # Normalise on the URL side first so "..", "//" and backslashes cannot
    # escape the documents directory.
    rel = posixpath.normpath("/" + rel.replace("\\", "/")).lstrip("/")
    if not rel:
        return None
    full = os.path.realpath(os.path.join(DOCS_DIR, *rel.split("/")))
    root = os.path.realpath(DOCS_DIR)
    if full != root and not full.startswith(root + os.sep):
        return None
    return full if os.path.isfile(full) else None


def ufw_enabled():
    """True if ufw looks enabled on this host.

    Reading /etc/ufw/ufw.conf needs no privileges; the rule set itself
    (/etc/ufw/user.rules) is root-only, so we can warn but not verify that the
    port is actually open.  Returns None when ufw is not installed.
    """
    try:
        with open("/etc/ufw/ufw.conf", "r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if stripped.startswith("ENABLED="):
                    return stripped.split("=", 1)[1].strip().lower() == "yes"
    except OSError:
        return None
    return None


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # A classroom's worth of tablets hitting the LAN address at once should
    # not get connection-refused from a five-deep accept queue.
    request_queue_size = 64


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "cpa-utrules"
    access_log = False          # flipped on by --log

    def log_message(self, fmt, *args):
        """Quiet by default; with --log, one line per request showing who
        connected - which is what tells you whether a LAN client's request is
        arriving at all."""
        if not self.access_log:
            return
        print("  %s  %s  %s" % (time.strftime("%H:%M:%S"),
                                self.client_address[0].ljust(15),
                                fmt % args), flush=True)

    def log_error(self, fmt, *args):
        self.log_message(fmt, *args)

    def _send(self, code, body, content_type, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self._send(404, "Not Found", "text/plain; charset=utf-8")
            return
        self._send(200, body, ctype, {
            "Content-Disposition": 'inline; filename="%s"'
                                   % os.path.basename(path),
            "Cache-Control": "no-cache",
        })

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            try:
                with open(INDEX_HTML, "r", encoding="utf-8") as fh:
                    html = fh.read()
            except FileNotFoundError:
                self._send(500, "index.html not found next to cpa-utrules.py",
                           "text/plain; charset=utf-8")
                return
            self._send(200, html, "text/html; charset=utf-8")

        elif path == "/api/data":
            payload = json.dumps({
                "topics": content.TOPICS,
                "flashcards": content.FLASHCARDS,
                "quiz": content.QUIZ,
                "meta": {
                    "source": content.SOURCE_NOTE,
                    "documents": list_documents(),
                    "reference_pdf": "/documents/" + REFERENCE_PDF
                    if os.path.isfile(os.path.join(DOCS_DIR, REFERENCE_PDF))
                    else None,
                },
            })
            self._send(200, payload, "application/json; charset=utf-8")

        elif path == "/api/health":
            self._send(200, json.dumps({
                "ok": True,
                "flashcards": len(content.FLASHCARDS),
                "quiz": len(content.QUIZ),
                "topics": len(content.TOPICS),
            }), "application/json; charset=utf-8")

        elif path.startswith("/documents/"):
            full = safe_document_path(path)
            if full is None:
                self._send(404, "Not Found", "text/plain; charset=utf-8")
            else:
                self._send_file(full)

        else:
            self._send(404, "Not Found", "text/plain; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Utah CPA Laws & Rules study web app")
    parser.add_argument("--lan", action="store_true",
                        help="Serve on 0.0.0.0 so the app is reachable from "
                             "other devices on your network")
    parser.add_argument("--host", default=None,
                        help="Explicit bind address (overrides --lan)")
    parser.add_argument("--port", type=int, default=PORT,
                        help="Port to serve on (default %d)" % PORT)
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not auto-open a browser")
    parser.add_argument("--log", action="store_true",
                        help="Print one line per request, with the client's IP "
                             "(useful for diagnosing LAN access)")
    args = parser.parse_args()

    Handler.access_log = args.log

    bind_addr = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    serving_wide = bind_addr not in ("127.0.0.1", "localhost")
    addresses = lan_addresses() if serving_wide else ["localhost"]
    url = "http://%s:%d" % (addresses[0], args.port)

    try:
        content.validate()
    except AssertionError as exc:
        raise SystemExit("content.py failed validation: %s" % exc)

    try:
        server = ReusableTCPServer((bind_addr, args.port), Handler)
    except OSError as exc:
        raise SystemExit("cannot bind %s:%d - %s" % (bind_addr, args.port, exc))

    line = "=" * 68
    print(line)
    print("  Utah CPA Laws & Rules - Study Web App")
    print(line)
    print("  Flashcards: %d   |   Quiz questions: %d   |   Topics: %d"
          % (len(content.FLASHCARDS), len(content.QUIZ), len(content.TOPICS)))
    ref = os.path.join(DOCS_DIR, REFERENCE_PDF)
    if os.path.isfile(ref):
        print("  Reference:  /documents/%s (%.1f KB)"
              % (REFERENCE_PDF, os.path.getsize(ref) / 1024.0))
    else:
        print("  Reference:  not built yet - run "
              "'python3 fetch_sources.py && python3 build_reference.py'")
    print("  Bound to:   %s:%d" % (bind_addr, args.port))
    if serving_wide:
        print("  Open from any device on your network:")
        for addr in addresses:
            print("      http://%s:%d" % (addr, args.port))
        subnets = sorted({".".join(a.split(".")[:3]) + ".0/24"
                          for a in addresses if a.count(".") == 3})
        allow = ("sudo ufw allow from %s to any port %d proto tcp"
                 % (subnets[0] if subnets else "192.168.0.0/16", args.port))
        if ufw_enabled():
            print("")
            print("  !! ufw is enabled on this machine. Until the port is")
            print("     opened, other devices will time out. Run:")
            print("         %s" % allow)
        else:
            print("  If a client cannot connect, allow the port through this")
            print("  machine's firewall, e.g.:")
            print("         %s" % allow)
    else:
        print("  Local only: %s   (use --lan to share on your network)" % url)
    print("  Press Ctrl+C to stop.")
    print(line)

    if not args.no_browser and not serving_wide:
        threading.Thread(
            target=lambda: (time.sleep(0.6), webbrowser.open(url)),
            daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
