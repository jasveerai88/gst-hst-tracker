# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** gst-hst-tracker's promise is
  "clone and run". Pull requests that add a third-party
  dependency will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of
  user files.
- **Tax rates are data, never gospel.** The defaults are
  stamped "as of 2026-11" everywhere they appear. A PR updating
  a default rate must cite the province's or CRA's own rate
  page and update the stamp, the README table and the tests in
  the same change.
- **The CRA wording is load-bearing.** The small-supplier test
  is EXCEEDS $30,000 over the last 4 calendar quarters, and the
  net is GST/HST collected − ITCs. Any change to those rules,
  to the quarter bucketing, or to the Quebec boundary (QST
  never enters the net) is a behaviour change: it needs the
  README model section, the changelog and the tests updated
  together — and a hand-worked example proving the new math.
- **The disclaimer is not decoration.** "A tracking and
  calculation aid only — not tax advice, not a CRA filing"
  stays in the README, SKILL.md and every report footer.
  Penalties and interest are never computed; PRs adding them
  will not be merged.
- **Both directions tested.** A behaviour change needs a test
  where good input succeeds and bad input fails cleanly — not
  just one side. Tax math needs a hand-checked number, not a
  number copied from the tool's own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/gst-hst-tracker
cd gst-hst-tracker
python3 -m unittest discover -s tests -v
python3 src/gst_hst_tracker.py report examples/sample.json
python3 src/gst_hst_tracker.py threshold examples/sample.json
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
