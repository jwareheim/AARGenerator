# Chronicle Companion Mod — Design Document v2.0

**Project:** Chronicle AAR Generator  
**Component:** Stellaris Workshop Mod + Chronicle Backend Integration  
**Scope:** In-game event tracking via `game.log` and Chronicle log ingestion pipeline  
**Depends On:** Chronicle Core (v1.x), Chronicle Companion Mod (v1.0)  
**Status:** Draft

---

## 1. Overview

Chronicle v1.x generates AAR narratives from a single save file snapshot — it knows the current state of the galaxy but has no visibility into how it got there. Design doc v2.0 introduces longitudinal event tracking: the companion mod instruments significant in-game events and writes structured log entries to `game.log` using a `CHRONICLE|` prefix protocol. Chronicle's backend ingests these log entries alongside the save parse, building an event timeline that is passed to Claude for richer, story-arc-aware narrative generation.

The result is the difference between:

> *"The Zethali Dominion controls 47 systems and is at war with the Hegemony of Vrak."*

and:

> *"The Zethali Dominion, once a modest federation of three worlds, rose to galactic prominence after Admiral Yara crushed the Hegemony of Vrak at the Battle of Keth Station in 2367 — a war the Dominion itself provoked after years of uneasy rivalry."*

---

## 2. Goals

- Capture the narrative spine of a campaign — wars, diplomacy, crises, key decisions — as structured log data the mod can emit without file I/O privileges
- Build a Chronicle backend pipeline that reads, parses, and correlates log entries with save state
- Pass the resulting event timeline to Claude as additional context for narrative generation
- Keep the mod lightweight, non-intrusive, and compatible with v1.0 of the companion mod
- Keep the log protocol simple enough that community contributors can add new event hooks without deep Chronicle knowledge

---

## 3. Non-Goals

- Replacing save file parsing — the log supplements the snapshot, it does not replace it
- Capturing every game event — only narratively significant events are tracked (see Section 5)
- Real-time Chronicle updates during a play session — Chronicle is still run manually against a save
- Supporting `game.log` as the sole data source — Chronicle requires a `.sav` file; the log is additive
- Ironman compatibility — unchanged from v1.0

---

## 4. The CHRONICLE Log Protocol

### 4.1 Entry Format

All mod-written log entries use a pipe-delimited format with a fixed prefix so Chronicle can extract them unambiguously from the noise of a standard `game.log`:

```
CHRONICLE|<version>|<event_type>|<date>|<field_1>|<field_2>|...|<field_n>
```

Fields:

| Field | Description |
|---|---|
| `CHRONICLE` | Fixed prefix, used as extraction filter |
| `version` | Protocol version integer (`1`). Allows Chronicle to handle format changes gracefully |
| `event_type` | Snake_case event category (e.g. `war_declared`, `leader_died`) |
| `date` | In-game date at time of event, format `YYYY.MM.DD` |
| `field_1..n` | Event-specific payload fields, defined per event type |

Example entries:

```
CHRONICLE|1|war_declared|2341.05.12|Zethali Dominion|Hegemony of Vrak|border_friction
CHRONICLE|1|war_ended|2344.02.01|Zethali Dominion|Hegemony of Vrak|attacker_victory|Dominion Ascendant
CHRONICLE|1|leader_died|2349.08.20|Admiral Yara Keth|admiral|war_hero|age_95
CHRONICLE|1|first_contact|2312.01.01|Zethali Dominion|Hegemony of Vrak
CHRONICLE|1|crisis_initiated|2387.03.15|contingency
CHRONICLE|1|player_choice|2355.11.04|event_id_distar.1|option_b|The Flesh is Weak
```

### 4.2 Clausewitz `log` Effect Usage

Each event hook fires a hidden country event that emits the log line. Clausewitz's `log` effect writes directly to `game.log` and supports localisation token substitution inline:

```
log = "CHRONICLE|1|war_declared|[Root.GetDate]|[Root.GetName]|[From.GetName]|[Root.GetWarGoal]"
```

String values that contain pipes must be sanitized. The localisation layer will strip or replace pipes in empire names and leader names with a defined safe character (`~`) so the parser is not confused. This is handled in the event scripting, not in Chronicle.

### 4.3 Log File Location

`game.log` is written to:

- **Windows:** `%USERPROFILE%\Documents\Paradox Interactive\Stellaris\logs\game.log`
- **Linux:** `~/.local/share/Paradox Interactive/Stellaris/logs/game.log`

Chronicle derives the log path from the save path — both live under the same Stellaris user data root. The backend resolves `../logs/game.log` relative to the saves directory it is already reading.

### 4.4 Log Persistence and Limitations

`game.log` is **session-scoped** — it is cleared on each game launch and does not accumulate across sessions. This is the protocol's primary constraint and shapes several design decisions:

- Chronicle must be run at least once per play session to capture that session's events before the next launch clears the log
- Chronicle stores parsed log entries in its own persistent event store (see Section 7) so longitudinal data survives across sessions
- The companion mod also writes durable `chronicle_*` country flags into the save file as a cross-reference index (see Section 6). These survive session boundaries and allow Chronicle to detect which events have already been ingested

---

## 5. Event Taxonomy

The following event types are in scope for v2.0. Each entry defines the type string, trigger condition, and payload fields.

### 5.1 War Events

| Type | Trigger | Payload Fields |
|---|---|---|
| `war_declared` | `on_war_start` | attacker, defender, war_goal |
| `war_ended` | `on_war_end` | attacker, defender, outcome, war_name |
| `war_white_peaced` | `on_war_end` (white peace) | attacker, defender |

### 5.2 Diplomatic Events

| Type | Trigger | Payload Fields |
|---|---|---|
| `first_contact` | `on_first_contact` | player_empire, contacted_empire |
| `federation_formed` | `on_federation_formed` | federation_name, founder |
| `federation_joined` | `on_federation_joined` | federation_name, joining_empire |
| `rival_declared` | `on_rival_declared` | declarer, target |
| `alliance_formed` | `on_defensive_pact_formed` | empire_a, empire_b |
| `subject_integrated` | `on_subject_integrated` | overlord, subject |

### 5.3 Leader Events

| Type | Trigger | Payload Fields |
|---|---|---|
| `ruler_elected` | `on_ruler_elected` | ruler_name, leader_class |
| `leader_died` | `on_leader_death` | leader_name, leader_class, trait_summary, age |
| `admiral_victorious` | `on_battle_won_space` (player) | admiral_name, system_name, enemy_empire |

### 5.4 Exploration and Expansion

| Type | Trigger | Payload Fields |
|---|---|---|
| `colony_founded` | `on_colony_created` | planet_name, system_name |
| `homeworld_lost` | `on_planet_lost` (homeworld) | planet_name, lost_to |
| `precursor_completed` | `on_precursor_completed` | precursor_name |
| `anomaly_discovered` | `on_anomaly_created` (significant) | anomaly_name, system_name |

### 5.5 Crisis Events

| Type | Trigger | Payload Fields |
|---|---|---|
| `crisis_initiated` | `on_crisis_start` | crisis_type |
| `crisis_ended` | `on_crisis_end` | crisis_type, outcome |
| `end_game_crisis_awakened` | `on_crisis_fleet_spawned` (first) | crisis_type |

### 5.6 Player Decisions

| Type | Trigger | Payload Fields |
|---|---|---|
| `player_choice` | Hooked on major story events | event_id, option_chosen, option_label |
| `ascension_perk_taken` | `on_ascension_perk_taken` | perk_name |
| `tradition_completed` | `on_tradition_completed` | tradition_name, tree_name |

### 5.7 Miscellaneous Narrative

| Type | Trigger | Payload Fields |
|---|---|---|
| `tech_breakthrough` | Tier 5 / rare tech researched | tech_name, tech_tier |
| `empire_defeated` | `on_country_eliminated` (player-adjacent) | eliminated_empire, eliminated_by |
| `chronicle_session_start` | `on_game_start` + `on_game_load` | empire_name, empire_id, game_date |

`chronicle_session_start` is critical — it anchors the session in the log and allows Chronicle to correlate which campaign a log file belongs to even if the player has multiple saves.

---

## 6. Save File Flag Index

Because `game.log` clears on each launch, the mod writes a parallel lightweight index into the save file using country flags. These are **not** the primary data store — they are a cross-reference Chronicle uses to detect what has already been ingested from previous sessions.

Flag naming convention:

```
chronicle_ingested_<event_type>_<YYYY_MM_DD>
```

Example:

```
set_country_flag = chronicle_ingested_war_declared_2341_05_12
```

Chronicle reads these flags from the save during parse, compares them against its local event store, and identifies any gaps — events that fired in previous sessions where the log has since been cleared. In that case Chronicle logs a warning noting incomplete event history for the affected date range. It does not fabricate missing events.

A `chronicle_session_id` variable (integer, auto-incremented by the mod on each `on_game_load`) is also written to save state, allowing Chronicle to sequence sessions correctly.

---

## 7. Chronicle Backend Changes

### 7.1 New Module: `log_reader.py`

Responsible for locating, reading, and parsing `game.log`. Runs as a pipeline stage after `stellaris-parser` completes save parsing.

```python
class ChronicleLogReader:
    def __init__(self, save_path: Path):
        self.log_path = self._resolve_log_path(save_path)
    
    def _resolve_log_path(self, save_path: Path) -> Path:
        # Traverse up from saves/ to Stellaris root, then down to logs/
        stellaris_root = save_path.parent.parent
        return stellaris_root / "logs" / "game.log"
    
    def extract_chronicle_entries(self) -> list[ChronicleLogEntry]:
        entries = []
        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("CHRONICLE|"):
                    entry = self._parse_entry(line.strip())
                    if entry:
                        entries.append(entry)
        return entries
    
    def _parse_entry(self, line: str) -> ChronicleLogEntry | None:
        parts = line.split("|")
        if len(parts) < 4:
            return None
        try:
            return ChronicleLogEntry(
                version=int(parts[1]),
                event_type=parts[2],
                date=parts[3],
                payload=parts[4:]
            )
        except (ValueError, IndexError):
            return None
```

### 7.2 New Module: `event_store.py`

Provides persistent storage for Chronicle log entries across sessions. Backed by a simple SQLite database stored in Chronicle's application data directory — no external dependencies, no server.

Schema:

```sql
CREATE TABLE chronicle_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     TEXT NOT NULL,
    session_id      INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    game_date       TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    ingested_at     TEXT NOT NULL
);

CREATE INDEX idx_campaign_date ON chronicle_events(campaign_id, game_date);
```

On each Chronicle run, `event_store.py` merges newly parsed log entries with the existing store, deduplicating by `(campaign_id, event_type, game_date)`.

### 7.3 Updated Pipeline Orchestration

The main Chronicle pipeline gains a new stage between save parse and Claude prompt construction:

```
1. stellaris-parser         → raw save data (existing)
2. save_parser.py           → structured SaveState object (existing)
3. log_reader.py            → current session ChronicleLogEntry list (new)
4. event_store.py           → merge + retrieve full campaign event timeline (new)
5. timeline_builder.py      → build ordered EventTimeline from store (new)
6. prompt_builder.py        → construct Claude prompt with save + timeline (updated)
7. claude_api.py            → generate narrative (existing)
```

### 7.4 New Module: `timeline_builder.py`

Converts the raw event store records for a campaign into a structured `EventTimeline` object suitable for prompt injection.

```python
@dataclass
class EventTimeline:
    campaign_id: str
    empire_name: str
    events: list[TimelineEvent]      # sorted by game_date
    coverage_gaps: list[DateRange]   # sessions where log was unavailable
    session_count: int
```

The timeline is serialized to a human-readable format for Claude context injection rather than passing raw JSON. Example serialized timeline block:

```
CAMPAIGN EVENT TIMELINE — Zethali Dominion (Campaign ID: zethali_20240101)
Coverage: 2300.01.01 – 2389.05.12 | Sessions: 4 | Gaps: none

2312.03.04  FIRST CONTACT      Met the Hegemony of Vrak (first alien contact)
2323.11.20  COLONY FOUNDED     Settled Keth Prime in the Keth system
2341.05.12  WAR DECLARED       Declared war on Hegemony of Vrak (border friction)
2344.02.01  WAR ENDED          Attacker victory — War name: Dominion Ascendant
2349.08.20  LEADER DIED        Admiral Yara Keth (admiral, war_hero) died age 95
2355.11.04  PLAYER CHOICE      distar.1 — chose: The Flesh is Weak
2367.01.01  ASCENSION PERK     Synthetic Evolution
2387.03.15  CRISIS INITIATED   The Contingency awakened
```

### 7.5 Updated Prompt Builder

The Claude prompt gains a new context section injected between the save state summary and the narrative instruction:

```python
def build_prompt(save_state: SaveState, timeline: EventTimeline) -> str:
    return f"""
You are generating an After Action Report for a Stellaris campaign.

## Empire State (Current Save)
{format_save_state(save_state)}

## Campaign Event Timeline
{format_timeline(timeline)}

## Narrative Instructions
Write a compelling AAR narrative in the style of an in-universe historical document.
Use the event timeline to establish story arc, cause and effect, and character moments.
The current save state represents the end point of this history.
Where timeline coverage gaps exist, acknowledge narrative uncertainty for that period.
Do not fabricate specific events not present in the timeline or save data.
"""
```

---

## 8. Mod File Structure Changes from v1.0

```
chronicle_companion/
├── descriptor.mod                          # version bump to 2.0
├── common/
│   └── on_actions/
│       ├── 00_chronicle_on_actions.txt     # existing save hook
│       └── 01_chronicle_event_hooks.txt    # new — all event type hooks
├── events/
│   ├── chronicle_events.txt                # existing notification event
│   └── chronicle_tracking_events.txt       # new — all tracking log events
├── interface/
│   └── chronicle_hud.gui                   # updated — session status display
└── localisation/
    └── english/
        └── chronicle_l_english.yml         # updated strings
```

---

## 9. Open Questions

| # | Question | Notes |
|---|---|---|
| 1 | Which `on_actions` are actually exposed in current Stellaris for `on_war_end`, `on_leader_death`, etc.? | Needs verification against modding wiki — some are confirmed, some may require workarounds via triggered events |
| 2 | Does `log` effect in Clausewitz support full localisation token resolution at write time? | Confirmed for `[Root.GetName]` and `[Root.GetDate]` — needs testing for `[From.GetName]` in war context |
| 3 | Can `player_choice` hooks fire reliably for vanilla story events without overwriting the vanilla event files? | May require copying and modifying vanilla event files, which breaks compatibility with other event mods |
| 4 | What is the maximum `game.log` size before Stellaris rotates or truncates it? | Long sessions may hit limits — needs testing at 50+ year campaign length |
| 5 | Should Chronicle warn the user if no `CHRONICLE\|` entries are found (mod not installed)? | Probably yes — graceful degradation to v1.x behavior with a UI prompt to install the companion mod |
| 6 | SQLite vs flat JSON file for the event store? | SQLite preferred for query flexibility; JSON acceptable if we want zero-dependency simplicity |

---

## 10. Upgrade Path from v1.0

Chronicle v2.0 is fully backward compatible with saves and sessions that have no companion mod log data. The pipeline degrades gracefully:

- If `game.log` is missing or contains no `CHRONICLE|` entries → skip timeline stage, generate v1.x-style snapshot narrative
- If event store is empty for the campaign → same fallback
- If coverage gaps exist → noted in the timeline block passed to Claude; Claude is instructed to acknowledge uncertainty for those periods

Users upgrading mid-campaign will have a partial timeline starting from the session they first installed v2.0 of the companion mod. Chronicle will note the gap in output.

---

## 11. Out of Scope for v2.0

- Automated session detection / Chronicle running as a background watcher process
- Any UI changes to the Chronicle desktop application beyond backend pipeline
- Non-English Stellaris installs (localisation token output language follows game language setting — may produce non-English strings in the log)
- Multiplayer campaign tracking
- Galaxy map screenshot correlation with timeline events (future doc candidate)
