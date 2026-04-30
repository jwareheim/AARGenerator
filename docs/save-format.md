# Stellaris Save Format Notes

## File Structure

A `.sav` file is a ZIP archive containing two plain-text entries:

- `meta` — lightweight header: empire name, player ID, game date, ironman flag, patch version
- `gamestate` — the full game state in Clausewitz script format (can exceed 200MB late game)

## Clausewitz Script Format

Clausewitz is Paradox's proprietary key-value format. Example:

```
date="2287.06.15"
player="PLAYER"
country={
    0={
        name="Keth Dominion"
        capital=4
    }
}
```

Chronicle parses this with `ClauseWizard.cwparse()` → `ClauseWizard.cwformat()` → `json.loads()`.

## Key Paths in gamestate (to be documented)

These paths need to be verified against a real save file. The `extract_relevant_data()` function in `chronicle.py` (Section 5) reads from these locations.

| Field | Path in gamestate dict | Notes |
|-------|----------------------|-------|
| Date | `date` | Format: `"YYYY.MM.DD"` |
| Player empire ID | `player` | Used to find the player's country block |
| Empire name | `country[player_id].name` | |
| Species traits | TBD | |
| Ethics | TBD | |
| Civics | TBD | |
| Planets | TBD | |
| Wars | TBD | |
| Leaders | TBD | |
| Technologies | TBD | |

## Test Fixture

`tests/fixtures/sample.sav` is an anonymized early-game save (circa 2220–2230 in-game) used for parser unit tests. It was produced by:

1. Starting a new standard game
2. Saving shortly after first contact
3. Stripping personal identifiers (steam ID, etc.) — TBD

Target size: under 2MB compressed.

## Known Issues

- ClauseWizard's handling of very large files (>100MB) has not been stress-tested
- Some modded saves use non-standard keys that ClauseWizard may not parse correctly
- Ironman saves use a different encoding — not yet supported
- Patch compatibility: Chronicle was last tested against Stellaris 3.x saves; newer patches may introduce new field layouts
