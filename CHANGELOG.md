# Changelog

## v0.1.0 — 2026-11-04

First release.

- **`report FILE.json|FILE.csv`** — per-calendar-quarter GST/HST
  for Canadian freelancers and sole proprietors: income and
  expense totals (pre-tax), **GST/HST collected** on income,
  **ITCs** (tax paid on expenses), and **net tax owing**
  (collected − ITCs), for every quarter in the file or one
  chosen `--period YYYY` / `--period YYYY-Qn`. Each period
  carries a **T2125-style prep section**: gross business income
  and expenses grouped by category (common categories matched
  to T2125-style names; unknown categories pass through).
- **`threshold FILE.json|FILE.csv`** — the small-supplier alarm:
  taxable income over the **last 4 calendar quarters** ending at
  the latest transaction's quarter, against the **$30,000**
  registration limit, with exact headroom. Follows CRA's
  wording: registration is required when the total **exceeds**
  $30,000 — exactly at $30,000 is still a small supplier and is
  reported as such. Exit code 1 when crossed, so a script can
  catch the alarm.
- **Province rate defaults stamped "as of 2026-11"** in the
  README, the code and every report header — GST 5% (AB, BC,
  MB, NT, NU, SK, YT), HST 13% ON, HST 15% NB/NL/PE, **HST 14%
  NS** (Nova Scotia lowered its HST from 15% on 2025-04-01),
  QC at the 5% federal GST — and **every rate is overridable**
  with `--rate PROV=PCT`, so the tool survives provinces
  changing their rates.
- **Per-row `tax` is optional:** omit it and the tax is
  computed from the province rate; supply it when the actual
  amount is known. An explicit `0` marks a zero-rated supply
  and is respected, never "corrected".
- **The Quebec boundary is explicit:** QST (9.975%) is a
  separate Revenu Québec tax and is never part of the net
  GST/HST figure. A `qst` amount on a QC row is tracked as a
  separate memo total; `qst` on any other province's row is a
  validation error. BC/SK/MB provincial sales taxes are out of
  scope (those provinces use the 5% GST rate).
- **The honesty rules are built in:** the disclaimer — *a
  tracking and calculation aid only, not tax advice, not a CRA
  filing* — appears in the README, SKILL.md and every report
  footer (text and JSON). Penalties and interest are never
  computed.
- **`--cad-to-inr RATE`** — also prints INR equivalents next to
  every amount (the CAD + INR display pattern of
  payout-tracker).
- **Validation with row numbers:** bad or impossible dates,
  unknown kinds or provinces, negative or non-finite numbers,
  missing fields, misplaced `qst` and non-numeric CSV cells are
  clean errors that name the exact row — never a traceback,
  never a silent zero.
- **`--json` on both commands** — one JSON object with the same
  numbers and exit codes as the text report; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`SKILL.md`** at the repo root for AI coding agents:
  commands, the JSON schemas, exit codes, and the honesty
  rules (not tax advice; rates are Nov-2026 defaults;
  exactly-at-threshold is not crossed; QST never enters the
  net).
- Bundled sample (`examples/sample.json` + the identical
  `examples/sample.csv`): a 7-transaction ledger whose Q1 net
  of **556.00** and rolling threshold total of **9,000.00**
  (headroom 21,000.00) are worked by hand in the tests.
- 59 stdlib-unittest tests: net-tax math hand-checked against
  the published rates, the rolling 4-quarter window across
  year boundaries, a crossing case, the exactly-$30,000
  boundary, the QST boundary, quarter bucketing at year edges,
  malformed-row errors with row numbers, `--rate` overrides,
  and CSV/JSON agreement on the same data.
- Pure Python standard library; local only; MIT licence.
