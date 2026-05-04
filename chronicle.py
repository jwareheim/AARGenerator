# Chronicle — Stellaris AAR Generator
# https://github.com/jwareheim/chronicle
# GNU General Public License v3 — see LICENSE for details

__version__ = "0.1.0"

# =============================================================================
# [1] DEPENDENCY BOOTSTRAP
# =============================================================================

import sys
import subprocess

REQUIRED = {
    "anthropic": "anthropic",
}


def check_and_install_deps():
    missing = []
    for import_name, pip_name in REQUIRED.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append((import_name, pip_name))

    if not missing:
        return

    print("Chronicle: installing missing dependencies...")
    for import_name, pip_name in missing:
        print(f"  Installing {pip_name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  ✓ {pip_name} installed")

    print("Dependencies ready.\n")


check_and_install_deps()


# =============================================================================
# [2] IMPORTS
# =============================================================================

import http.server
import json
import os
import pathlib
import shutil
import socketserver
import tempfile
import threading
import time
import webbrowser
from datetime import datetime, timezone

import anthropic


# =============================================================================
# [3] CONFIGURATION & CONSTANTS
# =============================================================================

PORT = 8765
SCRIPT_DIR = pathlib.Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "chronicle_data"
CHAPTERS_DIR = DATA_DIR / "chapters"

PARSER_VERSION = "1.0.0"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_WORD_TARGET = 500

SYSTEM_PROMPT = (
    "You are a science fiction author writing an After Action Report for a "
    "Stellaris campaign. Write in the style of a sweeping historical chronicle "
    "— dramatic, with a sense of destiny unfolding. Use the empire's ethics "
    "and civics to inform the narrative voice. Never reference game mechanics "
    'directly ("fleet power", "energy credits", "alloys") — translate '
    "everything into in-universe language. Write in past tense. Be vivid but "
    "concise."
)


# =============================================================================
# [4] STORAGE LAYER
# =============================================================================

def _read_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    return _read_json(DATA_DIR / "config.json")


def save_config(data: dict):
    _write_json(DATA_DIR / "config.json", data)


def load_meta() -> dict:
    return _read_json(DATA_DIR / "meta.json")


def save_meta(data: dict):
    _write_json(DATA_DIR / "meta.json", data)


def load_baseline() -> dict:
    return _read_json(DATA_DIR / "baseline.json")


def save_baseline(data: dict):
    _write_json(DATA_DIR / "baseline.json", data)


def load_summary() -> dict:
    return _read_json(DATA_DIR / "summary.json")


def save_summary(data: dict):
    _write_json(DATA_DIR / "summary.json", data)


def _chapter_path(n: int) -> pathlib.Path:
    return CHAPTERS_DIR / f"chapter-{n:03d}.json"


def load_chapter(n: int) -> dict:
    return _read_json(_chapter_path(n))


def save_chapter(n: int, data: dict):
    _write_json(_chapter_path(n), data)


def list_chapters() -> list[dict]:
    if not CHAPTERS_DIR.exists():
        return []
    chapters = []
    for path in sorted(CHAPTERS_DIR.glob("chapter-*.json")):
        ch = _read_json(path)
        chapters.append({
            "id": ch.get("id"),
            "title": ch.get("title", f"Chapter {ch.get('id')}"),
            "date_from": ch.get("date_from"),
            "date_to": ch.get("date_to"),
            "word_count": ch.get("word_count", 0),
        })
    return chapters


def get_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    config = load_config()
    return config.get("api_key") or None


# =============================================================================
# [5] SAVE PARSER
# =============================================================================

def get_parser_binary() -> pathlib.Path:
    exe = "stellaris-parser.exe" if sys.platform == "win32" else "stellaris-parser"
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys._MEIPASS) / exe
    return SCRIPT_DIR / "bin" / exe


def ensure_parser_binary():
    binary = get_parser_binary()
    if binary.exists():
        return
    if getattr(sys, "frozen", False):
        raise RuntimeError(f"Parser binary missing from frozen package at {binary}.")

    import urllib.request
    import stat as _stat

    platform_name = "stellaris-parser.exe" if sys.platform == "win32" else "stellaris-parser"
    url = (
        f"https://github.com/jwareheim/AARGenerator/releases/download"
        f"/v{PARSER_VERSION}/{platform_name}"
    )
    print(f"Chronicle: downloading parser binary ({platform_name})...")
    try:
        binary.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, str(binary))
        if sys.platform != "win32":
            binary.chmod(binary.stat().st_mode | _stat.S_IEXEC)
        print("  ✓ parser binary ready")
    except Exception as exc:
        raise RuntimeError(
            f"Could not download parser binary: {exc}\n"
            f"Download manually: {url}\n"
            f"Place it at: {binary}"
        )


def _raise_parser_error(code: int, detail: str):
    messages = {
        1: "Save file could not be read.",
        2: "Not a valid Stellaris save file.",
        3: f"Could not parse save: {detail}",
        4: "Could not identify player country in this save.",
        5: (
            "This save uses a binary-encoded format that is not supported. "
            "Verify the save is from Stellaris 3.x or later."
        ),
    }
    raise ValueError(messages.get(code, f"Parser failed (exit {code}): {detail}"))


def parse_save(file_bytes: bytes) -> dict:
    binary = get_parser_binary()
    if not binary.exists():
        raise RuntimeError(
            f"Parser binary not found at {binary}. "
            "Run Chronicle once normally to auto-download it, or see CONTRIBUTING.md."
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as f:
            f.write(file_bytes)
            tmp_path = f.name

        result = subprocess.run(
            [str(binary), "extract", tmp_path],
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            _raise_parser_error(result.returncode, detail)

        raw = json.loads(result.stdout.decode("utf-8"))
        return extract_relevant_data(raw)

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def extract_relevant_data(raw: dict) -> dict:
    empire = raw.get("empire", {})
    state = raw.get("state", {})
    ruler_raw = raw.get("ruler", {})
    diplomacy = raw.get("diplomacy", {})
    fed = diplomacy.get("federation")

    return {
        "date": raw.get("date", "unknown"),
        "empire_name": empire.get("name") or "unknown",
        "species_name": empire.get("species_name") or "unknown",
        "portrait_class": empire.get("species_class") or "unknown",
        "species_traits": empire.get("species_traits", []),
        "ethics": empire.get("ethics", []),
        "civics": empire.get("civics", []),
        "authority": empire.get("authority") or "unknown",
        "origin": empire.get("origin") or "unknown",
        "home_planet": empire.get("home_planet") or "unknown",
        "home_system": empire.get("home_system") or "unknown",
        "patch_version": raw.get("patch_version") or "unknown",
        "planets": state.get("owned_planets", []),
        "pop_count": state.get("total_pops", 0),
        "fleet_power": state.get("fleet_power", 0),
        "income": {
            "energy": state.get("monthly_energy", 0),
            "minerals": state.get("monthly_minerals", 0),
            "alloys": state.get("monthly_alloys", 0),
        },
        "traditions": state.get("traditions", []),
        "perks": state.get("ascension_perks", []),
        "ruler": {
            "id": ruler_raw.get("id"),
            "name": ruler_raw.get("name"),
            "class": ruler_raw.get("class"),
            "age": ruler_raw.get("age"),
            "gender": ruler_raw.get("gender"),
            "traits": ruler_raw.get("traits", []),
        },
        "leaders": [
            {
                "id": l.get("id"),
                "name": l.get("name"),
                "class": l.get("class"),
                "age": l.get("age"),
                "gender": l.get("gender"),
                "traits": l.get("traits", []),
            }
            for l in raw.get("leaders", [])
        ],
        "wars": raw.get("wars", []),
        "federation": {
            "name": fed.get("name"),
            "members": fed.get("members", []),
            "player_role": fed.get("player_role"),
        } if fed else None,
        "subjects": diplomacy.get("subjects", []),
        "rivals": diplomacy.get("rivals", []),
        "allies": diplomacy.get("allies", []),
        "recent_techs": state.get("recent_technologies", []),
    }


# =============================================================================
# [6] DIFF ENGINE
# =============================================================================

def diff_snapshots(baseline: dict, current: dict) -> list[dict]:
    if not baseline:
        return []

    deltas = []

    # Wars
    baseline_war_ids = {w.get("id") for w in baseline.get("wars", [])}
    current_war_ids = {w.get("id") for w in current.get("wars", [])}

    for war in current.get("wars", []):
        if war.get("id") not in baseline_war_ids:
            deltas.append({"type": "war_started", "weight": 1, "data": war})

    for war in baseline.get("wars", []):
        if war.get("id") not in current_war_ids:
            deltas.append({"type": "war_ended", "weight": 1, "data": war})

    # Leaders / ruler
    baseline_leader_ids = {l.get("id") for l in baseline.get("leaders", [])}
    for leader in baseline.get("leaders", []):
        if leader.get("id") not in {l.get("id") for l in current.get("leaders", [])}:
            deltas.append({"type": "leader_died", "weight": 2, "data": leader})

    if baseline.get("ruler", {}).get("name") != current.get("ruler", {}).get("name"):
        deltas.append({"type": "ruler_changed", "weight": 2, "data": current.get("ruler", {})})

    # Territorial
    baseline_planets = set(baseline.get("planets", []))
    current_planets = set(current.get("planets", []))
    for planet in current_planets - baseline_planets:
        deltas.append({"type": "planet_colonized", "weight": 3, "data": {"name": planet}})
    for planet in baseline_planets - current_planets:
        deltas.append({"type": "planet_lost", "weight": 3, "data": {"name": planet}})

    # Tech / perks
    baseline_techs = set(baseline.get("recent_techs", []))
    for tech in current.get("recent_techs", []):
        if tech not in baseline_techs:
            deltas.append({"type": "tech_researched", "weight": 4, "data": {"tech": tech}})

    baseline_perks = set(baseline.get("perks", []))
    for perk in current.get("perks", []):
        if perk not in baseline_perks:
            deltas.append({"type": "perk_taken", "weight": 4, "data": {"perk": perk}})

    # Date delta always included
    deltas.append({
        "type": "date_delta",
        "weight": 99,
        "data": {"from": baseline.get("date"), "to": current.get("date")},
    })

    deltas.sort(key=lambda d: d["weight"])
    return deltas


# =============================================================================
# [7] PROMPT BUILDER
# =============================================================================

def build_origin_prompt(snapshot: dict) -> str:
    leaders_summary = ", ".join(
        f"{l.get('name')} ({l.get('class', 'unknown')})"
        for l in snapshot.get("leaders", [])
    ) or "none"

    return (
        "Write Chapter 1 of this AAR. This is the origin — establish who this "
        "empire is, their home, their character, and the galaxy they are about "
        "to enter. 400–600 words.\n\n"
        f"EMPIRE\n"
        f"Name: {snapshot['empire_name']}\n"
        f"Species: {snapshot['species_name']} ({snapshot['portrait_class']})\n"
        f"Traits: {', '.join(snapshot['species_traits']) or 'none'}\n"
        f"Ethics: {', '.join(snapshot['ethics']) or 'none'}\n"
        f"Civics: {', '.join(snapshot['civics']) or 'none'}\n"
        f"Authority: {snapshot['authority']}\n"
        f"Origin: {snapshot['origin']}\n"
        f"Home: {snapshot['home_planet']}, {snapshot['home_system']} system\n\n"
        f"STATE — {snapshot['date']}\n"
        f"Planets: {len(snapshot['planets'])} ({', '.join(snapshot['planets'][:5])})\n"
        f"Ruler: {snapshot['ruler'].get('name', 'unknown')}, "
        f"{', '.join(snapshot['ruler'].get('traits', []))}\n"
        f"Leaders: {leaders_summary}\n"
    )


def build_chapter_prompt(n: int, delta: list[dict], snapshot: dict, summary: dict) -> str:
    summary_text = summary.get("text", "No prior history.")
    date_from = next(
        (d["data"]["from"] for d in delta if d["type"] == "date_delta"), "unknown"
    )
    date_to = next(
        (d["data"]["to"] for d in delta if d["type"] == "date_delta"), snapshot["date"]
    )

    events_lines = []
    for d in delta:
        if d["type"] == "date_delta":
            continue
        events_lines.append(f"- [{d['type']}] {json.dumps(d['data'])}")
    events_text = "\n".join(events_lines) or "- (No major events detected)"

    return (
        f"Story so far:\n{summary_text}\n\n"
        f"Write Chapter {n} of this AAR, covering {date_from} to {date_to}. "
        f"Focus on what changed — do not recap the empire's full state. "
        f"Weave these events into a cohesive narrative:\n\n"
        f"EVENTS THIS PERIOD:\n{events_text}\n\n"
        f"EMPIRE AT END OF PERIOD:\n"
        f"Planets: {len(snapshot['planets'])} | "
        f"Ruler: {snapshot['ruler'].get('name', 'unknown')} | "
        f"Pops: {snapshot['pop_count']}\n\n"
        f"400–700 words. End with a sentence or two that looks forward."
    )


def build_summary_update_prompt(chapter_prose: str, current_summary: dict) -> str:
    current_text = current_summary.get("text", "")
    return (
        "Update the running story summary to incorporate the new chapter below.\n"
        "Total summary must stay under 250 words. Return only the updated "
        "summary text, nothing else.\n\n"
        f"NEW CHAPTER:\n{chapter_prose}\n\n"
        f"CURRENT SUMMARY:\n{current_text}"
    )


# =============================================================================
# [8] CLAUDE API
# =============================================================================

def generate_chapter(prompt: str, api_key: str, model: str):
    print(f"[chronicle] API request — model: {model}, key: ...{api_key[-8:]}", file=sys.stderr)
    print(f"[chronicle] system prompt ({len(SYSTEM_PROMPT)} chars): {SYSTEM_PROMPT[:120]}…", file=sys.stderr)
    print(f"[chronicle] user prompt ({len(prompt)} chars): {prompt[:300]}…", file=sys.stderr)
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=model,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            yield text_chunk


def update_summary(chapter_prose: str, current_summary: dict, api_key: str, model: str) -> str:
    prompt = build_summary_update_prompt(chapter_prose, current_summary)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# =============================================================================
# [9] HTTP REQUEST HANDLER
# =============================================================================

class ChronicleHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default request logging

    def _send_json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": message})

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_ui()
        elif self.path == "/api/chapters":
            self.handle_list_chapters()
        elif self.path.startswith("/api/chapters/"):
            try:
                n = int(self.path.split("/")[-1])
                self.handle_get_chapter(n)
            except ValueError:
                self._send_error(400, "Invalid chapter number.")
        elif self.path == "/api/export":
            self.handle_export()
        else:
            self._send_error(404, "Not found.")

    def do_POST(self):
        if self.path == "/api/upload":
            self.handle_upload()
        elif self.path == "/api/config":
            self.handle_config()
        elif self.path == "/api/meta":
            self.handle_update_meta()
        elif self.path.endswith("/title"):
            try:
                n = int(self.path.split("/")[-2])
                self.handle_update_title(n)
            except (ValueError, IndexError):
                self._send_error(400, "Invalid chapter number.")
        elif self.path.endswith("/regenerate"):
            try:
                n = int(self.path.split("/")[-2])
                self.handle_regenerate(n)
            except (ValueError, IndexError):
                self._send_error(400, "Invalid chapter number.")
        else:
            self._send_error(404, "Not found.")

    def do_DELETE(self):
        if self.path == "/api/reset":
            self.handle_reset()
        else:
            self._send_error(404, "Not found.")

    def _serve_ui(self):
        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_list_chapters(self):
        meta = load_meta()
        self._send_json(200, {
            "chapters": list_chapters(),
            "campaign_name": meta.get("campaign_name") or meta.get("empire_name") or "",
        })

    def handle_get_chapter(self, n: int):
        ch = load_chapter(n)
        if not ch:
            self._send_error(404, f"Chapter {n} not found.")
            return
        self._send_json(200, ch)

    def handle_upload(self):
        api_key = get_api_key()
        if not api_key:
            self._send_error(401, "No API key configured.")
            return

        config = load_config()
        model = config.get("model", DEFAULT_MODEL)

        content_type = self.headers.get("Content-Type", "")
        body = self._read_body()

        # Extract raw file bytes from multipart or raw body
        file_bytes = self._extract_file(body, content_type)
        if file_bytes is None:
            self._send_error(400, "Could not read upload.")
            return

        if not self._is_zip(file_bytes):
            self._send_error(400, "This doesn't look like a Stellaris save file.")
            return

        try:
            snapshot = parse_save(file_bytes)
        except Exception as exc:
            print(f"[chronicle] Parse error: {exc}", file=sys.stderr)
            self._send_error(500, "Couldn't parse this save — is it from a heavily modded game?")
            return

        baseline = load_baseline()
        meta = load_meta()

        # Empire mismatch check
        if meta and meta.get("empire_name") and meta["empire_name"] != snapshot["empire_name"]:
            self._send_error(409, "Empire mismatch — start a new campaign or use Reset.")
            return

        chapter_num = (meta.get("chapter_count", 0) or 0) + 1
        delta = diff_snapshots(baseline, snapshot)
        summary = load_summary()

        if chapter_num == 1:
            prompt = build_origin_prompt(snapshot)
        else:
            prompt = build_chapter_prompt(chapter_num, delta, snapshot, summary)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        full_text = ""
        try:
            for chunk in generate_chapter(prompt, api_key, model):
                full_text += chunk
                event = f"data: {json.dumps({'chunk': chunk})}\n\n"
                self.wfile.write(event.encode("utf-8"))
                self.wfile.flush()
        except Exception as exc:
            print(f"[chronicle] Generation error: {exc}", file=sys.stderr)
            self.wfile.write(b'data: {"error": "Generation failed."}\n\n')
            self.wfile.flush()
            return

        now = datetime.now(timezone.utc).isoformat()
        chapter_data = {
            "id": chapter_num,
            "title": f"Chapter {chapter_num}",
            "date_from": baseline.get("date") if baseline else snapshot["date"],
            "date_to": snapshot["date"],
            "prose": full_text,
            "word_count": len(full_text.split()),
            "delta_events": [d["type"] for d in delta],
            "generated_at": now,
        }
        save_chapter(chapter_num, chapter_data)

        new_summary_text = update_summary(full_text, summary, api_key, model)
        save_summary({
            "text": new_summary_text,
            "updated_at": now,
            "chapters_covered": chapter_num,
        })
        save_baseline(snapshot)

        updated_meta = {
            "empire_name": snapshot["empire_name"],
            "species_name": snapshot["species_name"],
            "start_date": meta.get("start_date", snapshot["date"]),
            "chapter_count": chapter_num,
            "created_at": meta.get("created_at", now),
            "last_updated": now,
        }
        save_meta(updated_meta)

        self.wfile.write(b'data: {"done": true}\n\n')
        self.wfile.flush()

    def handle_update_meta(self):
        body = json.loads(self._read_body())
        meta = load_meta()
        if "campaign_name" in body:
            meta["campaign_name"] = body["campaign_name"].strip()
        save_meta(meta)
        self._send_json(200, {"ok": True})

    def handle_update_title(self, n: int):
        ch = load_chapter(n)
        if not ch:
            self._send_error(404, f"Chapter {n} not found.")
            return
        body = json.loads(self._read_body())
        ch["title"] = body.get("title", ch["title"])
        save_chapter(n, ch)
        self._send_json(200, {"ok": True})

    def handle_regenerate(self, n: int):
        # Placeholder — full implementation in Phase 2
        self._send_error(501, "Regenerate not yet implemented.")

    def handle_export(self):
        chapters = list_chapters()
        meta = load_meta()
        lines = [f"# {meta.get('empire_name', 'Chronicle')} — AAR\n"]
        for stub in chapters:
            ch = load_chapter(stub["id"])
            default_title = f"Chapter {stub['id']}"
            lines.append(f"\n## {ch.get('title', default_title)}")
            lines.append(f"*{ch.get('date_from')} – {ch.get('date_to')}*\n")
            lines.append(ch.get("prose", ""))
        body = "\n".join(lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="chronicle.md"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_config(self):
        body = json.loads(self._read_body())
        config = load_config()
        if "api_key" in body:
            config["api_key"] = body["api_key"]
        if "model" in body:
            config["model"] = body["model"]
        if "chapter_word_target" in body:
            config["chapter_word_target"] = int(body["chapter_word_target"])
        save_config(config)
        self._send_json(200, {"ok": True})

    def handle_reset(self):
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        self._send_json(200, {"ok": True})

    @staticmethod
    def _is_zip(data: bytes) -> bool:
        return data[:2] == b"PK"

    @staticmethod
    def _extract_file(body: bytes, content_type: str) -> bytes | None:
        if "multipart/form-data" in content_type:
            boundary = content_type.split("boundary=")[-1].encode()
            parts = body.split(b"--" + boundary)
            for part in parts:
                if b"filename=" in part:
                    idx = part.find(b"\r\n\r\n")
                    if idx != -1:
                        return part[idx + 4:].rstrip(b"\r\n--")
            return None
        return body  # assume raw bytes


# =============================================================================
# [10] EMBEDDED UI
# =============================================================================

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chronicle</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #0b0c12;
    --panel:   #12141e;
    --sidebar: #0e0f18;
    --border:  #1e2030;
    --gold:    #c9a84c;
    --text:    #d8d0c4;
    --muted:   #6b6570;
    --danger:  #9e3030;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Lora', Georgia, serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.5rem;
    height: 52px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    flex-shrink: 0;
  }

  .logo {
    font-family: 'Cinzel', serif;
    font-size: 1.1rem;
    letter-spacing: 0.15em;
    color: var(--gold);
  }

  .header-actions { display: flex; gap: 0.75rem; }

  button {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    font-family: inherit;
    font-size: 0.8rem;
    padding: 0.35rem 0.75rem;
    cursor: pointer;
    border-radius: 3px;
    transition: border-color 0.15s, color 0.15s;
  }
  button:hover { border-color: var(--gold); color: var(--gold); }
  button.primary { border-color: var(--gold); color: var(--gold); }

  .main {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* Sidebar */
  .sidebar {
    width: 220px;
    min-width: 220px;
    background: var(--sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .campaign-name {
    font-family: 'Cinzel', serif;
    font-size: 0.85rem;
    padding: 1rem 1rem 0.5rem;
    color: var(--gold);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
    user-select: none;
  }
  .campaign-name:hover::after {
    content: ' ✎';
    font-size: 0.7rem;
    opacity: 0.6;
  }

  .chapter-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 0;
  }

  .chapter-item {
    padding: 0.6rem 1rem;
    cursor: pointer;
    font-size: 0.8rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-left: 3px solid transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .chapter-item:hover { background: var(--panel); }
  .chapter-item.active { border-left-color: var(--gold); background: var(--panel); color: var(--gold); }

  .chapter-item .ch-date { color: var(--muted); font-size: 0.72rem; }

  .sidebar-footer {
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .upload-zone {
    border: 1px dashed var(--border);
    border-radius: 4px;
    padding: 0.6rem;
    text-align: center;
    font-size: 0.75rem;
    color: var(--muted);
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .upload-zone:hover, .upload-zone.drag-over {
    border-color: var(--gold);
    color: var(--gold);
  }
  .upload-zone.uploading {
    pointer-events: none;
    border-color: var(--gold);
    color: var(--gold);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    width: 0.85rem;
    height: 0.85rem;
    border: 2px solid var(--border);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }

  .stats { font-size: 0.72rem; color: var(--muted); text-align: center; }

  /* Reading panel */
  .reading-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--panel);
  }

  .chapter-header {
    padding: 1.25rem 2rem 0.75rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-shrink: 0;
  }

  .chapter-title {
    font-family: 'Cinzel', serif;
    font-size: 1.3rem;
    color: var(--gold);
  }

  .chapter-meta {
    font-size: 0.78rem;
    color: var(--muted);
    margin-top: 0.3rem;
  }

  .chapter-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }

  .prose-container {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
  }

  .prose {
    max-width: 65ch;
    margin: 0 auto;
    line-height: 1.85;
    font-size: 1rem;
    white-space: pre-wrap;
  }

  /* Setup / empty states */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    height: 100%;
    color: var(--muted);
    font-size: 0.9rem;
    text-align: center;
    padding: 2rem;
  }

  .empty-state .logo-large {
    font-family: 'Cinzel', serif;
    font-size: 2rem;
    color: var(--gold);
    opacity: 0.5;
  }

  /* Settings modal */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.open { display: flex; }

  .modal {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1.5rem;
    width: 380px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .modal h2 { font-family: 'Cinzel', serif; font-size: 1rem; color: var(--gold); }

  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field label { font-size: 0.78rem; color: var(--muted); }
  .field input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: monospace;
    font-size: 0.82rem;
    padding: 0.4rem 0.6rem;
    border-radius: 3px;
    width: 100%;
  }
  .field input:focus { outline: none; border-color: var(--gold); }

  .modal-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }

  /* Streaming cursor */
  .cursor { display: inline-block; width: 2px; height: 1em; background: var(--gold); animation: blink 1s step-start infinite; vertical-align: text-bottom; }
  @keyframes blink { 50% { opacity: 0; } }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>

<header>
  <div class="logo">✦ CHRONICLE</div>
  <div class="header-actions">
    <button id="btn-export">Export .md</button>
    <button id="btn-settings">⚙ Settings</button>
  </div>
</header>

<div class="main">
  <aside class="sidebar">
    <div class="campaign-name" id="campaign-name">No campaign</div>
    <div class="chapter-list" id="chapter-list"></div>
    <div class="sidebar-footer">
      <div class="upload-zone" id="upload-zone">
        <span id="upload-label">↑ Drop .sav or click<br>to upload</span>
        <input type="file" id="file-input" accept=".sav" style="display:none">
      </div>
      <div class="stats" id="stats"></div>
    </div>
  </aside>

  <section class="reading-panel">
    <div class="chapter-header" id="chapter-header" style="display:none">
      <div>
        <div class="chapter-title" id="chapter-title"></div>
        <div class="chapter-meta" id="chapter-meta"></div>
      </div>
      <div class="chapter-actions">
        <button id="btn-edit-title">✎ Edit Title</button>
        <button id="btn-regenerate">↺ Regenerate</button>
      </div>
    </div>
    <div class="prose-container">
      <div class="prose" id="prose">
        <div class="empty-state">
          <div class="logo-large">✦</div>
          <p>Drop a Stellaris save to begin your chronicle.</p>
        </div>
      </div>
    </div>
  </section>
</div>

<!-- Settings modal -->
<div class="modal-overlay" id="settings-modal">
  <div class="modal">
    <h2>Settings</h2>
    <div class="field">
      <label>Anthropic API Key</label>
      <input type="password" id="input-api-key" placeholder="sk-ant-...">
    </div>
    <div class="field">
      <label>Chapter word target</label>
      <input type="number" id="input-word-target" value="500" min="200" max="1500">
    </div>
    <div class="modal-actions">
      <button id="btn-settings-cancel">Cancel</button>
      <button class="primary" id="btn-settings-save">Save</button>
    </div>
  </div>
</div>

<script>
(function () {
  'use strict';

  let currentChapterId = null;
  let chapters = [];

  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    await loadChapters();
    if (chapters.length > 0) {
      selectChapter(chapters[chapters.length - 1].id);
    }
  }

  // ── Chapters ──────────────────────────────────────────────────────────────

  let campaignName = '';

  async function loadChapters() {
    const res = await fetch('/api/chapters');
    const data = await res.json();
    chapters = data.chapters || [];
    campaignName = data.campaign_name || '';
    renderSidebar();
  }

  function renderSidebar() {
    const list = document.getElementById('chapter-list');
    const name = document.getElementById('campaign-name');
    const stats = document.getElementById('stats');

    list.innerHTML = '';
    name.textContent = campaignName || 'No campaign';
    if (chapters.length === 0) {
      stats.textContent = '';
      return;
    }

    const totalWords = chapters.reduce((s, c) => s + (c.word_count || 0), 0);
    stats.textContent = `${chapters.length} ch · ${totalWords.toLocaleString()}w`;

    chapters.forEach(ch => {
      const el = document.createElement('div');
      el.className = 'chapter-item' + (ch.id === currentChapterId ? ' active' : '');
      el.dataset.id = ch.id;
      el.innerHTML = `<span>Ch.${ch.id} ${escHtml(ch.title)}</span><span class="ch-date">${ch.date_to || ''}</span>`;
      el.addEventListener('click', () => selectChapter(ch.id));
      list.appendChild(el);
    });
  }

  async function selectChapter(id) {
    currentChapterId = id;
    renderSidebar();

    const res = await fetch(`/api/chapters/${id}`);
    const ch = await res.json();

    document.getElementById('chapter-header').style.display = '';
    document.getElementById('chapter-title').textContent = ch.title || `Chapter ${id}`;
    document.getElementById('chapter-meta').textContent =
      `${ch.date_from || ''} – ${ch.date_to || ''} · ${(ch.word_count || 0).toLocaleString()} words`;
    document.getElementById('prose').textContent = ch.prose || '';
  }

  // ── Upload ─────────────────────────────────────────────────────────────────

  const uploadZone = document.getElementById('upload-zone');
  const fileInput  = document.getElementById('file-input');

  uploadZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) uploadFile(fileInput.files[0]);
  });

  uploadZone.addEventListener('dragover', e => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
  });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  async function uploadFile(file) {
    const form = new FormData();
    form.append('save', file);

    document.getElementById('chapter-header').style.display = 'none';
    const prose = document.getElementById('prose');
    prose.textContent = '';

    const zone = document.getElementById('upload-zone');
    const label = document.getElementById('upload-label');
    const spinnerEl = document.createElement('div');
    spinnerEl.className = 'spinner';
    zone.classList.add('uploading');
    label.textContent = 'Parsing…';
    zone.insertBefore(spinnerEl, label);

    function resetUploadZone() {
      zone.classList.remove('uploading');
      spinnerEl.remove();
      label.innerHTML = '↑ Drop .sav or click<br>to upload';
    }

    const cursor = document.createElement('span');
    cursor.className = 'cursor';
    prose.appendChild(cursor);

    let text = '';

    const res = await fetch('/api/upload', { method: 'POST', body: form });
    if (!res.ok) {
      resetUploadZone();
      const err = await res.json().catch(() => ({ error: 'Unknown error.' }));
      prose.textContent = '⚠ ' + (err.error || 'Upload failed.');
      return;
    }
    resetUploadZone();

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.done) {
          cursor.remove();
          await loadChapters();
          const last = chapters[chapters.length - 1];
          if (last) selectChapter(last.id);
          return;
        }
        if (payload.chunk) {
          text += payload.chunk;
          prose.textContent = text;
          prose.appendChild(cursor);
        }
        if (payload.error) {
          cursor.remove();
          prose.textContent = '⚠ ' + payload.error;
          resetUploadZone();
          return;
        }
      }
    }
  }

  // ── Campaign name ─────────────────────────────────────────────────────────

  document.getElementById('campaign-name').addEventListener('click', async () => {
    const current = campaignName || '';
    const next = prompt('Campaign name:', current);
    if (next === null || next.trim() === current) return;
    await fetch('/api/meta', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campaign_name: next.trim() }),
    });
    campaignName = next.trim();
    document.getElementById('campaign-name').textContent = campaignName || 'No campaign';
  });

  // ── Edit title ────────────────────────────────────────────────────────────

  document.getElementById('btn-edit-title').addEventListener('click', async () => {
    const el = document.getElementById('chapter-title');
    const current = el.textContent;
    const next = prompt('Chapter title:', current);
    if (!next || next === current) return;
    await fetch(`/api/chapters/${currentChapterId}/title`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: next }),
    });
    el.textContent = next;
    await loadChapters();
  });

  // ── Export ────────────────────────────────────────────────────────────────

  document.getElementById('btn-export').addEventListener('click', () => {
    window.location = '/api/export';
  });

  // ── Settings modal ────────────────────────────────────────────────────────

  document.getElementById('btn-settings').addEventListener('click', () => {
    document.getElementById('settings-modal').classList.add('open');
  });
  document.getElementById('btn-settings-cancel').addEventListener('click', () => {
    document.getElementById('settings-modal').classList.remove('open');
  });
  document.getElementById('btn-settings-save').addEventListener('click', async () => {
    const key = document.getElementById('input-api-key').value.trim();
    const wt  = parseInt(document.getElementById('input-word-target').value, 10);
    const body = {};
    if (key) body.api_key = key;
    if (!isNaN(wt)) body.chapter_word_target = wt;
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    document.getElementById('settings-modal').classList.remove('open');
  });

  // ── Regenerate (stub) ─────────────────────────────────────────────────────

  document.getElementById('btn-regenerate').addEventListener('click', () => {
    alert('Regenerate will be available in Phase 2.');
  });

  // ── Util ──────────────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  init();
})();
</script>
</body>
</html>"""


# =============================================================================
# [11] ENTRYPOINT
# =============================================================================

class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    check_and_install_deps()
    ensure_parser_binary()

    DATA_DIR.mkdir(exist_ok=True)
    CHAPTERS_DIR.mkdir(exist_ok=True)

    if not get_api_key():
        print("Chronicle: No API key found.")
        print("  Set ANTHROPIC_API_KEY env var, or enter it in the Settings screen.")

    print(f"Chronicle v{__version__} (parser v{PARSER_VERSION}) — http://localhost:{PORT}")
    print("Press Ctrl+C to stop.\n")

    server = ThreadingServer(("127.0.0.1", PORT), ChronicleHandler)

    threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChronicle stopped.")


if __name__ == "__main__":
    main()
