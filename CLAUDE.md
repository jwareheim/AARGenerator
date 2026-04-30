# Chronicle — CLAUDE.md

## Project Overview

Chronicle is a single-file Python app that turns Stellaris save files into AI-generated narrative AAR (After Action Report) chapters. Players drop `.sav` files incrementally; the tool diffs each save against the previous baseline, builds a prompt, and streams a prose chapter via the Anthropic API.

**Design document:** `docs/design.md` — read it before working on anything non-trivial.

---

## Critical Constraints

- **Single file.** The entire application is `chronicle.py`. Do not split it into modules. Everything — server, parser, diff engine, prompt builder, API client, and embedded UI — lives in that one file.
- **Two pip deps only.** `anthropic` and `clausewizard`. Everything else must be stdlib. Do not add new pip dependencies without explicit discussion.
- **No build step.** The embedded HTML/JS/CSS is a Python triple-quoted string. No bundler, no npm, no transpiler.
- **Python 3.8+ compatible.** No walrus operators, no match statements, no 3.10+ features.
- **`chronicle_data/` is gitignored.** Never commit user data, API keys, or save files.

---

## File Layout

```
chronicle.py                  ← the application (single file)
docs/
  design.md                   ← full design spec — read this
  save-format.md              ← Clausewitz format notes
  screenshots/                ← UI screenshots for README
tests/
  fixtures/sample.sav         ← anonymized test save
  test_parser.py
  test_diff.py
  test_prompt.py
.github/workflows/ci.yml      ← runs pytest on push/PR
README.md
CONTRIBUTING.md
LICENSE
CHANGELOG.md
.gitignore
```

---

## chronicle.py Section Map

The file is divided into 11 numbered sections — always maintain this order and labeling:

| # | Section | Key symbols |
|---|---------|-------------|
| 1 | DEPENDENCY BOOTSTRAP | `check_and_install_deps()` |
| 2 | IMPORTS | stdlib + pip imports |
| 3 | CONFIGURATION & CONSTANTS | `PORT`, `DATA_DIR`, `__version__`, `SYSTEM_PROMPT` |
| 4 | STORAGE LAYER | `load_meta/save_meta`, `load_baseline/save_baseline`, `load_chapter/save_chapter`, `list_chapters` |
| 5 | SAVE PARSER | `parse_save(file_bytes)`, `extract_relevant_data(raw, meta)` |
| 6 | DIFF ENGINE | `diff_snapshots(baseline, current)` |
| 7 | PROMPT BUILDER | `build_origin_prompt`, `build_chapter_prompt`, `build_summary_update_prompt` |
| 8 | CLAUDE API | `generate_chapter(prompt)`, `update_summary(prose, summary)` |
| 9 | HTTP REQUEST HANDLER | `class ChronicleHandler(BaseHTTPRequestHandler)` |
| 10 | EMBEDDED UI | `HTML_PAGE = """..."""` |
| 11 | ENTRYPOINT | `main()` |

When adding code, put it in the correct section. When reading code, use the section number to orient.

---

## API Routes

| Method | Path | Handler method | Purpose |
|--------|------|---------------|---------|
| GET | `/` | `do_GET` | Serve embedded HTML |
| GET | `/api/chapters` | `handle_list_chapters` | List all chapters |
| GET | `/api/chapters/<n>` | `handle_get_chapter` | Get single chapter |
| POST | `/api/upload` | `handle_upload` | Parse save → stream chapter |
| POST | `/api/chapters/<n>/title` | `handle_update_title` | Edit chapter title |
| POST | `/api/chapters/<n>/regenerate` | `handle_regenerate` | Re-generate chapter |
| GET | `/api/export` | `handle_export` | Download full AAR as .md |
| POST | `/api/config` | `handle_config` | Save API key / settings |
| DELETE | `/api/reset` | `handle_reset` | Wipe chronicle_data/ |

---

## Data Files (chronicle_data/)

| File | Contents |
|------|----------|
| `config.json` | `api_key`, `model`, `chapter_word_target` |
| `meta.json` | Empire name, species, start date, chapter count, timestamps |
| `baseline.json` | Extracted snapshot from the most recent save |
| `summary.json` | Rolling narrative summary (≤250 words), `chapters_covered` |
| `chapters/chapter-NNN.json` | `id`, `title`, `date_from`, `date_to`, `prose`, `word_count`, `delta_events`, `generated_at` |

Chapter files are zero-padded three digits (`chapter-001`, not `chapter-1`).

---

## Key Behaviors

**Dependency bootstrap** — `check_and_install_deps()` runs before any pip imports. It pip-installs `anthropic` and `clausewizard` silently if missing.

**API key priority** — `ANTHROPIC_API_KEY` env var beats `config.json`. If neither exists, the browser shows a setup screen before the main UI.

**Save parsing** — `.sav` is a ZIP; extract `meta` + `gamestate` text files. Parse both with `ClauseWizard.cwparse` → `ClauseWizard.cwformat` → `json.loads`. Then `extract_relevant_data()` prunes to ~50KB.

**Streaming** — `/api/upload` responds with `Content-Type: text/event-stream`. Each chunk is `data: {"chunk": "..."}\n\n`. On completion: `data: {"done": true}\n\n`.

**Delta sorting** — wars → leader deaths → territorial changes → tech/perks.

**Rolling summary** — after each chapter, a second non-streamed API call compresses history to ≤250 words.

---

## Model

Use `claude-sonnet-4-6` (defined as `DEFAULT_MODEL` constant). The model name must appear only in `config.json` defaults and the constant — never hardcoded in the API call itself (read from config).

---

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

- Tests must not call the real Anthropic API — mock `anthropic.Anthropic`.
- `tests/fixtures/sample.sav` is a real (anonymized) early-game save used for parser tests.
- CI runs on every push and PR via `.github/workflows/ci.yml`.

---

## Error Handling Philosophy

Return structured HTTP errors with clear user-facing messages. The UI displays these directly. Never crash the server on a bad upload — catch, log to stderr, and send the appropriate status code.

Key status codes:
- `400` — not a `.sav` file
- `401` — missing API key
- `409` — empire mismatch or save older than baseline
- `422` — ironman save
- `500` — parse failure or disk write failure
- `502` — Anthropic API error

---

## Roadmap Phase Summary

| Phase | Status | Focus |
|-------|--------|-------|
| 1 | In progress | Bootstrap + parser + Chapter 1 + minimal UI |
| 2 | Planned | Diff engine + incremental chapters + sidebar |
| 3 | Planned | Full UI polish + export + settings + tests |
| 4 | Stretch | Multi-campaign, tone config, ironman |

Current target: **Phase 1 → v0.1.0**.

---

## Architectural Decision Records

Reference these ADRs when working on related functionality to understand prior decisions and constraints.

### Save Parser

| ADR | Summary | Key Files |
|-----|---------|-----------|
| [initial-script-parser-fixes](docs/decisions/initial-script-parser-fixes.md) | ClauseWizard API usage, 4.x gamestate fallback, Python 3.8 f-string fix | `chronicle.py` §5 |

---

## Style Notes

- No comments unless the *why* is non-obvious.
- No docstrings (the function names and section headers are sufficient).
- `snake_case` throughout — no camelCase in Python.
- The embedded HTML/JS may use camelCase for JS variables — that's fine.
- Keep the embedded HTML/JS readable; it's part of the codebase, not a minified artifact.
