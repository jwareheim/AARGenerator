# Stellaris AAR Tool — Design Document

**Project:** Chronicle  
**Version:** 0.4  
**Status:** Pre-development  
**License:** MIT  
**Repository:** github.com/[username]/chronicle  

---

## 1. Overview

Chronicle is an open-source, locally-run After Action Report (AAR) builder for Stellaris. Players upload their `.sav` files incrementally as they play, and the tool automatically generates narrative prose chapters by diffing each new save against the previous one. The result is a living, chapter-by-chapter story of their campaign that grows alongside the game.

No manual event entry. No notes. No build step. No package manager. Just run one Python file.

Chronicle is distributed as a **single `chronicle.py` file**. On first run it checks for and installs its own dependencies, starts a local HTTP server, and opens the browser automatically. The UI is a plain HTML/JS page embedded directly in the script.

---

## 2. Goals

- **Single file** — one `.py` file is the entire application; easy to download and share
- **Self-installing** — auto-installs missing pip packages on first run, no manual setup
- **Zero friction** — drop in a save file, get a readable chapter in under 60 seconds
- **Narrative quality** — chapters read like fiction, not a stats printout
- **Incremental** — each session produces a new chapter, building a cohesive arc
- **Persistent** — all data stored on disk in a `chronicle_data/` folder next to the script
- **Local-first** — nothing leaves the machine except the Anthropic API call
- **Community-friendly** — MIT licensed, well-documented, easy to fork and extend

---

## 3. Repository Structure

```
chronicle/                        ← GitHub repository root
│
├── chronicle.py                  ← THE application (single file)
│
├── README.md                     ← Quick start, features, screenshots
├── CONTRIBUTING.md               ← How to contribute
├── LICENSE                       ← MIT
├── CHANGELOG.md                  ← Version history
├── .gitignore                    ← Excludes chronicle_data/, __pycache__, etc.
│
├── docs/
│   ├── design.md                 ← This document
│   ├── save-format.md            ← Notes on Clausewitz format + what we extract
│   └── screenshots/              ← UI screenshots for README
│
└── tests/
    ├── fixtures/
    │   └── sample.sav            ← Anonymized/minimal test save file
    ├── test_parser.py            ← Unit tests for save parsing + extraction
    ├── test_diff.py              ← Unit tests for snapshot diffing
    └── test_prompt.py            ← Unit tests for prompt building
```

**What is NOT in the repo:**
- `chronicle_data/` — all user campaign data lives here locally, gitignored
- Any API keys
- Any personal save files

### 3.1 .gitignore

```gitignore
# Chronicle user data — never commit this
chronicle_data/

# Python
__pycache__/
*.pyc
*.pyo
.env

# OS
.DS_Store
Thumbs.db
```

---

## 4. User Flow

```
First time ever:
  python chronicle.py
  └── Checks for anthropic, clausewizard
      └── Missing? pip-installs them automatically
          └── Starts HTTP server on localhost:8765
              └── Opens browser automatically
                  └── Prompts for ANTHROPIC_API_KEY (saved to chronicle_data/config.json)
                      └── Ready — drop in first .sav file

First session:
  Drop .sav file onto the upload zone
  └── Server unzips → parses gamestate → extracts empire profile + state
      └── Claude generates Chapter 1 (origin / who this empire is)
          └── Chapter + snapshot written to chronicle_data/
              └── Chapter displayed in browser

Every subsequent session:
  python chronicle.py  (browser opens, existing AAR loads automatically)
  └── Drop in new .sav file
      └── Server parses → diffs against saved baseline snapshot
          └── Delta extracted (wars, deaths, colonization, tech, diplomacy...)
              └── Claude generates next chapter covering that period
                  └── Chapter written to disk, new baseline saved
                      └── Chapter displayed, appended to chapter list

At any time:
  └── Read any chapter
  └── Edit chapter titles
  └── Export full AAR as Markdown
```

---

## 5. Architecture

### 5.1 Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Runtime | Python 3.8+ | Standard install on most machines |
| HTTP Server | `http.server` + `socketserver.ThreadingMixIn` (stdlib) | No framework needed |
| Save Unzipping | `zipfile` (stdlib) | Built-in ZIP support |
| Save Parsing | `clausewizard` (pip) | Clausewitz format → Python dict/JSON |
| AI Generation | `anthropic` (pip) | `claude-sonnet-4-20250514`, streaming |
| Persistence | JSON files on disk (stdlib `json`) | `chronicle_data/` next to the script |
| UI | Plain HTML + vanilla JS | Embedded as a Python string in the script |
| Styling | Inline CSS in the embedded HTML | No build step, no CDN dependency |

**Total pip dependencies: 2** — `anthropic` and `clausewizard`. Everything else is stdlib.

### 5.2 Single-File Layout

The entire application lives in `chronicle.py`, structured in logical sections:

```
chronicle.py
│
├── [1] DEPENDENCY BOOTSTRAP
│     check_and_install_deps()
│     — runs before anything else
│     — pip-installs anthropic + clausewizard if missing
│
├── [2] IMPORTS
│     stdlib + conditionally-imported pip packages
│
├── [3] CONFIGURATION & CONSTANTS
│     PORT, DATA_DIR, paths, version
│
├── [4] STORAGE LAYER
│     load_meta(), save_meta()
│     load_baseline(), save_baseline()
│     load_summary(), save_summary()
│     load_chapter(n), save_chapter(n)
│     list_chapters()
│
├── [5] SAVE PARSER
│     parse_save(file_bytes) -> snapshot dict
│     extract_relevant_data(raw_parsed) -> curated snapshot
│     — unzip, clausewizard parse, field extraction
│
├── [6] DIFF ENGINE
│     diff_snapshots(baseline, current) -> list of delta events
│
├── [7] PROMPT BUILDER
│     build_origin_prompt(snapshot) -> str
│     build_chapter_prompt(n, delta, snapshot, summary) -> str
│     build_summary_update_prompt(chapter_prose, current_summary) -> str
│
├── [8] CLAUDE API
│     generate_chapter(prompt) -> generator (streamed text chunks)
│     update_summary(chapter_prose, current_summary) -> str
│
├── [9] HTTP REQUEST HANDLER
│     class ChronicleHandler(BaseHTTPRequestHandler)
│     — GET  /                     → serve embedded HTML
│     — GET  /api/chapters         → list chapters
│     — GET  /api/chapters/<n>     → get chapter
│     — POST /api/upload           → parse save, diff, stream chapter
│     — POST /api/chapters/<n>/title      → update title
│     — POST /api/chapters/<n>/regenerate → re-generate
│     — GET  /api/export           → full AAR as .md download
│     — POST /api/config           → save API key
│     — DELETE /api/reset          → wipe chronicle_data/
│
├── [10] EMBEDDED UI
│     HTML_PAGE = """<!DOCTYPE html>..."""
│     — full single-page app as a Python string
│     — upload zone, chapter sidebar, reading panel
│     — vanilla JS fetch calls to /api/* routes
│     — SSE handling for streamed chapter generation
│
└── [11] ENTRYPOINT
      main()
      — run bootstrap
      — create chronicle_data/ if needed
      — check for API key, prompt if missing
      — start ThreadingMixIn TCPServer
      — open browser (webbrowser.open)
      — serve forever
```

### 5.3 Runtime File Layout

```
chronicle.py                  ← the one file you run (checked into git)

chronicle_data/               ← auto-created on first run (gitignored)
├── config.json               ← API key, user preferences
├── meta.json                 ← campaign metadata
├── baseline.json             ← extracted snapshot from most recent save
├── summary.json              ← rolling narrative summary
└── chapters/
    ├── chapter-001.json
    ├── chapter-002.json
    └── ...
```

### 5.4 Request Flow — Save Upload

```
Browser: drag .sav onto upload zone
         │
         ▼
POST /api/upload  (multipart form data)
         │
         ▼
parse_save(file_bytes)
  zipfile.ZipFile → extract "meta" + "gamestate" text
  ClauseWizard.cwparse(gamestate) → token list
  extract_relevant_data(tokens) → curated ~50KB snapshot dict
         │
         ▼
diff_snapshots(load_baseline(), snapshot)
  → list of delta events sorted by significance
  (empty list if this is chapter 1)
         │
         ▼
build_prompt(chapter_number, delta, snapshot, summary)
         │
         ▼
generate_chapter(prompt)
  anthropic.Anthropic().messages.stream(...)
         │  streamed chunks
         ▼
HTTP response: text/event-stream (SSE)
  browser receives chunks → renders prose word by word
         │  (after stream completes)
         ▼
save_chapter(n, prose)
update_summary(prose, current_summary)  ← second API call, non-streamed
save_baseline(snapshot)
         │
         ▼
Browser: chapter appears in sidebar, reading panel updates
```

---

## 6. Dependency Bootstrap

This runs at the very top of `chronicle.py`, before any imports of pip packages:

```python
import sys
import subprocess

REQUIRED = {
    "anthropic": "anthropic",       # import name : pip package name
    "ClauseWizard": "clausewizard",
}

def check_and_install_deps():
    missing = []
    for import_name, pip_name in REQUIRED.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append((import_name, pip_name))

    if not missing:
        return  # all good

    print("Chronicle: installing missing dependencies...")
    for import_name, pip_name in missing:
        print(f"  Installing {pip_name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  ✓ {pip_name} installed")

    print("Dependencies ready.\n")

check_and_install_deps()

# Now safe to import pip packages
import anthropic
import ClauseWizard
```

**Behavior:**
- Already installed → zero output, zero delay
- Missing → prints brief status per package, installs silently, continues
- pip fails (no internet, permissions) → raises with a clear message pointing to manual install instructions in the README

---

## 7. API Key Handling

Chronicle never hardcodes or commits API keys. Priority order:

1. `ANTHROPIC_API_KEY` environment variable (takes precedence — good for power users)
2. `chronicle_data/config.json` (set via the in-browser settings screen on first run)

On first launch with no key present, the browser shows a setup screen before the main UI. The key is stored locally and never logged or transmitted anywhere except the Anthropic API endpoint.

```json
// chronicle_data/config.json (gitignored)
{
  "api_key": "sk-ant-...",
  "model": "claude-sonnet-4-20250514",
  "chapter_word_target": 500
}
```

**Security note for the README:** Users should never share their `chronicle_data/config.json` or commit it to any fork/branch. The `.gitignore` covers this for the standard setup.

---

## 8. Save File Parsing

### 8.1 File Format

Stellaris `.sav` files are ZIP archives containing two plain-text files:

- `meta` — lightweight: empire name, player ID, game date, ironman flag, patch version
- `gamestate` — heavyweight: full game state in Clausewitz script format (can exceed 200MB late game)

### 8.2 Parsing with ClauseWizard

```python
import zipfile, io, json
import ClauseWizard

def parse_save(file_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        meta_text = zf.read("meta").decode("utf-8", errors="replace")
        gamestate_text = zf.read("gamestate").decode("utf-8", errors="replace")

    meta_tokens = ClauseWizard.cwparse(meta_text)
    meta = json.loads(ClauseWizard.cwformat(meta_tokens))

    gamestate_tokens = ClauseWizard.cwparse(gamestate_text)
    raw = json.loads(ClauseWizard.cwformat(gamestate_tokens))

    return extract_relevant_data(raw, meta)
```

### 8.3 Data Extraction

`extract_relevant_data()` pulls only what Claude needs, discarding the vast majority of the gamestate:

**Empire Profile** (first save; re-checked each upload for changes)
```
- empire name, adjective
- species name, portrait class, traits
- ethics (list), civics (list), authority type
- home planet name, home system name
- origin
- patch version (for compatibility warnings)
```

**Current State** (captured per save, stored as baseline)
```
- in-game date
- owned planet names + count
- total pop count
- fleet power (raw — translated to narrative scale in prompt)
- monthly energy/mineral/alloy income
- active traditions list
- ascension perks list
- current ruler: name, traits, age, gender
- all leaders: name, class, traits, age
- active wars: name, attacker, defender, war goal, start date, warscore
- federation: name, members, our role
- subjects: names, subject type
- rivals + allies
- last 10 researched technologies
```

### 8.4 Large Save Handling

Late-game saves can exceed 200MB. Mitigations:

- `zipfile` reads gamestate into a string buffer rather than loading the full ZIP archive into memory at once
- `extract_relevant_data()` accesses only named top-level keys and discards the rest immediately
- The server sends a status SSE event to the browser if parse time exceeds 5 seconds ("Still parsing large save...")
- Extracted snapshot is typically under 100KB regardless of save size

### 8.5 Delta / Diff Detection

`diff_snapshots(baseline, current)` compares field by field and returns a sorted list of delta events:

| Delta Type | Detection Method |
|---|---|
| War started | War ID in `current.wars` not in `baseline.wars` |
| War ended | War ID in `baseline.wars` absent from `current.wars` |
| Planet colonized | Planet name in `current.planets` not in `baseline.planets` |
| Planet lost | Planet name in `baseline.planets` absent from `current.planets` |
| Leader died | Leader ID in `baseline.leaders` absent from `current.leaders` |
| Ruler changed | `current.ruler.name != baseline.ruler.name` |
| Ascension perk taken | Perk in `current.perks` not in `baseline.perks` |
| Tech researched | Tech in `current.recent_techs` not in `baseline.recent_techs` |
| Federation joined/left | Federation membership changed |
| Subject gained/lost | Subject list changed |
| Date delta | Always included |

Deltas are sorted by narrative weight before being passed to the prompt builder (wars first, deaths second, territorial changes third, tech/perks last).

---

## 9. AI Narrative Generation

### 9.1 Streaming via SSE

Chronicle uses the Anthropic streaming API. The HTTP handler writes chunks as Server-Sent Events so the browser renders prose word-by-word as it arrives:

```python
def handle_upload(self, file_bytes):
    # ... parse save, build prompt ...
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.end_headers()

    with anthropic.Anthropic(api_key=api_key).messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    ) as stream:
        full_text = ""
        for text_chunk in stream.text_stream:
            full_text += text_chunk
            self.wfile.write(
                f"data: {json.dumps({'chunk': text_chunk})}\n\n".encode()
            )
            self.wfile.flush()

    save_chapter(chapter_num, full_text)
    new_summary = update_summary(full_text, load_summary())
    save_summary(new_summary)
    save_baseline(snapshot)
    self.wfile.write(b"data: {\"done\": true}\n\n")
```

### 9.2 System Prompt

```
You are a science fiction author writing an After Action Report for a
Stellaris campaign. Write in the style of a sweeping historical chronicle
— dramatic, with a sense of destiny unfolding. Use the empire's ethics
and civics to inform the narrative voice. Never reference game mechanics
directly ("fleet power", "energy credits", "alloys") — translate
everything into in-universe language. Write in past tense. Be vivid but
concise.
```

### 9.3 Chapter 1 Prompt (Origin)

```
Write Chapter 1 of this AAR. This is the origin — establish who this
empire is, their home, their character, and the galaxy they are about
to enter. 400–600 words.

EMPIRE
Name: {empire_name}
Species: {species_name} ({portrait_class})
Traits: {species_traits}
Ethics: {ethics}
Civics: {civics}
Authority: {authority}
Origin: {origin}
Home: {home_planet}, {home_system} system

STATE — {date}
Planets: {planet_count} ({planet_names})
Ruler: {ruler_name}, {ruler_traits}
Leaders: {leaders_summary}
```

### 9.4 Subsequent Chapter Prompt

```
Story so far:
{rolling_summary}

Write Chapter {n} of this AAR, covering {date_from} to {date_to}
({years_elapsed} years). Focus on what changed — do not recap the
empire's full state. Weave these events into a cohesive narrative:

EVENTS THIS PERIOD:
{delta_events_formatted}

EMPIRE AT END OF PERIOD:
Planets: {count} | Ruler: {ruler} | {brief_state}

400–700 words. End with a sentence or two that looks forward.
```

### 9.5 Rolling Summary Update

After each chapter, a second non-streamed call compresses the narrative history:

```
Update the running story summary to incorporate the new chapter below.
Total summary must stay under 250 words. Return only the updated
summary text, nothing else.

NEW CHAPTER:
{chapter_prose}

CURRENT SUMMARY:
{current_summary}
```

---

## 10. Persistent Storage Schema

All data written to `chronicle_data/` as plain JSON (human-readable, easy to back up or share).

**`config.json`** — gitignored, never shared
```json
{
  "api_key": "sk-ant-...",
  "model": "claude-sonnet-4-20250514",
  "chapter_word_target": 500
}
```

**`meta.json`**
```json
{
  "empire_name": "Keth Dominion",
  "species_name": "Keth",
  "start_date": "2200.01.01",
  "chapter_count": 3,
  "created_at": "2026-04-28T12:00:00Z",
  "last_updated": "2026-04-28T18:00:00Z"
}
```

**`baseline.json`** — full extracted snapshot from most recent save.

**`summary.json`**
```json
{
  "text": "The Keth Dominion emerged from Keth Prime under Emperor Vorlan I...",
  "updated_at": "2026-04-28T18:00:00Z",
  "chapters_covered": 3
}
```

**`chapters/chapter-001.json`**
```json
{
  "id": 1,
  "title": "The Long War",
  "date_from": "2287.01.01",
  "date_to": "2310.06.15",
  "prose": "Thirty-one years had passed since...",
  "word_count": 512,
  "delta_events": ["War declared against Zroni Remnants", "..."],
  "generated_at": "2026-04-28T18:00:00Z"
}
```

Chapter files are zero-padded (`chapter-001`, `chapter-002`) so directory listings sort correctly.

---

## 11. Embedded UI

The UI is a single HTML page embedded as a Python triple-quoted string and served from the `/` route. It uses no external CDN dependencies except Google Fonts — all logic is inline vanilla JS.

### 11.1 Layout

```
┌──────────────────────────────────────────────────────────────┐
│  ✦ CHRONICLE                    [Export .md]  [⚙ Settings]  │
├───────────────┬──────────────────────────────────────────────┤
│               │                                              │
│ Keth Dominion │  Chapter 3: The Long War                    │
│ ─────────────│  2287 – 2310  ·  512 words                  │
│               │                                              │
│ Ch.1  2200   │  Thirty-one years had passed since the      │
│ Ch.2  2263   │  fleets of the Keth Dominion first crossed  │
│ Ch.3  2310 ◀ │  the Outer Veil...                          │
│               │                                              │
│ ─────────────│                                              │
│               │                                              │
│ [↑ Upload     │              [✎ Edit Title]  [↺ Regenerate]│
│  New Save]   │                                              │
│ 3 ch · 1842w │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

### 11.2 Visual Direction

- **Theme:** Dark — near-black background (`#0b0c12`), warm off-white prose text
- **Reading panel:** Slightly lighter (`#12141e`), generous line-height (1.85), ~65ch measure
- **Fonts:** `Cinzel` for headings, `Lora` for prose body (Google Fonts)
- **Accent:** Amber-gold `#c9a84c` for active states, buttons, highlights
- **No dashboards** — this is a reading experience, not an analytics tool

---

## 12. OSS-Specific Considerations

### 12.1 README Contents

The README should include:

- One-line description + screenshot of the UI
- Prerequisites (Python 3.8+, Anthropic API key)
- Quickstart (literally `python chronicle.py`)
- How to get an Anthropic API key (link to console.anthropic.com)
- How incremental saves work
- Known limitations (ironman saves, event gaps, mod compatibility)
- Contributing section (link to CONTRIBUTING.md)
- License badge

### 12.2 CONTRIBUTING.md

Should cover:

- How the single-file structure is organized (section map)
- How to run tests (`python -m pytest tests/`)
- The philosophy: keep it a single file, keep pip deps to a minimum
- How to submit a PR (fork → branch → PR against `main`)
- Issue templates: bug report, feature request

### 12.3 Test Fixtures

The `tests/fixtures/` directory should contain a minimal anonymized `.sav` file — small enough to commit to git (ideally under 1MB), sufficient to exercise the parser and diff logic. This means either a very early-game save or a manually trimmed one. Document how it was produced in `docs/save-format.md`.

### 12.4 GitHub Actions CI

A minimal CI workflow (`.github/workflows/ci.yml`) that runs on every PR:

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install anthropic clausewizard pytest
      - run: python -m pytest tests/ -v
```

Note: tests that call the Anthropic API should be mocked. No `ANTHROPIC_API_KEY` secret needed in CI.

### 12.5 Versioning

Use `MAJOR.MINOR.PATCH` semantic versioning. The version string is defined as a constant at the top of `chronicle.py`:

```python
__version__ = "0.1.0"
```

It's displayed in the UI footer and in the terminal on startup. GitHub Releases are used for tagged versions; `CHANGELOG.md` is updated with each release.

### 12.6 Issue Labels

Suggested label set for the repo:

| Label | Use |
|---|---|
| `bug` | Something broken |
| `enhancement` | New feature request |
| `parser` | Clausewitz parsing issues |
| `mod-compat` | Problems with modded saves |
| `good first issue` | Small, well-scoped, beginner-friendly |
| `help wanted` | Good for community contribution |

### 12.7 License

MIT. Short, permissive, standard for community tools. Include the full `LICENSE` file in the repo root. Add the license header as a comment block at the top of `chronicle.py`:

```python
# Chronicle — Stellaris AAR Generator
# https://github.com/[username]/chronicle
# MIT License — see LICENSE for details
```

---

## 13. Error Handling

| Scenario | Server response | UI display |
|---|---|---|
| Non-`.sav` file uploaded | 400 | "This doesn't look like a Stellaris save file." |
| Ironman save detected | 422 | "Ironman saves aren't supported yet. See the README." |
| Save from different empire | 409 | "Empire mismatch — start a new campaign or override?" |
| Save older than baseline | 409 | "This save appears to predate your last upload." |
| Parse failure | 500 | "Couldn't parse this save — is it from a heavily modded game?" |
| Anthropic API error | 502 | "Generation failed." + Retry button |
| Missing API key | 401 | Redirected to settings/setup screen |
| Disk write failure | 500 | Chapter prose shown in UI for manual copy |
| pip bootstrap failure | Terminal exit | Clear message + link to manual install instructions in README |

---

## 14. Limitations & Known Constraints

**Event gaps between saves.** Stellaris saves record current state only. If a war starts and ends between two uploads, it won't appear in the diff. Note this in the README; encourage saving at key moments.

**Ironman saves.** Ironman mode uses a different encoding. Out of scope for Phase 1; tracked as a future enhancement issue.

**Mod compatibility.** Custom civics, traits, or species classes from mods may appear as unrecognized IDs. `extract_relevant_data()` handles unknown values gracefully with fallback strings rather than crashing. Document known mod limitations in the README.

**ClauseWizard patch compatibility.** The library is several years old. Chronicle should log the save's patch version and warn if it's newer than last tested. This is a known risk worth calling out in the README so the community can report breakage.

**Parse performance.** Very large late-game saves may take 30–60 seconds to parse. The streaming status SSE prevents the UI from appearing frozen.

**Single campaign.** `chronicle_data/` holds one campaign at a time. Starting a new campaign requires using Reset. Multi-campaign support is a Phase 4 item.

**Google Fonts.** The embedded UI links Google Fonts for typography. Requires internet on first load; cached by browser thereafter. Offline fallback is system serif — this is fine for most users.

---

## 15. Phased Roadmap

### Phase 1 — MVP
- `check_and_install_deps()` bootstrap
- API key prompt + `config.json` storage
- `/api/upload` → unzip → ClauseWizard parse → extract → Chapter 1
- Streaming SSE to browser
- Minimal embedded UI: upload zone + chapter display + live stream preview
- `chronicle_data/` file layout
- README, LICENSE, .gitignore
- Initial GitHub release: `v0.1.0`

### Phase 2 — Incremental Chapters
- Baseline storage and snapshot diff engine
- Delta event detection: wars, leaders, colonies, tech, diplomacy
- Rolling summary generation
- Chapter list sidebar
- Regenerate button
- `v0.2.0`

### Phase 3 — Polish
- Full delta coverage (federations, subjects, ascension perks, ethics shifts)
- Full dark-space UI with Cinzel/Lora typography
- Inline chapter title editing
- Export to `.md` download
- Settings modal (API key, word target)
- Basic test suite + CI
- `v0.3.0`

### Phase 4 — Community / Stretch
- Multi-campaign support
- Configurable narrative tone (chronicle, military log, personal journal, alien POV)
- Screenshot attachment per chapter
- Bulk import (drop N saves, generate N chapters in sequence)
- Ironman save support (if feasible)
- `v1.0.0`

---

## 16. Open Questions

1. **ClauseWizard robustness on current patch.** The library predates several major Stellaris updates. Need to test against a current save before building on it. If it fails, a hand-rolled Clausewitz parser is feasible in ~200 lines of Python and could live in `chronicle.py`.

2. **Minimum viable snapshot payload.** Need real saves at various game ages to calibrate how little data Claude needs for a quality chapter. Publish findings in `docs/save-format.md` so contributors can improve extraction.

3. **Tone derivation from ethics.** Should narrative voice be auto-derived from ethics/civics (Authoritarian → imperious, Pacifist → measured, Gestalt → collective/hive)? Or a manual setting? Auto-derivation via prompt feels more magical but needs testing.

4. **Concluded war records.** Need to confirm whether Stellaris exposes concluded war outcomes in a queryable block in the gamestate, or if we can only detect ended wars by absence from the active war list.

5. **Test fixture size.** A real early-game `.sav` is probably 1–5MB compressed. That's acceptable to commit to git, but worth verifying before publishing.

---

## 17. Getting Started (for contributors)

```bash
git clone https://github.com/[username]/chronicle
cd chronicle

# Run the app
python chronicle.py

# Run tests
pip install pytest
python -m pytest tests/ -v
```

Set your API key as an environment variable to skip the in-browser prompt:

```bash
ANTHROPIC_API_KEY=sk-ant-... python chronicle.py
```

---

*Document prepared April 2026. v0.4 — updated for open source GitHub distribution.*  
*Next step: Phase 1 build — bootstrap + parser + Chapter 1 generation + initial repo setup.*
