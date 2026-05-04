# Stellaris Save Format Notes

**Last verified against:** Cetus v4.3.5  
**Sample save:** `thebloodcrusade2_-2068187095/2205.07.01.sav` (early game, ~5 years in)

---

## File Structure

A `.sav` file is a ZIP archive containing two plain-text entries:

- `meta` — lightweight header, always parseable by ClauseWizard
- `gamestate` — full game state in Clausewitz script format (can exceed 200MB late game)

---

## meta file

Parsed successfully by ClauseWizard in all tested versions.

| Field | Path | Example | Notes |
|-------|------|---------|-------|
| Patch version | `meta["version"]` | `"Cetus v4.3.5"` | |
| In-game date | `meta["date"]` | `"2205.07.01"` | |
| Save name | `meta["name"]` | `"The Blood Crusade 2"` | User-visible save name, not empire name |
| Player portrait | `meta["player_portrait"]` | `"inf9"` | Use to identify player's country ID in gamestate |
| Ironman flag | `meta["ironman"]` | `True` / absent | Absent means not ironman. In 4.x, ironman saves use the same plaintext format as normal saves — the flag indicates achievement eligibility only, not binary encoding. Ironman saves are parseable. |
| Fleet count | `meta["meta_fleets"]` | `10` | Quick summary only |
| Planet count | `meta["meta_planets"]` | `1` | Quick summary only |

---

## gamestate file

### ClauseWizard compatibility (4.3.5)

ClauseWizard 1.0.4 **cannot parse the full gamestate** in Stellaris 4.x. It hits unrecognised syntax and raises `ParseException` before reaching the `country` block. 

**Workaround:** Extract individual top-level blocks by brace-counting on the raw text, then parse each block independently. Blocks that fail are skipped; blocks that succeed are used. See `explore_save.py` for the reference implementation.

The `country` block specifically fails with `Expected '}', found '='` because it uses integer-keyed sub-blocks (`0={ ... }`) that ClauseWizard's grammar does not support. This requires a custom parser for the country block.

---

### Identifying the player's country ID

There is no reliable simple scalar `player=N` in 4.3. The player country is identified by cross-referencing `meta["player_portrait"]` against the `leaders` block:

```
leaders[id].portrait == meta["player_portrait"]  →  leaders[id].country == player_id
```

In the sample save, `meta["player_portrait"] = "inf9"` and all `inf9` leaders have `country: 0`, so the player country ID is `0`.

---

### Top-level gamestate scalars

| Field | Path | Example |
|-------|------|---------|
| In-game date | `extract_scalar(gs, "date")` | `"2205.07.01"` |
| Patch version | `extract_scalar(gs, "version")` | `"Cetus v4.3.5"` |

---

### `planets` block

Path: `planets["planet"][planet_id]`

| Field | Path | Example | Notes |
|-------|------|---------|-------|
| Planet name | `planet["name"]` | see below | Complex localisation dict |
| Planet class | `planet["planet_class"]` | `"pc_volcanic"` | |
| System ID | `planet["coordinate"]["origin"]` | `76` | Foreign key into `galactic_object` |
| Size | `planet["planet_size"]` | `14` | |

**Planet name resolution:**

```python
name_block = planet["name"]
if name_block.get("literal"):
    display_name = name_block["key"]          # "Skull Throne" — user-named/colonised planet
else:
    display_name = name_block.get("key", "")  # localisation key, e.g. "STAR_NAME_1_OF_1"
```

**Identifying colonised (player-owned) planets:**  
Colonised planets have `name.literal = True`. Uncolonised bodies use localisation keys. Additionally, check `planet["owner"]` (not yet confirmed in output — verify against a save with multiple colonies).

**Habitable planet classes** (non-exhaustive): `pc_continental`, `pc_tropical`, `pc_arid`, `pc_ocean`, `pc_tundra`, `pc_arctic`, `pc_desert`, `pc_savanna`, `pc_alpine`, `pc_volcanic` (with modifiers).  
**Non-habitable classes** (exclude from colony lists): `pc_a_star`, `pc_asteroid`, `pc_gas_giant`, `pc_frozen`, `pc_rare_crystal_asteroid`.

---

### `leaders` block

Path: `leaders[leader_id]`

Player leaders are identified by `leader["country"] == player_id`.

| Field | Path | Example | Notes |
|-------|------|---------|-------|
| Country | `leader["country"]` | `0` | Filter on this to get player leaders |
| Portrait | `leader["portrait"]` | `"inf9"` | Matches `meta["player_portrait"]` for player's species |
| Class | `leader["class"]` | `"commander"` | `commander`, `scientist`, `official`, `envoy` |
| Gender | `leader["gender"]` | `"female"` | |
| Age | `leader["age"]` | `36` | Integer years |
| Species | `leader["species"]` | `3422552065` | Foreign key into `species` block |
| Name | `leader["name"]["full_names"]` | see below | Localisation dict |
| Birth date | `leader["date"]` | `"2200.01.01"` | |
| Job | `leader["job"]` | `"low_tech_researcher"` | |
| Traits | `leader["traits"]` | TBD | Not visible in truncated output — verify |

**Leader name resolution:** TBD — `full_names` is a localisation dict. Likely needs variable substitution to get a readable name. May be simpler to use `full_names["key"]` as a raw identifier.

---

### `galactic_object` block (star systems)

Path: `galactic_object[object_id]`

| Field | Path | Example | Notes |
|-------|------|---------|-------|
| System name | `galactic_object[id]["name"]["key"]` | `"Jompron"` | Plain string — not a localisation key |
| Type | `galactic_object[id]["type"]` | `"star"` | |
| Star class | `galactic_object[id]["star_class"]` | `"sc_b"` | |
| Planet IDs | `galactic_object[id]["planet"]` | `[1135, 1136, …]` | List of `planets.planet` IDs |
| Hyperlanes | `galactic_object[id]["hyperlane"]` | `[{"to": 46, "length": 24}, …]` | |

**Home system lookup:**
```python
home_planet_id = country["capital"]           # TBD — verify path in country block
system_id = planets["planet"][home_planet_id]["coordinate"]["origin"]
home_system = galactic_object[system_id]["name"]["key"]
```

---

### `country` block

**Status: NOT YET EXTRACTABLE via ClauseWizard.**  
ClauseWizard 1.0.4 fails to parse integer-keyed sub-blocks (`0={ ... }`).

A custom parser is required. Fields expected at `country[player_id]` (paths TBD, pending custom parser implementation):

| Field | Expected path | Notes |
|-------|--------------|-------|
| Empire name | `country[id]["name"]` | |
| Adjective | `country[id]["adjective"]` | |
| Capital planet ID | `country[id]["capital"]` | Integer — look up in `planets` block |
| Ethics | `country[id]["ethos"]` or `["ethics"]` | TBD |
| Civics | `country[id]["civics"]` | TBD |
| Authority | `country[id]["authority"]` | TBD |
| Origin | `country[id]["origin"]` | TBD |
| Species ref | `country[id]["species"]` or `["starting_species"]` | Foreign key |
| Ruler leader ID | `country[id]["ruler"]` | Foreign key into `leaders` |
| Traditions | `country[id]["tradition_cats"]` | TBD |
| Ascension perks | `country[id]["ascension_perks"]` | TBD |
| Monthly income | `country[id]["budget"]` | TBD — sub-structure unknown |
| Fleet power | `country[id]["fleets_manager"]` | TBD |
| Tech | `country[id]["tech_status"]` | TBD |

---

### `war` block

Empty in sample save (early game). Structure TBD — verify against a save with active wars.

Expected fields per war entry: `name`, attacker country ID, defender country ID, start date, warscore. 

---

### `federation` block

Empty in sample save. Structure TBD.

---

## Open issues

1. **Country block parser** — the biggest blocker. Requires either a hand-rolled Clausewitz parser for integer-keyed blocks, or pre-processing the block text to rewrite `0={` as `"0"={` before handing to ClauseWizard.

2. **Leader name display** — `full_names` is a localisation dict. Determining the readable name string requires either localisation file lookup (out of scope) or a heuristic fallback using `key` + `portrait` as a readable identifier.

3. **Player country ID detection** — the portrait cross-reference approach works but is indirect. Check if `player` appears as a block (`player={ ... }`) in the raw gamestate text.

4. **Colonised planet ownership** — confirm `planet["owner"]` exists and equals `player_id` for the player's colonies, rather than relying on `name.literal`.

5. **Concluded wars** — unknown whether ended wars remain in the `war` block or are removed. Needs a save with at least one completed war.

6. **Species block** — not yet explored. Needed to resolve species name, portrait class, and traits from the foreign key in `leaders[id]["species"]` and `country[id]["species"]`.
