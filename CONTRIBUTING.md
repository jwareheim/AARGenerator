# Contributing to Chronicle

Thanks for your interest in contributing!

## Project Philosophy

- **Single file.** `chronicle.py` is the entire application. Do not split it into modules.
- **Two pip dependencies.** `anthropic` and `clausewizard` only. Everything else is stdlib.
- **No build step.** The HTML/JS/CSS is embedded as a Python string. No bundler, no npm.

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

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests must not call the real Anthropic API — mock `anthropic.Anthropic` in any test that exercises generation.

## Submitting a PR

1. Fork the repo
2. Create a branch from `main`
3. Make your change
4. Run `python -m pytest tests/ -v`
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
