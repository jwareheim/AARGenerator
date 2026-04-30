# Chronicle — Screenshot Feature Design Document

**Project:** Chronicle  
**Document:** Screenshot Integration  
**Version:** 1.1  
**Status:** Pre-development  
**Target Release:** Chronicle v0.4.0  
**Depends on:** Chronicle core v0.3.0 (chapters, export, full UI)  

---

## 1. Overview

This document covers adding screenshot support to Chronicle. Screenshots enrich the AAR by anchoring the narrative in actual game moments — a map at the height of a war, a planet view on colonization day, a diplomacy screen showing a hard-won alliance.

The feature supports two association modes:

- **Auto-pull** — Chronicle watches the Stellaris screenshot directory and automatically picks up screenshots taken during the period covered by a chapter
- **Manual drag-and-drop** — the user drags screenshots directly onto a chapter at any time, including before chapter generation (as placeholders)

Screenshots appear both **inline within prose** (at user-placed or placeholder positions) and in a **gallery at the end of each chapter**. Each screenshot gets an optional Claude-generated caption that the user can edit or clear.

All screenshots are copied into `chronicle_data/screenshots/` for portability — the AAR stays self-contained regardless of where the original files were.

---

## 2. User Flow

### 2.1 Auto-Pull Flow

```
User configures screenshot directory in Settings
  └── Path saved to chronicle_data/config.json

User plays Stellaris, takes screenshots (F12 / Steam overlay)
  └── Screenshots land in the configured directory
      └── Each screenshot has a filesystem timestamp

User uploads new .sav file
  └── Is this the first save? (no last_upload_time in meta.json)
      │
      ├── YES → First Upload Prompt (see Section 2.4)
      │         └── User chooses one of:
      │             ├── Select screenshots manually → opens file picker
      │             ├── Skip images for this chapter → auto-pull disabled for ch.1
      │             └── Specify session start time → datetime picker
      │                 └── Window becomes [specified_time, now]
      │                     └── Proceeds to normal scan below
      │
      └── NO → Normal auto-pull
                └── Window is [last_upload_time, now]
                    └── Server scans screenshot directory
                        └── Finds screenshots whose timestamps fall in window
                            └── Copies matches to chronicle_data/screenshots/chapter-N/pending/
                                └── Sends to Claude for auto-captioning (vision API)
                                    └── Screenshots shown as pending — user reviews
                                        └── User can approve, reorder, edit captions, or remove
```

### 2.2 Manual Drag-and-Drop Flow

```
User opens any chapter in Chronicle
  └── Drags image file(s) onto the chapter panel
      └── Screenshots copied to chronicle_data/screenshots/chapter-N/
          └── Claude auto-captions (optional, user can skip)
              └── Screenshot appears in chapter gallery
                  └── User can drag to reorder, edit caption, or remove

Placeholder flow (before chapter exists):
  User drags screenshots onto the Upload zone before uploading a .sav
  └── Screenshots stored as "pending" with no chapter assignment
      └── When chapter is generated, pending screenshots are offered for attachment
```

### 2.3 Inline Placement Flow

```
User is reading a chapter
  └── Clicks "Insert screenshot here" between prose paragraphs
      └── Picks from chapter's attached screenshots (or uploads a new one)
          └── Screenshot appears inline at that position
              └── Saved as an inline marker in the chapter JSON
                  └── Renders inline in UI and in Markdown export
```

### 2.4 First Upload Prompt

When no `last_upload_time` exists in `meta.json` (i.e. this is Chapter 1), Chronicle cannot automatically determine the session window. Instead, after the chapter is generated and displayed, a modal appears:

```
┌──────────────────────────────────────────────────────┐
│  📷  Add screenshots to Chapter 1?                   │
│                                                      │
│  Chronicle doesn't have a previous session           │
│  timestamp to scan from. How would you like to       │
│  handle screenshots for this chapter?                │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  🗂  Select screenshots manually             │   │
│  │     Browse or drag in specific files         │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  🕐  Specify when this session started       │   │
│  │     Chronicle will scan from that time       │   │
│  │                                              │   │
│  │     [ Apr 28, 2026  ▾ ]  [ 18:00  ▾ ]       │   │
│  │                                              │   │
│  │                          [Scan screenshots]  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  ⏭  Skip — no screenshots for Chapter 1     │   │
│  └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**Option A — Select manually:**  
Opens a standard file picker (or drag target). Selected files are copied directly to `chronicle_data/screenshots/chapter-001/` as confirmed screenshots, bypassing the pending/review step since the user made an explicit selection. Auto-captioning still runs.

**Option B — Specify session start time:**  
A datetime picker defaulting to 3 hours before `now` (a reasonable session length). Once confirmed, the scanner runs with the window `[specified_time, now]` and the normal pending review flow applies. The specified time is **not** saved as `last_upload_time` — that is always set to the actual wall-clock time of the upload so future windows are accurate.

**Option C — Skip:**  
Dismisses the modal. `last_upload_time` is still recorded as `now`, so the next upload will have a clean window. Manual drag-and-drop remains available at any time.

**Timing:** The prompt appears *after* chapter generation completes, not before — so it never blocks or delays the narrative generation. The chapter is fully readable before the user has to make any screenshot decision.

**Screenshot directory requirement:** The prompt only shows options A and C if no screenshot directory is configured. All three options are available if a directory is already set in Settings.

---

## 3. Architecture

### 3.1 New Server Routes

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chapters/<n>/screenshots` | Upload screenshot(s) to a chapter |
| `DELETE` | `/api/chapters/<n>/screenshots/<id>` | Remove a screenshot from a chapter |
| `PATCH` | `/api/chapters/<n>/screenshots/<id>` | Update caption, position, inline marker |
| `POST` | `/api/chapters/<n>/screenshots/<id>/caption` | Re-run Claude auto-caption |
| `GET` | `/api/screenshots/<chapter>/<filename>` | Serve screenshot image file |
| `POST` | `/api/config/screenshot-dir` | Save screenshot directory path |
| `GET` | `/api/screenshots/pending` | List unassigned screenshots |

### 3.3 Auto-Pull Logic

The scanner runs at the end of every `/api/upload` handler, after the chapter is generated. On first upload it is not called automatically — instead the first-upload prompt result is passed in directly.

```python
def scan_for_screenshots(screenshot_dir, session_start, session_end, chapter_id):
    """
    Finds screenshots taken between session_start and session_end.
    
    session_start = last_upload_time from meta.json (subsequent uploads)
                  = user-specified time from first-upload prompt (chapter 1)
    session_end   = now (time of current upload)
    
    Returns list of matched file paths, sorted by mtime.
    """
    if not screenshot_dir or not Path(screenshot_dir).exists():
        return []

    matched = []
    for f in Path(screenshot_dir).iterdir():
        if f.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if session_start <= mtime <= session_end:
            matched.append(f)

    return sorted(matched, key=lambda f: f.stat().st_mtime)


def is_first_upload():
    """Returns True if no last_upload_time exists in meta.json."""
    meta = load_meta()
    return meta.get('last_upload_time') is None
```

**Session window — normal flow:**
`last_upload_time` from `meta.json` → `now`. Updated to `now` after every successful upload.

**Session window — first upload, user specified time:**
`user_specified_datetime` → `now`. The specified time is used only for the scan — `last_upload_time` is still recorded as `now` so future windows are accurate.

**First upload, manual selection:**
`scan_for_screenshots()` is not called. Files chosen by the user are copied directly as confirmed (no pending step).

**First upload, skipped:**
`scan_for_screenshots()` is not called. `last_upload_time` is recorded as `now`.

### 3.4 Screenshot Storage

All screenshots are copied into:

```
chronicle_data/
└── screenshots/
    ├── chapter-001/
    │   ├── scr-001-a.png          ← copied from source, renamed
    │   ├── scr-001-b.png
    │   └── pending/               ← auto-pulled but not yet confirmed
    │       └── scr-001-c.png
    ├── chapter-002/
    │   └── scr-002-a.png
    └── unassigned/                ← dragged in before chapter exists
        └── scr-pending-xyz.png
```

**Filename convention:** `scr-{chapter_id}-{sequence}.{ext}` — predictable, collision-free, human-readable.

**Why copy instead of reference by path?**  
Referencing by path breaks if the user moves their screenshots folder, renames files, or shares the `chronicle_data/` directory. Copying makes the AAR self-contained and portable.

**Size consideration:** Stellaris screenshots at 1080p are typically 1–4MB as PNG. With a cap of 3 per chapter and potentially 20 chapters, worst case is ~240MB of screenshots in `chronicle_data/`. This is acceptable. The `.gitignore` already excludes `chronicle_data/`.

---

## 4. Data Schema Changes

### 4.1 Chapter JSON — Updated

```json
{
  "id": 3,
  "title": "The Long War",
  "date_from": "2287.01.01",
  "date_to": "2310.06.15",
  "prose": "Thirty-one years had passed since...",
  "word_count": 512,
  "delta_events": ["..."],
  "generated_at": "2026-04-28T18:00:00Z",

  "screenshots": [
    {
      "id": "scr-003-a",
      "filename": "scr-003-a.png",
      "caption": "The Keth war fleet assembles at the Outer Veil, 2287.",
      "caption_source": "claude",
      "caption_edited": false,
      "inline_after_paragraph": 2,
      "confirmed": true,
      "added_at": "2026-04-28T19:00:00Z"
    },
    {
      "id": "scr-003-b",
      "filename": "scr-003-b.png",
      "caption": null,
      "caption_source": null,
      "caption_edited": false,
      "inline_after_paragraph": null,
      "confirmed": true,
      "added_at": "2026-04-28T19:05:00Z"
    }
  ],

  "screenshots_pending": [
    {
      "id": "scr-003-c",
      "filename": "scr-003-c.png",
      "caption": "Fleet engages at Davar — auto-pulled, awaiting review.",
      "caption_source": "claude",
      "confirmed": false
    }
  ]
}
```

**Key fields:**

| Field | Description |
|---|---|
| `id` | Stable identifier for this screenshot within the chapter |
| `filename` | File in `chronicle_data/screenshots/chapter-N/` |
| `caption` | Display caption, or `null` if none |
| `caption_source` | `"claude"`, `"user"`, or `null` |
| `caption_edited` | `true` if user has modified the Claude caption |
| `inline_after_paragraph` | Integer paragraph index for inline placement, or `null` for gallery-only |
| `confirmed` | `false` = pending review (auto-pulled candidate); `true` = attached |

### 4.2 Meta JSON — Updated

```json
{
  "empire_name": "Keth Dominion",
  "chapter_count": 3,
  "last_upload_time": "2026-04-28T18:00:00Z",
  "screenshot_dir": "C:/Users/James/Documents/Paradox Interactive/Stellaris/screenshots"
}
```

`last_upload_time` is updated on every successful save upload. Used as the left bound of the auto-pull time window.

---

## 5. Claude Vision — Auto-Captioning

Chronicle uses the Anthropic vision API to generate captions for screenshots. The model receives the image and a brief context prompt.

### 5.1 Caption Prompt

```
You are captioning a screenshot for a Stellaris After Action Report.
The player's empire is the {empire_name} ({species_name}).
This screenshot is from Chapter {n}, covering {date_from} to {date_to}.

Write a single caption sentence (15–25 words) for this screenshot as it 
would appear in a historical chronicle. Do not mention UI elements, 
menus, or game mechanics. Describe what is shown as if it were a real 
historical image. Write in past tense.

Examples of good captions:
- "The Keth war fleet assembles at the Outer Veil before the first campaign, 2287."
- "Davar Prime, newly colonized, seen from orbit in the early years of expansion."
- "Emperor Vorlan I signs the Treaty of Keth, ending the Hegemony War."
```

### 5.2 When Captioning Runs

- **Auto-pull:** Captions generated automatically for all auto-pulled screenshots as part of the upload pipeline. Runs in a background thread so it doesn't block the chapter generation stream
- **Manual upload:** Caption generated immediately on drop. User sees a "Captioning..." spinner on the screenshot thumbnail, then the caption appears
- **Regenerate:** User can click "Recaption" on any screenshot to run the vision API again
- **Skip:** User can dismiss the caption field entirely — a screenshot with `caption: null` renders without a caption in both UI and export

### 5.3 Cost Consideration

Vision API calls cost more than text calls. At 1–3 screenshots per chapter and a typical run of 10–20 chapters, this is 10–60 vision API calls per campaign — negligible in practice. No rate limiting or batching needed at this scale.

### 5.4 Model

Use `claude-sonnet-4-20250514` (same as chapter generation) with the image passed as base64:

```python
def generate_caption(image_path, empire_name, species_name, chapter_meta):
    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')
    
    ext = Path(image_path).suffix.lower().lstrip('.')
    media_type = 'image/png' if ext == 'png' else 'image/jpeg'

    response = anthropic.Anthropic(api_key=api_key).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    }
                },
                {
                    "type": "text",
                    "text": build_caption_prompt(empire_name, species_name, chapter_meta)
                }
            ]
        }]
    )
    return response.content[0].text.strip()
```

---

## 6. UI Changes

### 6.1 Settings — Screenshot Directory

A new field in the Settings modal:

```
Screenshot Directory
[C:\Users\James\...\Stellaris\screenshots]  [Browse]

Chronicle will automatically pick up screenshots taken during each
play session and offer them for attachment to the matching chapter.
Leave blank to disable auto-pull.
```

The default Stellaris screenshot path by platform:

| Platform | Default Path |
|---|---|
| Windows | `%USERPROFILE%\Documents\Paradox Interactive\Stellaris\screenshots` |
| Linux | `~/.local/share/Paradox Interactive/Stellaris/screenshots` |

Chronicle attempts to pre-populate this field on first launch by checking whether the default path exists.

### 6.2 Chapter View — Screenshot Panel

Below the chapter prose, a new collapsible section:

```
┌─────────────────────────────────────────────────────┐
│  SCREENSHOTS  (2 attached · 1 pending review)   [+] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [thumbnail]  [thumbnail]                           │
│  The Keth war  Davar Prime,                        │
│  fleet, 2287.  from orbit.                         │
│  ✎ edit  ✕    ✎ edit  ✕                           │
│                                                     │
│  ─── PENDING REVIEW ───                            │
│  [thumbnail]                                        │
│  Fleet engages at Davar.                           │
│  [✓ Attach]  [✕ Dismiss]                           │
│                                                     │
│  [Drag screenshots here or click to browse]         │
└─────────────────────────────────────────────────────┘
```

**Interactions:**
- Click thumbnail → full-size preview overlay
- ✎ edit → inline text edit for caption
- ✕ → remove screenshot (with confirmation)
- Drag thumbnails to reorder within the panel (order = gallery order)
- "Attach" on pending → moves to confirmed, copies to chapter folder
- "Dismiss" on pending → removes from pending, deletes from pending folder

### 6.3 Inline Placement

In the prose reading panel, paragraph breaks show a subtle affordance on hover:

```
...the Keth fleet crossed the Outer Veil.

    [+ Insert screenshot]          ← appears on hover between paragraphs

Thirty-one years of warfare followed...
```

Clicking "Insert screenshot" opens a picker showing the chapter's confirmed screenshots. Selecting one inserts it inline at that paragraph position and saves `inline_after_paragraph` to the chapter JSON.

An inline screenshot renders as:

```
...the Keth fleet crossed the Outer Veil.

┌──────────────────────────────────┐
│  [screenshot image]              │
│  The Keth war fleet, 2287.       │
└──────────────────────────────────┘

Thirty-one years of warfare followed...
```

### 6.4 Pending Screenshot Notification

When auto-pulled screenshots are waiting, a badge appears on the chapter in the sidebar:

```
│ Ch.3  2310 ◀  📷 1 pending │
```

Clicking the chapter clears the badge and scrolls to the pending review section.

---

## 7. Export Changes

### 7.1 Markdown Export

Screenshots are exported as standard Markdown image syntax, with paths relative to the export file location. On export, Chronicle copies the `chronicle_data/screenshots/` tree alongside the Markdown file.

**Inline screenshot:**
```markdown
The Keth fleet crossed the Outer Veil.

![The Keth war fleet, 2287.](screenshots/chapter-003/scr-003-a.png)
*The Keth war fleet, 2287.*

Thirty-one years of warfare followed...
```

**End-of-chapter gallery:**
```markdown
---

### Chapter 3 — Images

![The Keth war fleet, 2287.](screenshots/chapter-003/scr-003-a.png)
*The Keth war fleet, 2287.*

![Davar Prime from orbit.](screenshots/chapter-003/scr-003-b.png)
*Davar Prime from orbit.*
```

**Export directory structure:**
```
chronicle-export/
├── chronicle.md              ← full AAR
└── screenshots/
    ├── chapter-001/
    │   └── scr-001-a.png
    ├── chapter-002/
    └── chapter-003/
        ├── scr-003-a.png
        └── scr-003-b.png
```

This structure means the Markdown renders correctly with relative paths in any Markdown viewer, GitHub, Obsidian, etc.

---

## 8. Placeholder Support

A placeholder is a screenshot slot in a chapter that has no image attached yet — just a label and an optional note. Intended for users who want to mark "I'll add a screenshot of the war declaration screen here" during writing but haven't taken or located the screenshot yet.

### 8.1 Creating a Placeholder

In the inline insertion picker, a "Add placeholder" option appears alongside confirmed screenshots:

```
[Screenshot A]  [Screenshot B]  [+ Add placeholder]
```

Selecting "Add placeholder" prompts for an optional label:

```
Label (optional): "War declaration screen"
[Add Placeholder]
```

### 8.2 Placeholder Rendering

In the UI, placeholders render as a dashed box:

```
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  📷 War declaration screen
  [Attach screenshot]  [Remove]
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

Clicking "Attach screenshot" opens a file picker. Attaching an image replaces the placeholder with the real screenshot (and triggers auto-captioning).

### 8.3 Placeholder in Export

Placeholders are exported as a Markdown comment so they're visible in the source but don't render in readers:

```markdown
<!-- PLACEHOLDER: War declaration screen -->
```

Or optionally as a visible note if the user prefers:

```markdown
*[Screenshot: War declaration screen — to be added]*
```

The export option for placeholder behavior (comment vs. visible note) is a setting in the Export dialog.

### 8.4 Placeholder Schema

```json
{
  "id": "ph-003-a",
  "type": "placeholder",
  "label": "War declaration screen",
  "inline_after_paragraph": 3,
  "created_at": "2026-04-28T20:00:00Z"
}
```

Placeholders live in the same `screenshots` array as real screenshots, distinguished by `"type": "placeholder"`. Real screenshots have `"type": "screenshot"` (default, can be omitted for backward compat).

---

## 9. Repository Changes

### 9.1 `chronicle.py` additions

New functions/sections added to the single file:

```
├── [5b] SCREENSHOT SCANNER
│     scan_for_screenshots(screenshot_dir, session_start, session_end)
│     copy_screenshot(src_path, chapter_id, sequence) -> dest_path
│     detect_default_screenshot_dir() -> path or None
│
├── [8b] CAPTION GENERATION
│     generate_caption(image_path, empire_name, chapter_meta) -> str
│     build_caption_prompt(empire_name, species_name, chapter_meta) -> str
│
└── [9] HTTP REQUEST HANDLER — new routes added
      POST /api/chapters/<n>/screenshots
      DELETE /api/chapters/<n>/screenshots/<id>
      PATCH /api/chapters/<n>/screenshots/<id>
      POST /api/chapters/<n>/screenshots/<id>/caption
      GET /api/screenshots/<chapter>/<filename>
      POST /api/config/screenshot-dir
      GET /api/screenshots/pending
```

### 9.2 Embedded HTML additions

New UI components added to the embedded `HTML_PAGE` string:

- Screenshot panel below chapter prose
- Inline insertion affordance between paragraphs
- Placeholder creation flow
- Pending review section
- Settings field for screenshot directory
- Full-size preview overlay

### 9.3 `chronicle_data/` layout additions

```
chronicle_data/
└── screenshots/              ← NEW
    ├── chapter-001/
    │   ├── scr-001-a.png
    │   └── pending/
    ├── chapter-002/
    └── unassigned/           ← screenshots dragged in with no chapter yet
```

---

## 10. Limitations & Edge Cases

**Timestamp ambiguity.** Auto-pull relies on screenshot file modification times matching the session window. If the user:
- Edits a screenshot in an external tool (changes mtime)
- Copies screenshots from another device
- Takes screenshots outside the active session

...those screenshots will be incorrectly included or excluded. The pending review step exists specifically to catch this — nothing is auto-attached without user confirmation.

**Screenshot cap.** The design targets 1–3 screenshots per chapter. The UI doesn't hard-enforce a cap, but the pending review UI makes it natural to select only the best ones. A soft warning ("You have 5 screenshots attached — consider trimming for readability") could be added later.

**Large images.** If a user drags in a very large image (e.g. a 4K PNG at 15MB), the copy operation and base64 encoding for the vision API could be slow. Add a file size check on upload (warn if > 10MB, reject if > 25MB).

**Vision API unavailability.** If the Claude vision API call fails, the screenshot is still attached — captioning just fails silently with `caption: null`. The user can manually type a caption or retry via "Recaption."

**Non-Stellaris screenshots.** The scanner has no way to know if a screenshot is actually from Stellaris vs. another game that saves to the same folder. The user's review step is the safeguard.

---

## 11. Phased Rollout

### Phase 1 — Manual only (v0.4.0)
- Drag-and-drop screenshots onto any chapter
- Copy to `chronicle_data/screenshots/chapter-N/`
- Auto-caption via Claude vision on drop
- Caption editing
- Gallery at end of chapter
- Export with screenshot folder

### Phase 2 — Placeholders (v0.4.1)
- Inline insertion between paragraphs
- Placeholder creation and rendering
- Placeholder export (comment or visible note)
- Reordering via drag within screenshot panel

### Phase 3 — Auto-pull (v0.5.0)
- Screenshot directory config in Settings
- Default path auto-detection
- Session window scanner on save upload
- Pending review UI with badge on sidebar
- `last_upload_time` tracking in meta.json

### Phase 4 — Polish (future)
- Full-size preview overlay
- Soft cap warning (>3 screenshots)
- File size validation on upload
- "Recaption" button per screenshot
- Bulk dismiss all pending

---

*Document prepared April 2026. v1.1 — added first-upload prompt for auto-pull session window.*  
*Target: Chronicle v0.4.0 (Phase 1 manual), v0.5.0 (Phase 3 auto-pull).*
