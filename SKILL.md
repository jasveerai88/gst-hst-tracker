---
name: gst-hst-tracker
description: Track GST/HST for Canadian freelancers and sole proprietors from a JSON/CSV ledger — per-calendar-quarter GST/HST collected, ITCs, and net tax owing (collected − ITCs) with a T2125-style prep section, plus the small-supplier alarm: rolling last-4-calendar-quarters taxable income vs the $30,000 registration threshold with exact headroom. Use when preparing GST/HST figures, checking ITCs, or monitoring the registration threshold. A tracking aid, NOT tax advice and NOT a CRA filing; rates are Nov-2026 defaults, overridable — never present them as live fact.
---

# gst-hst-tracker — agent skill

## Purpose

Canadian freelancers and sole proprietors track GST/HST in
spreadsheets and discover CRA's $30,000 small-supplier threshold
after crossing it. This tool reads a dated transaction ledger and
produces (a) per-quarter GST/HST collected, ITCs and net tax
owing with a T2125-style income/expense prep section, and (b) the
threshold test: rolling last-4-calendar-quarters taxable income
against the $30,000 limit, with headroom or a crossed alarm.
Pure Python standard library; local only; reads one ledger file,
writes nothing.

**The honesty core of this tool:** it is a tracking and
calculation aid, **not tax advice and not a CRA filing**. Every
report carries that disclaimer, and so must anything you write
from its output. It never computes penalties or interest.

## When to use / not use

Use when:
- Preparing a quarter's GST/HST figures from a transaction
  ledger: collected, ITCs, net owing.
- Checking how close a freelancer is to the $30,000
  registration threshold, or whether they crossed it.
- Organizing income and expense categories into a T2125-style
  prep view for filing season.
- An agent needs Canadian GST/HST numbers it can trust in JSON.

Do NOT use when:
- The user needs tax advice, a filing, or a ruling on their
  obligations — this tool cannot give one. Point them at the CRA
  or a qualified accountant.
- The question involves penalties or interest — never computed.
- The books are Quebec QST books: QST is memo-only here (see
  Limits). BC PST / SK PST / MB RST are out of scope entirely.
- The ledger is stale: the threshold window is anchored to the
  latest transaction, so a stale ledger gives a stale window.
  Say so if the dates look old.

## Commands

```bash
# Quarterly report (JSON or CSV input; exit 0 on success)
python3 src/gst_hst_tracker.py report LEDGER.json
python3 src/gst_hst_tracker.py report LEDGER.csv --json

# One calendar quarter or one year only
python3 src/gst_hst_tracker.py report LEDGER.json --period 2026-Q1
python3 src/gst_hst_tracker.py report LEDGER.json --period 2026

# The small-supplier alarm (exit 1 when crossed, 0 otherwise)
python3 src/gst_hst_tracker.py threshold LEDGER.json [--limit 30000]

# Also display INR equivalents (rate per 1 CAD)
python3 src/gst_hst_tracker.py report LEDGER.json --cad-to-inr 67.97

# Override a province rate when it changes
python3 src/gst_hst_tracker.py report LEDGER.json --rate NS=15
```

Input rows (JSON list, `{"transactions": [...]}` object, or CSV
with the same headers): `date` (`YYYY-MM-DD`, required), `kind`
(`income`|`expense`, required), `description` (required),
`amount` (pre-tax CAD, required, ≥ 0), `province` (two-letter
code, required); optional `tax` (GST/HST charged/paid — omit to
compute from the province rate; `0` means zero-rated and is
respected), `qst` (QC rows only; tracked separately, never in
the net), `category` (expenses only; T2125-style grouping).

## The model (state it when you report results)

- Net tax owing per calendar quarter = GST/HST collected on
  income − ITCs (GST/HST paid on expenses). Negative net = ITCs
  exceed collections: a refund position, not cash in hand.
- Threshold: taxable supplies (income rows only) over the last
  4 calendar quarters ending at the latest transaction's
  quarter. CRA's test is **exceeds** $30,000 — exactly $30,000
  is still a small supplier (`status: "at"`, exit 0).
- Rate defaults as of 2026-11: GST 5% (AB BC MB NT NU SK YT),
  HST 13% ON, HST 15% NB/NL/PE, **HST 14% NS** (lowered from
  15% on 2025-04-01), QC = GST 5% federal part only.
- QST (9.975%) is a separate Revenu Québec tax: supplied `qst`
  amounts appear as memo totals only and never enter the net.

## Output JSON schema (`--json`)

`report`: `tool` (`"gst-hst-tracker"`), `version`, `command`
(`"report"`), `file`, `currency` (`"CAD"`), `rates` (per-province
`rate_pct` + label, stamped `as_of: "2026-11"`, plus the QST
note), `cad_to_inr` (rate or null), `period_filter` (string or
null), `periods`, `totals`, `disclaimer`.

Each period: `period` (e.g. `"2026-Q1"`), `quarter` (`[2026, 1]`),
`income_total`, `expense_total`, `gst_hst_collected`, `itcs`,
`net_tax_owing`, `qst_collected`, `qst_paid`, `transactions`,
`t2125` (`gross_business_income`, `expenses_by_category`,
`total_expenses`). `totals` sums the same fields across the
periods shown. With `--cad-to-inr`, money fields gain `*_inr`
siblings.

`threshold`: the common fields plus `latest_transaction`,
`window_end_quarter`, `quarters` (four `{quarter, income}`
entries, oldest first), `rolling_total`, `limit`, `headroom`
(0 when crossed), `over_by` (0 when not crossed), `crossed`
(bool), `status` (`"under"` | `"at"` | `"crossed"`), `rule`,
`disclaimer`.

On error, stdout is a single object: `{"error": "<message>"}`
(validation errors name the row: `"row 2: ..."`) with exit code
2 — including argparse usage errors in `--json` mode. Never
plain text, never a traceback.

## Exit codes

- `report`: `0` — report computed. `2` — error.
- `threshold`: `0` — rolling total is under **or exactly at**
  the limit: still a small supplier on these figures. `1` —
  **THRESHOLD CROSSED**: the rolling total exceeds the limit
  and GST/HST registration is required. This is a finding, not
  a failure: surface it prominently. `2` — error: no numbers
  were produced; do not quote any.
- Errors in either command exit `2` with a clean message (or
  the `{"error": ...}` object in `--json` mode).

## Limits & honesty rules the agent must respect

- **Not tax advice, not a filing.** Never present this tool's
  output as advice or as a filed return. The disclaimer in
  every output is load-bearing: keep it attached to any summary
  you write.
- **The rates are defaults as of 2026-11, not live facts.**
  Cite them as "the tool's Nov-2026 defaults" and note they are
  overridable. Nova Scotia is 14% (it was 15% until
  2025-03-31) — if a user's figures were computed at 15% for NS,
  that is worth flagging, not silently accepting.
- **Exactly at $30,000 is NOT crossed.** CRA's test is
  "exceeds $30,000". If `status` is `"at"`, report "still a
  small supplier, zero headroom" — never "must register".
- **Exit 1 from `threshold` is the tool working.** It means the
  alarm fired. Report the rolling total, the amount over, and
  that registration is required — promptly, not buried.
- **QST never enters the net.** If you summarize Quebec rows,
  keep QST as a separate memo figure. Do not add QST collected
  to `net_tax_owing`, and do not treat QST paid as an ITC.
- **A negative net is a refund position, not income.** Do not
  describe it as money received.
- **Penalties and interest are never computed** — if the user
  crossed in an earlier period, that is a CRA/accountant
  conversation; do not estimate an amount.
- Local only: the tool reads the file you point it at and
  sends nothing anywhere.
