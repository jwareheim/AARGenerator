# Stellaris Parser — Compatibility

Tested patches and known field-format variations across Stellaris versions.

## Tested versions

| Stellaris patch | Parser version | Status | Notes |
|-----------------|----------------|--------|-------|
| Cetus v4.3.2 | 0.1.1 | ✅ Confirmed | Fixture in `tests/fixtures/sample.sav` |
| Cetus v4.3.5 | 0.1.1 | ✅ Confirmed | Phase 0 exploration save |

## Known format limitations (Cetus 4.x)

These fields return `null` or empty arrays because Stellaris 4.x stores them as Clausewitz localisation sub-objects instead of plain strings. Resolving them would require a localisation file lookup that is out of scope for this binary.

| Field | Symptom | Root cause |
|-------|---------|------------|
| `empire.name` | `null` | Country name is a localisation key dict, not a scalar |
| `empire.adjective` | `null` | Same as above |
| `empire.home_planet` | `null` | Planet name is a localisation dict |
| `empire.home_system` | `null` | Galactic object name may also be a dict in 4.x |
| `empire.species_name` | `null` | Species name is a localisation key |
| `state.owned_planets` | `[]` | Planet display names are localisation dicts |
| `state.total_pops` | `0` | 4.x stores pops as an array of IDs; `pop_count` field absent |
| `leaders[*].name` | `null` | Leader name is a localisation dict |
| `wars[*].name` | `null` | War name is a localisation dict |

`state.owned_planet_count` is populated correctly via the `planets.planet` block iteration.

## Reporting compatibility issues

Open an issue and include:
1. The patch version string from `meta` (e.g. `Cetus v4.3.5`)
2. The parser version (`stellaris-parser --version`)
3. A minimal anonymised snippet of the failing block (strip empire/planet names)
