# Chronicle — stellaris-parser Design Document

**Project:** Chronicle  
**Component:** stellaris-parser  
**Version:** 1.1  
**Status:** Pre-development  
**Language:** Rust  
**Repository:** github.com/[username]/chronicle (subdirectory `stellaris-parser/`)  

---

## 1. Overview

`stellaris-parser` is a purpose-built Rust binary that extracts structured data from Stellaris `.sav` files and outputs JSON to stdout. It is built on the `jomini` crate — a battle-tested, actively maintained Clausewitz format parser that underpins the EU4 save analyzer at Rakaly, the Paradox Game Converters, and other community tools.

The binary is called from Chronicle's Python layer via `subprocess`. It is compiled for Windows and Linux and either:

- **Auto-downloaded** on first `python chronicle.py` run — Chronicle's bootstrap fetches the correct platform binary from GitHub Releases and places it in `bin/`
- **Bundled** into the Chronicle executable via PyInstaller's `--add-binary` mechanism for the packaged distribution

**Design philosophy:** Do one thing well. `stellaris-parser` is not a general Stellaris data explorer — it extracts exactly the fields Chronicle needs for AAR generation, nothing more. This keeps the output schema tight, the binary small, and the maintenance burden low.

---

## 2. Why Rust + jomini

> **Inspiration:** The approach of using Rust + jomini as the parsing layer was inspired by [stellaris-companion](https://github.com/gitmaan/stellaris-companion/), a community Stellaris save tool that demonstrated this combination is viable and performant for 4.x saves.

**jomini** is the right foundation for several reasons:

- Actively maintained — last updated 2026, powers production tools with large userbases
- Parses at over 1 GB/s, making even the largest late-game saves a non-issue
- Handles the full Clausewitz format including edge cases that have tripped up other parsers
- Supports both plaintext and binary encoded saves
- Handles Windows-1252 encoding correctly (Stellaris uses this, not UTF-8)
- Has a built-in JSON output path via `reader.json()`
- Extensively fuzzed against malformed input — won't crash on corrupted saves

**Rust** is the right language because:

- Compiles to a small, self-contained native binary with no runtime dependency
- PyInstaller can bundle it as a data file alongside the Python code
- Cross-compilation for Windows from Linux is well-supported via `cross`
- The jomini crate is Rust-native — using it from Python directly would require FFI bindings; a subprocess binary is simpler and equally fast

---

## 3. Integration with Chronicle

### 3.1 How Python Calls the Parser

```python
import subprocess
import json
import sys
import stat
import urllib.request
from pathlib import Path

PARSER_VERSION = "1.0.0"
PARSER_BASE_URL = f"https://github.com/[username]/chronicle/releases/download/v{PARSER_VERSION}"

def get_parser_binary() -> Path:
    """Locate the parser binary — bundled path in PyInstaller, bin/ otherwise."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle — binary is in the extracted temp dir
        base = Path(sys._MEIPASS)
    else:
        # Running as plain script — binary is in bin/ next to chronicle.py
        base = Path(__file__).parent

    binary = 'stellaris-parser.exe' if sys.platform == 'win32' else 'stellaris-parser'
    return base / 'bin' / binary

def ensure_parser_binary():
    """
    Called during bootstrap. Downloads the parser binary from GitHub Releases
    if it isn't already present in bin/. No-op when running as a PyInstaller bundle
    (binary is always bundled) or when the binary already exists.
    """
    if getattr(sys, 'frozen', False):
        return  # bundled — nothing to download

    binary_path = get_parser_binary()
    if binary_path.exists():
        return  # already present

    binary_name = binary_path.name
    url = f"{PARSER_BASE_URL}/{binary_name}"

    print(f"Chronicle: downloading parser binary ({binary_name})...")
    try:
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, binary_path)
    except Exception as e:
        print(f"\nError: could not download parser binary from:\n  {url}\n")
        print("Options:")
        print("  1. Check your internet connection and try again")
        print("  2. Build from source: cd stellaris-parser && cargo build --release")
        print("     then copy the binary to bin/")
        print(f"  3. Download manually from: {PARSER_BASE_URL}")
        sys.exit(1)

    # Mark executable on Unix
    if sys.platform != 'win32':
        binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)

    print(f"  ✓ parser ready\n")

def parse_save(save_path: str) -> dict:
    parser = get_parser_binary()
    result = subprocess.run(
        [str(parser), 'extract', save_path],
        capture_output=True,
        timeout=120  # 2 minute ceiling for very large saves
    )
    if result.returncode != 0:
        error = result.stderr.decode('utf-8', errors='replace')
        raise RuntimeError(f"Parser failed: {error}")

    return json.loads(result.stdout.decode('utf-8'))
```

`ensure_parser_binary()` is called from the main bootstrap sequence alongside `check_and_install_deps()`, before the HTTP server starts.

### 3.2 PyInstaller Bundling

In `chronicle.spec`, the parser binary is included as a data file:

```python
binaries=[
    ('bin/stellaris-parser.exe', 'bin'),   # Windows
],
# or for Linux build:
binaries=[
    ('bin/stellaris-parser', 'bin'),
],
```

PyInstaller places these in `sys._MEIPASS` at runtime, which is where `get_parser_binary()` looks when frozen.

### 3.3 Dev Layout

```
chronicle/
├── bin/
│   ├── stellaris-parser          ← Linux binary (auto-downloaded or built locally, gitignored)
│   └── stellaris-parser.exe      ← Windows binary (auto-downloaded or built locally, gitignored)
├── stellaris-parser/             ← Rust source
│   ├── Cargo.toml
│   ├── Cargo.lock
│   └── src/
│       ├── main.rs
│       ├── extract.rs
│       ├── schema.rs
│       └── error.rs
└── ...
```

**On first `python chronicle.py`:** if `bin/stellaris-parser` is absent, `ensure_parser_binary()` downloads it from GitHub Releases automatically. No manual steps needed.

**For Rust contributors:** build locally with `cargo build --release` and copy the output to `bin/`. The local binary takes precedence since `ensure_parser_binary()` skips the download if the file already exists.

**Note:** a tagged GitHub Release containing the parser binary must exist before `python chronicle.py` can auto-download it. For development before the first release, Rust contributors build locally and Python-only contributors can request a pre-release binary from the maintainer.

---

## 4. CLI Interface

The binary exposes a simple CLI with one primary subcommand:

```
USAGE:
    stellaris-parser extract <save_path> [OPTIONS]

ARGS:
    <save_path>    Path to the .sav file

OPTIONS:
    --pretty       Pretty-print JSON output (for debugging)
    --validate     Parse and validate only, no output (exit 0 = success)
    --version      Print parser version and exit

EXIT CODES:
    0    Success
    1    File not found
    2    Not a valid .sav file (not a ZIP or missing gamestate)
    3    Parse error (malformed Clausewitz data)
    4    Extraction error (expected field missing — likely a version mismatch)
    5    Ironman save detected (binary format, not supported)
```

**stdout:** JSON on success, empty on error  
**stderr:** Human-readable error message on failure  

Example usage:

```bash
# Normal extraction
stellaris-parser extract my_campaign.sav

# Debug / pretty print
stellaris-parser extract my_campaign.sav --pretty

# Validate a save without extracting (useful for upload pre-check)
stellaris-parser extract my_campaign.sav --validate
```

---

## 5. Output Schema

The parser outputs a single JSON object. All fields are present on success; unknown or missing fields use `null` rather than omitting the key, so the Python side can always expect a consistent shape.

```json
{
  "parser_version": "1.0.0",
  "patch_version": "3.14.0",
  "ironman": false,

  "date": "2310.06.15",
  "player_country_id": "42",

  "empire": {
    "name": "Keth Dominion",
    "adjective": "Keth",
    "authority": "imperial",
    "ethics": ["authoritarian", "militarist"],
    "civics": ["distinguished_admiralty", "feudal_realm"],
    "origin": "origin_prosperous_unification",
    "home_planet": "Keth Prime",
    "home_system": "Keth",
    "species_name": "Keth",
    "species_plural": "Keth",
    "species_class": "humanoid",
    "species_traits": ["intelligent", "adaptive", "industrious"]
  },

  "state": {
    "owned_planets": ["Keth Prime", "Davar IV", "Tessara", "Kelat II"],
    "owned_planet_count": 4,
    "total_pops": 847,
    "fleet_power": 142800,
    "monthly_energy": 214.5,
    "monthly_minerals": 178.2,
    "monthly_alloys": 62.1,
    "traditions": ["tr_supremacy_adopt", "tr_supremacy_finish"],
    "ascension_perks": ["ap_voidborn", "ap_mind_over_matter"],
    "recent_technologies": [
      "tech_psionic_theory",
      "tech_zero_point_power",
      "tech_mega_engineering"
    ]
  },

  "ruler": {
    "id": "1042",
    "name": "Empress Solan III",
    "gender": "female",
    "age": 52,
    "traits": ["charismatic", "expansionist"],
    "class": "ruler"
  },

  "leaders": [
    {
      "id": "1043",
      "name": "Admiral Varak",
      "class": "admiral",
      "age": 67,
      "traits": ["aggressive", "fleet_logistician"],
      "level": 4
    }
  ],

  "wars": [
    {
      "id": "war_001",
      "name": "The Davar War",
      "attacker": "Keth Dominion",
      "defender": "Zroni Remnants",
      "war_goal": "wg_conquest",
      "start_date": "2287.03.12",
      "our_warscore": 78.4,
      "active": true
    }
  ],

  "concluded_wars": [
    {
      "id": "war_000",
      "name": "The Border Skirmish",
      "attacker": "Keth Dominion",
      "defender": "Chirex Compact",
      "war_goal": "wg_humiliation",
      "start_date": "2241.07.01",
      "end_date": "2244.02.15",
      "outcome": "attacker_victory",
      "active": false
    }
  ],

  "diplomacy": {
    "federation": {
      "name": "Galactic Accord",
      "our_role": "member",
      "members": ["Keth Dominion", "Tessari Union", "Velhari Hegemony"]
    },
    "subjects": [
      { "name": "Chirex Compact", "type": "vassal" }
    ],
    "rivals": ["Zroni Remnants"],
    "allies": ["Tessari Union"]
  }
}
```

### 5.1 Field Notes

**`patch_version`** — extracted from the `meta` file. Chronicle logs a warning in the UI if this is newer than the parser's last tested version.

**`ironman`** — if `true`, the binary exits with code 5 and no JSON is produced. Chronicle surfaces a clear error to the user.

**`fleet_power`** — raw integer from the save. Chronicle's prompt builder translates this to a narrative scale (e.g. < 10k = "fledgling fleets", 10k–100k = "respectable military", > 500k = "dominant war machine").

**`recent_technologies`** — the last 10 technologies researched by the player empire, in research order. Extracted from the technology list by comparing research dates.

**`concluded_wars`** — wars where `end_date` is present in the save's war history block. This is how Chronicle detects wars that ended between save uploads even if they're no longer in the active war list.

**`species_traits`, `ethics`, `civics`** — returned as internal ID strings (e.g. `"distinguished_admiralty"`). Chronicle's prompt builder has a display name lookup table for the most common values, with a fallback that humanizes the ID string (`"distinguished_admiralty"` → `"Distinguished Admiralty"`).

---

## 6. Rust Implementation

### 6.1 Cargo.toml

```toml
[package]
name = "stellaris-parser"
version = "1.0.0"
edition = "2021"
description = "Stellaris save file extractor for Chronicle"
license = "MIT"

[[bin]]
name = "stellaris-parser"
path = "src/main.rs"

[dependencies]
jomini = { version = "0.23", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
zip = { version = "0.6", default-features = false, features = ["deflate"] }
clap = { version = "4", features = ["derive"] }
thiserror = "1"

[profile.release]
opt-level = 3
lto = true          # Link-time optimization — smaller, faster binary
codegen-units = 1   # Better optimization at cost of compile time
strip = true        # Strip debug symbols from release binary
```

### 6.2 Module Structure

**`src/main.rs`** — CLI entry point using `clap`. Parses args, calls `extract::run()`, handles exit codes.

**`src/extract.rs`** — core logic:
  - Unzip the `.sav` file using the `zip` crate
  - Detect ironman (binary format header check)
  - Parse `meta` with jomini → extract patch version, date, player ID
  - Parse `gamestate` with jomini → navigate to relevant top-level keys
  - Call field extractors from `schema.rs`
  - Serialize result to JSON via `serde_json`

**`src/schema.rs`** — Rust structs representing the output schema, derived with `serde::Serialize`. Also contains the extraction functions that pull each field from the jomini parse tree.

**`src/error.rs`** — custom error type using `thiserror`, mapping to exit codes.

### 6.3 Parsing Strategy

jomini's key insight for performance is that it builds a "tape" — an index into the raw bytes — rather than materializing the full document into a tree. This means we can navigate directly to the keys we need without allocating memory for the rest.

```rust
use jomini::TextTape;

pub fn extract_gamestate(data: &[u8]) -> Result<GameState, ParserError> {
    let tape = TextTape::from_slice(data)?;
    let reader = tape.windows1252_reader();

    let mut empire = None;
    let mut state = None;
    let mut leaders = Vec::new();
    let mut wars = Vec::new();

    // Walk only top-level keys we care about
    for (key, _op, value) in reader.fields() {
        match key.read_str().as_ref() {
            "country" => empire = Some(extract_player_empire(&value)?),
            "war"     => wars.push(extract_war(&value)?),
            "leaders" => leaders = extract_leaders(&value)?,
            "planets" => state = Some(extract_state(&value)?),
            _         => {} // skip everything else — no allocation, no cost
        }
    }

    Ok(GameState { empire, state, leaders, wars })
}
```

The `_` arm is the key performance win — the vast majority of gamestate keys (pop data, tile data, species modifiers, etc.) are skipped entirely with no allocation.

### 6.4 Windows-1252 Encoding

Stellaris saves use Windows-1252 encoding, not UTF-8. jomini handles this correctly via `tape.windows1252_reader()`. All extracted strings are converted to UTF-8 for the JSON output. Characters that can't be converted cleanly are replaced with the Unicode replacement character rather than causing a parse failure.

### 6.5 Ironman Detection

Ironman saves use a binary format rather than plaintext Clausewitz. Detection:

```rust
fn is_ironman(gamestate_bytes: &[u8]) -> bool {
    // Binary saves start with a specific magic byte sequence
    // Plaintext saves start with printable ASCII
    gamestate_bytes.get(0).map(|b| *b < 0x20 && *b != b'\n' && *b != b'\r').unwrap_or(false)
}
```

If ironman is detected, exit with code 5 before attempting parse.

---

## 7. Error Handling

All errors produce a JSON-free stderr message and a non-zero exit code. Chronicle's Python layer checks the exit code and maps it to a user-facing message:

| Exit Code | Rust error variant | Python → UI message |
|---|---|---|
| 0 | — | Success |
| 1 | `FileNotFound` | "Save file not found." |
| 2 | `NotASave` | "This doesn't look like a Stellaris save file." |
| 3 | `ParseError` | "Couldn't parse this save — it may be from a heavily modded game." |
| 4 | `ExtractionError` | "Save parsed but expected data was missing — parser may need updating for this patch." |
| 5 | `IronmanSave` | "Ironman saves aren't supported yet." |

stderr format:

```
ERROR [code=3]: Failed to parse gamestate: unexpected token at offset 48291
```

This gives enough detail for a bug report without exposing raw Rust panics to the user.

---

## 8. Build & Distribution

### 8.1 Building Locally

```bash
cd stellaris-parser

# Debug build (fast compile, slow runtime — for development)
cargo build

# Release build (slow compile, fast runtime — for distribution)
cargo build --release

# Output
# Linux:   target/release/stellaris-parser
# Windows: target/release/stellaris-parser.exe

# Copy to Chronicle's bin/ directory
cp target/release/stellaris-parser ../bin/
```

### 8.2 Cross-Compilation

Building the Windows binary from Linux (or vice versa) uses `cross`, a Docker-based Rust cross-compilation tool:

```bash
# Install cross
cargo install cross

# Build Windows binary from Linux
cross build --release --target x86_64-pc-windows-gnu

# Output: target/x86_64-pc-windows-gnu/release/stellaris-parser.exe
```

### 8.3 GitHub Actions Integration

The parser is built as part of the existing Chronicle release workflow. The parser build runs first, producing binaries that are then bundled into the PyInstaller executables:

```yaml
jobs:
  build-parser:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            output: stellaris-parser
          - os: windows-latest
            target: x86_64-pc-windows-msvc
            output: stellaris-parser.exe

    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Build parser
        working-directory: stellaris-parser
        run: cargo build --release --target ${{ matrix.target }}

      - name: Stage binary
        shell: bash
        run: |
          mkdir -p bin
          cp stellaris-parser/target/${{ matrix.target }}/release/${{ matrix.output }} bin/

      - name: Upload parser binary
        uses: actions/upload-artifact@v4
        with:
          name: parser-${{ matrix.os }}
          path: bin/${{ matrix.output }}

  build-chronicle:
    needs: build-parser   # Parser must be built first
    # ... existing PyInstaller build steps ...
    # Downloads parser artifact into bin/ before running pyinstaller
```

### 8.4 Binary Versioning

The parser binary version is embedded at compile time and printed via `--version`:

```
stellaris-parser 1.0.0
```

Chronicle logs this version at startup and includes it in bug reports. When a Stellaris patch breaks parsing, the parser version makes it easy to correlate user reports.

---

## 9. Versioning & Patch Compatibility

The Clausewitz format is not formally specified and Paradox changes it between patches. The parser must be resilient:

- Unknown top-level keys are silently skipped (already the default behavior)
- Missing expected fields produce `null` in the output rather than a parse failure
- The `patch_version` field from `meta` is always included in output so Chronicle can warn the user if their save is newer than the last tested patch
- Exit code 4 (`ExtractionError`) is reserved for cases where a structurally required field (e.g. the player country block) is completely absent — indicating a format change significant enough that the parser needs updating

A `COMPATIBILITY.md` file in the `stellaris-parser/` directory tracks which Stellaris patches have been tested:

```markdown
## Tested Patches

| Stellaris Version | Parser Version | Status |
|---|---|---|
| 3.14.x | 1.0.0 | ✅ Confirmed working |
| 4.0.x  | 1.0.0 | ⚠️ Untested — please report |
```

Community bug reports against specific patches are the primary signal for when an update is needed.

---

## 10. Testing

### 10.1 Unit Tests (Rust)

```
stellaris-parser/
└── tests/
    ├── fixtures/
    │   ├── early_game.sav     ← anonymized real save, year ~2230
    │   ├── mid_game.sav       ← anonymized real save, year ~2300
    │   └── ironman.sav        ← ironman save (binary) for rejection test
    └── integration_test.rs    ← parse fixtures, assert output shape
```

Tests verify:
- Output JSON matches expected schema shape
- All required fields are present and correctly typed
- Ironman saves exit with code 5
- Corrupted/truncated saves exit with code 2 or 3, not a panic

### 10.2 Chronicle Integration Tests (Python)

```python
# tests/test_parser.py
def test_parse_early_game_save():
    result = parse_save('tests/fixtures/early_game.sav')
    assert result['empire']['name'] is not None
    assert result['date'].startswith('22')
    assert isinstance(result['state']['owned_planet_count'], int)

def test_ironman_save_raises():
    with pytest.raises(RuntimeError, match="Ironman"):
        parse_save('tests/fixtures/ironman.sav')
```

### 10.3 CI

Parser tests run in the existing `ci.yml` workflow on every PR:

```yaml
- name: Run Rust tests
  working-directory: stellaris-parser
  run: cargo test

- name: Run Python integration tests
  run: python -m pytest tests/test_parser.py -v
  # Requires parser binary to be pre-built and in bin/
```

---

## 11. Repository Changes

### 11.1 New Files

```
chronicle/
├── stellaris-parser/           ← NEW: Rust crate
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── COMPATIBILITY.md
│   └── src/
│       ├── main.rs
│       ├── extract.rs
│       ├── schema.rs
│       └── error.rs
├── bin/                        ← NEW: pre-built binaries (gitignored)
│   ├── stellaris-parser
│   └── stellaris-parser.exe
├── tests/
│   └── fixtures/
│       ├── early_game.sav      ← NEW: test fixture
│       └── ironman.sav         ← NEW: test fixture
└── .github/workflows/
    └── release.yml             ← UPDATED: parser build added
```

### 11.2 `.gitignore` additions

```gitignore
# Pre-built parser binaries — downloaded by CI, not committed
bin/stellaris-parser
bin/stellaris-parser.exe

# Rust build artifacts
stellaris-parser/target/
```

### 11.3 `chronicle.py` changes

- Remove `clausewizard` import and all ClauseWizard usage
- Remove `clausewizard` from `REQUIRED` in `check_and_install_deps()` — it's no longer a pip dependency
- Add `ensure_parser_binary()` to the bootstrap sequence (called after `check_and_install_deps()`)
- Add `get_parser_binary()` and `parse_save()` functions as described in Section 3.1
- Add `PARSER_VERSION` constant — must be kept in sync with the Rust crate version in `Cargo.toml`
- Update bootstrap output so the full startup sequence reads:

```
Chronicle: installing missing dependencies...
  ✓ anthropic installed
Chronicle: downloading parser binary (stellaris-parser)...
  ✓ parser ready

Starting Chronicle on http://localhost:8765
```

### 11.4 `requirements.txt` changes

```
anthropic>=0.25.0
# clausewizard removed — replaced by stellaris-parser Rust binary
```

---

## 12. Open Questions

1. **`concluded_wars` block location in gamestate.** Need to verify exactly where past war records live in a current Stellaris save — whether they persist in a `war_history` or similar block, or are only inferrable by absence from the active war list. This affects whether we can detect wars that started and ended between uploads.

2. **Leader death records.** Similarly, do deceased leaders remain in the gamestate with a death date, or are they simply absent? Affects how richly we can describe leader deaths in chapter narratives.

3. **Duplicate keys.** The Clausewitz format allows duplicate keys (e.g. multiple `planet = { ... }` entries). jomini handles these correctly via its `duplicated` attribute, but our extraction logic needs to handle them as lists not single values. Need to verify the exact structure of `war`, `leader`, and `planet` blocks in a real save.

4. ~~**Dev setup for contributors without Rust.**~~ **Resolved** — `ensure_parser_binary()` in the bootstrap auto-downloads the correct platform binary from GitHub Releases on first `python chronicle.py` run. Python-only contributors need no Rust toolchain. Documented in CONTRIBUTING.md: Rust contributors build locally and copy to `bin/`; Python contributors let the bootstrap handle it.

5. **Parser binary size.** With `lto = true` and `strip = true`, the release binary should be small (likely 2–5MB). Worth confirming after first build.

---

## 13. Getting Started

### Python-Only Contributors (no Rust required)

```bash
# Clone and run — binary is auto-downloaded on first launch
git clone https://github.com/[username]/chronicle
cd chronicle
pip install anthropic
python chronicle.py
# → downloads stellaris-parser binary automatically
# → opens http://localhost:8765
```

If the auto-download fails (no internet, pre-release), ask the maintainer for a pre-built binary and place it in `bin/`.

### Parser / Rust Contributors

```bash
# Prerequisites: Rust stable toolchain — https://rustup.rs

cd stellaris-parser

# Build and test
cargo build
cargo test

# Run against a real save
cargo run -- extract /path/to/my/save.sav --pretty

# Release build — copy to bin/ so chronicle.py picks it up
cargo build --release
cp target/release/stellaris-parser ../bin/        # Linux
cp target/release/stellaris-parser.exe ../bin/    # Windows
```

For cross-compilation (Windows binary from Linux):

```bash
cargo install cross
cross build --release --target x86_64-pc-windows-gnu
cp target/x86_64-pc-windows-gnu/release/stellaris-parser.exe ../bin/
```

---

*Document prepared April 2026. v1.1 — added auto-download bootstrap for `python chronicle.py` workflow.*  
*Next step: scaffold the Rust crate, implement meta extraction, test against a real save.*
