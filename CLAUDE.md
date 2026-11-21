## Agent skills

### Issue tracker

Issues live in GitHub Issues (misnow1/score-ocr-parser), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Project conventions

- Keep `README.md` in sync with the code: any change to the CLI, options, output format, setup or dependencies updates the README in the same change.
- Add CI (GitHub Actions) as tests are developed, and extend it as new test kinds arrive (for example macOS-only OCR tests need a macOS runner). Corpus tests stay opt-in and are never run in CI, because the scores can't be committed.
