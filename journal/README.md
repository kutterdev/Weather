# Journal

Human-written decision notes. Not auto-generated. Not appended to by the
agent. The agent should never create a file in this directory unless the
human explicitly asks it to.

## Purpose

The database is the memory. `weather-bot status` is the readout. This
folder is for the things the database cannot capture: why a threshold
was changed, what surprised us, what we want to look at next, what we
explicitly decided not to do.

## Convention

- One file per entry, named `YYYY-MM-DD-short-slug.md`.
- Multiple entries per day are fine: `YYYY-MM-DD-short-slug-2.md`.
- Use `TEMPLATE.md` as a starting point.
- Keep entries short. Two paragraphs is plenty. The point is the date
  and the decision, not the prose.

## When to write one

- When changing a config threshold (ev_threshold, kelly_fraction, etc.).
- When deciding NOT to ship something we considered.
- When a calibration result surprises us.
- When a real-world API quirk forces a code change.
- Before making any irreversible move (especially before turning on
  execution, when that day eventually comes).

## When NOT to write one

- After every routine code change. Use git history for that.
- For things the database already records. If `status` shows it,
  do not also write it down here.
