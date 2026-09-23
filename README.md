# Introduction & Who this is for

I built this for friends and colleagues who were either earning or recertifying their CPAs. This is specifically for the Utah Rules & Laws exam. 
NOTE: I AM NOT A CPA, just a nerd who did a bit of vibe-coding and general RAG-based AI rulesets to develop study material (flash cards, practice tests, etc.). 

# cpa-utrules

A zero-dependency (Python standard library only) **web app** for studying the
**Utah CPA Laws and Rules Examination**, together with a build pipeline that
downloads the governing law straight from the State of Utah and typesets it
into a single reference PDF.

## What is in here

| Piece | What it does |
|---|---|
| **Study app** | 305 flashcards and 258 multiple-choice questions across 16 topics, every one carrying its exact statutory or rule citation |
| **Mock exams** | Four fixed 35-question papers built to the published exam blueprint - 21 CPA Licensing Act and Rules, 14 DOPL Act and General Rules - on a 60-minute pausable clock |
| **Reference PDF** | All four governing authorities compiled verbatim into one bookmarked, 102-page PDF with a full table of contents |
| **Source pipeline** | `fetch_sources.py` pulls the official documents; `build_reference.py` typesets them; `pdfgen.py` is a small pure-Python PDF writer |

## The law it covers

Everything is written against the current official text, retrieved
**August 9, 2026**:

- **Utah Code Title 58, Chapter 1** – Division of Professional Licensing Act
- **Utah Code Title 58, Chapter 26a** – Certified Public Accountant Licensing Act
- **Utah Admin. Code R156-1** – General Rule of the Division (eff. 12/24/2024)
- **Utah Admin. Code R156-26a** – CPA Licensing Act Rule (last changed **7/8/2026**)

> R156-26a was substantially rewritten effective July 8, 2026. The education,
> CPE, peer review and reinstatement content here follows that current text.
> Material based on older versions of the rule is out of date.

Sources: [le.utah.gov](https://le.utah.gov/xcode/Title58/Chapter26A/58-26a.html)
(official electronic Utah Code) and
[adminrules.utah.gov](https://adminrules.utah.gov/public/rule/R156-26a/Current%20Rules)
(Utah Administrative Code).

## Study topics

Definitions & Key Terms · Division, Director & Board of Accountancy · Education
Requirements · Experience Requirements · Examinations · Licensure, Renewal &
Reinstatement · Firm Registration, Ownership & Names · Mobility & Exemptions ·
Continuing Professional Education · Peer Review & Quality Control · Unlawful
Conduct & Penalties · Unprofessional Conduct & Discipline · Independence,
Commissions & Contingent Fees · Working Papers, Confidentiality & Privity ·
Investigations & Adjudicative Procedure · Professional Ethics (AICPA Code)

## Features

- **Mock exams** - four numbered papers on the landing page, each a fixed
  35-question sitting matching the blueprint of the real examination: 21
  questions from the CPA Licensing Act and Rules (Title 58 Ch. 26a and
  R156-26a) and 14 from the DOPL Act and General Rules (Title 58 Ch. 1 and
  R156-1), one hour, 26 of 35 to pass. A countdown clock sits at the top with a
  start/pause toggle - pausing stops the clock and hides the questions - and the
  paper is submitted automatically when time runs out. No feedback is given
  until submission; the result then breaks the score down by domain, lists every
  question with the correct answer and explanation, and flags each miss for
  review. The papers are generated from a fixed seed, so Mock Exam 2 is the same
  paper every time and no question appears on two of the four.
- **Flashcards** – question on the front, flip for the answer and the exact
  citation. Mark each card *known* or *review again*; the marks persist in the
  browser and can drive a "review only" session.
- **Multiple-choice quiz** – instant feedback with an explanation, an
  end-of-quiz score against the 75% pass mark, and one-click retry of only the
  questions you missed. Missed questions are auto-flagged for review.
- **Documents & links** – a permanent section on the landing page listing
  everything openable in `./documents`: the combined reference PDF, each
  official source (with a link back to its upstream page), every other study
  PDF, and each external page saved as a `.url` shortcut. Extracted `.txt`
  sidecars are omitted.
- **Topic filters, session length caps (10/25/50/all), and full-text search**
  across questions, answers and citations.
- **Keyboard shortcuts** – Space to flip, ←/→ to navigate, `K` known, `J`
  review; `1`–`4` or `A`–`D` to answer and Enter to advance in the quiz. In a
  mock exam, `1`–`4`/`A`–`D` answer, ←/→ move between questions, Enter advances
  and Space pauses or resumes the clock.

## Requirements

- Python 3 (standard library only — no `pip install`).
- `pdftotext` (poppler-utils) is needed **only** the first time
  `build_reference.py` runs, to extract text from the downloaded PDFs. The
  extracted `.txt` files are committed alongside the PDFs, so a fresh clone can
  rebuild without it.

## Run

```bash
# Local only (auto-opens your browser): http://localhost:8090
python3 cpa-utrules.py

# Reachable from every device on your LAN
python3 cpa-utrules.py --lan

# Custom port / explicit bind address / no browser
python3 cpa-utrules.py --port 9000
python3 cpa-utrules.py --host 0.0.0.0
python3 cpa-utrules.py --no-browser
```

`Ctrl+C` stops the server.

### LAN access

`--lan` binds `0.0.0.0` and prints every address the app is reachable on, for
example `http://<host-ip>:8090`. Any client on that subnet can open it in a
browser — no install on the client side.

**If this host runs a firewall, open the port first.** With `ufw` on the
`<your-subnet>` subnet:

```bash
sudo ufw allow from <your-subnet> to any port 8090 proto tcp
```

The app detects an enabled `ufw` at startup and prints the exact command for
your subnet. It cannot read the rule set itself (that file is root-only), so it
warns rather than confirms.

To sanity-check reachability from another machine:

```bash
curl http://<host-ip>:8090/api/health
```

## Refreshing the law

```bash
python3 fetch_sources.py      # download the current official PDFs
python3 build_reference.py    # typeset them into one study PDF
```

`fetch_sources.py` writes `documents/official/` plus a `manifest.json`
recording each file's source URL, publisher and effective date, and prints the
effective date of each rule as it downloads — an easy way to notice that a rule
has been amended since the content was last reviewed.

`build_reference.py` produces `documents/Utah_CPA_Laws_and_Rules.pdf` with a
cover page, provenance notes, a generated table of contents, per-section PDF
bookmarks and running page numbers.

## Project layout

| File | Purpose |
|---|---|
| `cpa-utrules.py` | Web server / entry point (UI, `/api/data`, `/api/health`, `/documents/*`) |
| `content.py` | Topics, flashcards, quiz questions, and a `validate()` self-check |
| `index.html` | Single-page front end |
| `fetch_sources.py` | Downloads the official Utah Code chapters and Admin. Code rules |
| `build_reference.py` | Parses the official text and typesets the combined PDF |
| `pdfgen.py` | Minimal dependency-free PDF writer (base-14 fonts, wrapping, TOC, bookmarks) |
| `documents/` | The combined reference PDF, `official/` sources, and legacy study PDFs |

Run `python3 content.py` to validate the content bank and print per-topic counts.

The mock exam bank needs at least 84 questions citing Title 58 Ch. 26a or
R156-26a and 56 citing Title 58 Ch. 1 or R156-1 to fill four non-overlapping
papers; it currently holds 144 and 114.

## Disclaimer

Study aid only. The controlling texts are the official Utah Code at
**le.utah.gov** and the Utah Administrative Code at **adminrules.utah.gov**,
both of which are amended regularly. Verify every answer against the current
official text before relying on it.
