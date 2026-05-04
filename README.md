# Chronicle

> Turn your Stellaris campaigns into living, chapter-by-chapter chronicles — automatically.

Chronicle is a single-file Python app. Drop in a `.sav` file, get a narrative chapter. Drop in another save later, get the next chapter. No setup. No notes. No manual entry.

---

## Quickstart

```bash
python chronicle.py
```

That's it. Chronicle installs its own dependencies, starts a local server, and opens your browser automatically.

## Prerequisites

- Python 3.8 or later
- An [Anthropic API key](https://console.anthropic.com/)

## How it works

1. Run `chronicle.py` — browser opens to `localhost:8765`
2. Enter your API key in Settings (or set `ANTHROPIC_API_KEY` env var)
3. Drag your Stellaris `.sav` file onto the upload zone
4. Read Chapter 1 as it streams in
5. Next play session: run `chronicle.py` again, drop in the new save → get Chapter 2

Each chapter covers what *changed* between saves: wars, colonization, leader deaths, new technologies, diplomatic shifts. Chronicle diffs the saves and builds a prompt for Claude, which writes the prose.

## Screenshot

*(coming soon)*

## Known Limitations

- **Ironman saves** are fully supported — Stellaris 4.x ironman saves use the same plaintext format as normal saves
- **Event gaps**: if a war starts and ends between two saves, it won't appear in the diff — save at key moments
- **Mod compatibility**: custom civics, traits, or species from mods may appear as placeholder text
- **Single campaign**: only one campaign at a time; use Reset in Settings to start a new one
- **Large saves**: late-game saves (200MB+) may take 30–60 seconds to parse

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

The Rust parsing layer (`stellaris-parser`) was inspired by [stellaris-companion](https://github.com/gitmaan/stellaris-companion/) by gitmaan — a community Stellaris save tool that demonstrated Rust + jomini as a viable and performant approach for Stellaris 4.x saves.

Save parsing is built on the [jomini](https://github.com/nickbabcock/jomini) crate by nickbabcock, which also underpins [Rakaly](https://rakaly.com/) (the EU4 achievement tracker and save analyzer) and the [Paradox Game Converters](https://github.com/ParadoxGameConverters) project.

## License

GPL v3 — see [LICENSE](LICENSE).
