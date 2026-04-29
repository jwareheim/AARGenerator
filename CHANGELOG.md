# Changelog

All notable changes to Chronicle are documented here.

## [Unreleased] — v0.1.0

### Added
- `check_and_install_deps()` bootstrap — auto-installs `anthropic` and `clausewizard`
- Save parser: unzip `.sav`, parse with ClauseWizard, extract relevant fields
- Chapter 1 generation (origin story) via Anthropic streaming API
- Streaming SSE response — prose renders word-by-word in the browser
- `chronicle_data/` storage layout: `config.json`, `meta.json`, `baseline.json`, `summary.json`, `chapters/`
- Embedded dark-space UI with upload zone and reading panel
- Settings modal for API key configuration
- Export to `.md` download
- README, CONTRIBUTING, LICENSE, .gitignore
