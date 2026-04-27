# 2026-04-27 phase 1 shipped

## Context
Started with no code. Ended with 26 cities tracked, 429 sub-markets
parsed, observe mode running on my Mac.

## Decisions made today
- Used Claude Code (terminal CLI), not Goose
- Made repo public to unblock github access (revisit later)
- Tracking 26 cities including international guesses
- Running on Mac with caffeinate, not on a VM
- Phase 1 is observe-only by design, no execution code

## Things to watch
- Does scheduler stay up overnight?
- Do international station guesses match Polymarket resolutions?
- What does the first reliability diagram look like after a week?

## Open questions
- Where does the actual edge live (cities, buckets, time-to-resolution)?
- Is GFS or ECMWF more accurate for which cities?
