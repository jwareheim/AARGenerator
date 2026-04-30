# Initial Script Setup and Save Parser Fixes

## Status

Accepted

## Context

### Problem Statement

During initial development of `chronicle.py` on the `feature/InitialScript` branch, three bugs were discovered when running the application and uploading a real Stellaris 4.3 save file.

### Technical Constraints

- Python 3.8+ compatibility required — several f-string behaviours differ between 3.8–3.11 and 3.12+
- ClauseWizard 1.0.4 is the chosen Clausewitz-format parser; its API is not well-documented
- Stellaris 4.x introduced new save-file blocks (e.g. `astral_rifts`) that older parser versions do not handle

## Decision

### Approach Selected: Fix-Forward on Three Discrete Issues

Three bugs were identified and fixed in place rather than deferred.

---

#### Fix 1 — Python 3.8 f-string backslash restriction (`chronicle.py:594`)

**Problem:** Backslash escapes (e.g. `\"`) are not allowed inside f-string `{}` expressions prior to Python 3.12. The expression `f'Chapter {stub[\"id\"]}'` nested inside an outer f-string raised a `SyntaxError`.

**Decision:** Pre-compute the default value into a plain variable before the f-string.

```python
# before
lines.append(f"\n## {ch.get('title', f'Chapter {stub[\"id\"]}')}")

# after
default_title = f"Chapter {stub['id']}"
lines.append(f"\n## {ch.get('title', default_title)}")
```

---

#### Fix 2 — ClauseWizard `cwformat` return type mismatch

**Problem:** `chronicle.py` called `json.loads(ClauseWizard.cwformat(...))`, assuming `cwformat` returns a JSON string. Inspecting the library source revealed `cwformat` (`format_full`) returns a `defaultdict` directly. Passing it to `json.loads` raised `TypeError: the JSON object must be str, bytes or bytearray, not defaultdict`.

**Decision:** Remove the `json.loads()` wrapper and use the `defaultdict` directly. It supports `.get()` and iteration identically to a regular dict.

```python
# before
meta = json.loads(ClauseWizard.cwformat(meta_tokens))
raw  = json.loads(ClauseWizard.cwformat(gamestate_tokens))

# after
meta = ClauseWizard.cwformat(meta_tokens)
raw  = ClauseWizard.cwformat(gamestate_tokens)
```

---

#### Fix 3 — Graceful fallback for unparseable Stellaris 4.x gamestate blocks

**Problem:** ClauseWizard 1.0.4 uses pyparsing with `parseAll=True`. In Stellaris 4.3 saves the `astral_rifts` block (introduced with the Astral Planes DLC) contains syntax the grammar does not handle. This caused a `ParseException` at ~line 940,000 of the gamestate file, surfacing to the user as "Couldn't parse this save — is it from a heavily modded game?"

**Decision:** Wrap the gamestate parse in a try/except. On failure, log a warning to stderr and fall back to `raw = {}`. `extract_relevant_data` is currently a stub returning default values regardless, so no functional data is lost. The meta file (date, version) still parses successfully.

```python
try:
    gamestate_tokens = ClauseWizard.cwparse(gamestate_text)
    raw = ClauseWizard.cwformat(gamestate_tokens)
except Exception as exc:
    print(f"[chronicle] Gamestate parse partial failure: {exc}", file=sys.stderr)
    raw = {}
```

This fallback should be revisited when `extract_relevant_data` is fully implemented (Phase 1 completion). At that point, options include pre-stripping unknown top-level blocks via regex or switching to a more actively maintained Clausewitz parser.

### Alternatives Considered

#### Alternative — Switch to a different Clausewitz parser immediately

There are other community parsers (e.g. hand-rolled regex extractors). Rejected at this stage because ClauseWizard handles the majority of the format correctly, `extract_relevant_data` is a stub anyway, and a parser migration is a larger scope than fixing the immediate startup blocker.

## Consequences

### Positive

- Application starts and accepts 4.x save uploads without crashing
- Python 3.8 compatibility is maintained across all target platforms
- ClauseWizard API is now used correctly; future callers of `cwformat` output will work as expected

### Negative

- When the gamestate parse falls back to `raw = {}`, any data that would have been extracted from gamestate is silently absent (mitigated by the stderr warning and the fact that extraction is stubbed)
- The root cause of Fix 3 (ClauseWizard grammar incompatibility with 4.x blocks) remains unresolved until `extract_relevant_data` is implemented

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Future Stellaris patches introduce more unparseable blocks, silently degrading extraction quality | Stderr warning makes failures visible; revisit when implementing `extract_relevant_data` |
| ClauseWizard is unmaintained (last release 1.0.4) and falls further behind the save format | Evaluate alternative parsers before Phase 2 diff engine work begins |

## References

- **Branch**: `feature/InitialScript`
- **Key file**: `chronicle.py` — sections [5] Save Parser
- **Related docs**: `docs/save-format.md`
