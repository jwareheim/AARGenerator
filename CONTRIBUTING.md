# Contributing to Chronicle

Thanks for your interest in contributing!

## Project Philosophy

- **Single file.** `chronicle.py` is the entire application. Do not split it into modules.
- **One pip dependency.** `anthropic` only. Everything else is stdlib.
- **No build step.** The HTML/JS/CSS is embedded as a Python string. No bundler, no npm.
- **Parser binary.** Save parsing is handled by `stellaris-parser`, a compiled Rust binary. Python contributors do not need to build it themselves — it auto-downloads on first run.

## How chronicle.py is organized

The file has 11 numbered sections — always maintain their order:

1. Dependency Bootstrap
2. Imports
3. Configuration & Constants
4. Storage Layer
5. Save Parser
6. Diff Engine
7. Prompt Builder
8. Claude API
9. HTTP Request Handler
10. Embedded UI
11. Entrypoint

See `docs/design.md` for the full design specification.

## Running the app

```bash
python chronicle.py
```

Set your API key as an env var to skip the browser prompt:

```bash
ANTHROPIC_API_KEY=sk-ant-... python chronicle.py
```

On first run, `chronicle.py` auto-downloads the correct `stellaris-parser` binary for your platform from GitHub Releases and places it at `bin/stellaris-parser[.exe]`.

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

The Python tests call the real `stellaris-parser` binary at `bin/stellaris-parser[.exe]`. If the binary is absent, the parser tests will fail — either run the app once to auto-download, or follow the Rust contributor steps below to build it yourself.

Tests must not call the real Anthropic API — mock `anthropic.Anthropic` in any test that exercises generation.

## Rust contributor workflow

Use this if you are modifying `stellaris-parser/` (the Rust parsing binary).

**Prerequisites:** Rust stable toolchain — install from [rustup.rs](https://rustup.rs/).

```bash
# Build and run tests (integration tests require the fixture at tests/fixtures/sample.sav)
cd stellaris-parser
cargo test

# Build the release binary and copy it into place for chronicle.py
cargo build --release
mkdir -p ../bin
cp target/release/stellaris-parser[.exe] ../bin/

# Run all tests (Rust + Python)
cd ..
python -m pytest tests/ -v
```

When the parser output schema changes, update `src/schema.rs` and `chronicle.py §5 extract_relevant_data()` together, then update the fixture assertions in `tests/test_parser.py` and `stellaris-parser/tests/integration_test.rs`.

## Python-only contributor workflow

Use this if you are only modifying `chronicle.py` (no Rust changes).

```bash
# First run auto-downloads the binary; subsequent runs skip the download
python chronicle.py
```

After the binary is in `bin/`, the full test suite runs without Rust:

```bash
pip install pytest
python -m pytest tests/ -v
```

## Submitting a PR

1. Fork the repo
2. Create a branch from `main`
3. Make your change
4. Run `python -m pytest tests/ -v` (and `cargo test` if you changed the parser)
5. Open a PR against `main`

## Issue labels

| Label | Use |
|---|---|
| `bug` | Something broken |
| `enhancement` | New feature request |
| `parser` | Clausewitz parsing issues |
| `mod-compat` | Problems with modded saves |
| `good first issue` | Small, well-scoped, beginner-friendly |
| `help wanted` | Good for community contribution |
