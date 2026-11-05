# Notes for AI agents working with falg

**This is a public repository** (github.com/lemmon/falg, MIT).

- Never commit secrets, API keys, personal paths (`/Users/...`), email addresses or private
  project details.
- Write README, docs and commit messages for outside readers.
- falg builds on and is inspired by other people's work (see README, "Similar projects").
  Mention other projects respectfully: describe what each does well and how it differs.
  Don't disparage them, and don't use stars, activity or staleness as arguments.
  Credit ideas taken from them.

- **Never pick fal models from memory.** Models, versions and endpoints change monthly.
  Read `MODELS.md` and check its `Generated:` date. If it is older than 30 days, run
  `falg catalog` first; `falg models` also prints the snapshot's age.
- The "Registry check" table in `MODELS.md` flags newer releases in each family. Before adding
  a model, run `falg schema <endpoint>`, then edit `src/falg/models.json`.
- Prices in `models.json` are rough guesses (one USD figure per image), good enough to catch a
  run that costs 10x what you expected. Cost estimates are a secondary feature. Don't model
  per-megapixel, per-resolution or per-quality pricing, and don't treat small price differences
  as bugs. Fix a price only when it is clearly wrong (a missing price, or one off by ~2x or more).
- Start every paid run with `--dry-run`. Non-interactive runs need `-y` or `--max-cost N`.
- Never print or commit the API key. It lives in `~/.config/falg/.env` (`falg auth`).
- Keep `README.md` up to date when commands or the config format change.
