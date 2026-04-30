# Multi-Campaign Support — Design Draft

## Overview

Chronicle currently supports a single active campaign stored flat in `chronicle_data/`. This doc covers what it would take to support multiple campaigns with a UI for switching between them and deleting old ones.

---

## Current Data Layout

```
chronicle_data/
  config.json          ← global (API key, model, word target)
  meta.json            ← campaign identity (empire, dates, chapter count)
  baseline.json        ← last parsed save snapshot
  summary.json         ← rolling narrative summary
  chapters/
    chapter-001.json
    chapter-002.json
    ...
```

Everything except `config.json` is campaign-scoped but lives at the top level, so there's no room for a second campaign without collisions.

---

## Proposed Data Layout

```
chronicle_data/
  config.json                    ← global (unchanged)
  campaigns/
    {campaign-id}/
      meta.json
      baseline.json
      summary.json
      chapters/
        chapter-001.json
        ...
```

`campaign-id` is a short slug generated at campaign creation time — e.g. `camp-1`, or a sanitised version of the campaign name. ULIDs or UUIDs are not necessary; the id just needs to be unique within the local `campaigns/` directory.

A lightweight `campaigns/index.json` tracks the list of known campaigns and the active one:

```json
{
  "active": "camp-1",
  "campaigns": [
    { "id": "camp-1", "name": "United Nations of Earth", "created_at": "2200.01.01" },
    { "id": "camp-2", "name": "Determined Exterminators", "created_at": "2250.04.12" }
  ]
}
```

---

## API Changes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/campaigns` | List all campaigns + active id |
| POST | `/api/campaigns` | Create new campaign (returns new id) |
| POST | `/api/campaigns/{id}/activate` | Switch active campaign |
| DELETE | `/api/campaigns/{id}` | Delete a campaign and all its data |
| GET | `/api/chapters` | Same as today, scoped to active campaign |
| POST | `/api/upload` | Same as today, scoped to active campaign |

All existing routes (`/api/upload`, `/api/chapters`, `/api/meta`, etc.) continue to operate on the **active campaign** — no path changes needed for them.

---

## Storage Layer Changes

Every function that currently references `DATA_DIR` directly needs to be updated to accept or resolve a campaign directory:

- `load_meta / save_meta`
- `load_baseline / save_baseline`
- `load_summary / save_summary`
- `load_chapter / save_chapter / list_chapters`

The cleanest approach is a `campaign_dir(campaign_id: str) -> Path` helper that resolves `DATA_DIR / "campaigns" / campaign_id`, then thread it through the above functions as a parameter (defaulting to the active campaign when not specified).

`load_config / save_config` are global and do not change.

---

## UI Changes

### Sidebar header

Replace the static campaign name label with a small dropdown or switcher:

```
[ United Nations of Earth ▾ ]
```

Clicking opens a panel listing campaigns with:
- Campaign name (click to activate)
- Chapter count + word count
- Delete button (with confirmation)
- "+ New campaign" button at the bottom

### New campaign flow

1. User clicks "+ New campaign"
2. Prompted for a name (or left blank to be named after the first upload's empire)
3. A new campaign id is created, written to `index.json`, and set as active
4. The chapter list clears; upload zone is ready for the first save

### Delete flow

1. User clicks delete on a non-active campaign → confirmation prompt → campaign directory removed, removed from `index.json`
2. User tries to delete the **active** campaign → must first switch to another campaign (or it's the last one, in which case confirm a full reset)

---

## Migration

Existing `chronicle_data/` installations (pre-multi-campaign) need a one-time migration on startup:

1. Check if `chronicle_data/campaigns/` exists. If not, assume legacy layout.
2. Create `chronicle_data/campaigns/camp-1/`
3. Move `meta.json`, `baseline.json`, `summary.json`, `chapters/` into it
4. Write `chronicle_data/campaigns/index.json` with `"active": "camp-1"`

This runs transparently before the server starts accepting requests.

---

## Open Questions

- **Campaign name vs empire name**: currently `meta.json` stores `empire_name` (from the save) and `campaign_name` (user-set). With multi-campaign, both should live in the campaign's `meta.json`. The `index.json` entry stores a display name which defaults to `campaign_name` → `empire_name` → the campaign id.
- **Import/export**: should exporting a campaign (`/api/export`) include enough metadata to re-import it on another machine? Out of scope for this iteration.
- **Campaign id stability**: if a user manually renames the campaign directory, `index.json` will point to a missing id. Validate on startup and surface a clear error rather than silently breaking.

---

## Implementation Order

1. Storage layer refactor (campaign_dir helper + update all load/save functions)
2. Migration logic in `main()`
3. New API routes (`/api/campaigns`)
4. UI switcher panel
5. Delete flow with confirmation
6. New campaign flow

The single-file constraint means all of this stays in `chronicle.py`. Estimated scope: Phase 4 or an early Phase 3 addition once the core read/write loop is stable.
