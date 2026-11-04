# gst-hst-tracker

**The $30,000 surprise is the most expensive surprise in Canadian freelancing.**

Cross CRA's small-supplier threshold and you were supposed to be
registered for GST/HST — charging tax you never charged, on income
you already spent. Most freelancers and sole proprietors discover
the threshold *after* crossing it, because their "system" is a
spreadsheet they update when they remember. `gst-hst-tracker`
turns that spreadsheet into two answers you can trust:

1. **`report`** — per calendar quarter: GST/HST collected on
   income, ITCs (the tax you paid on expenses), and the **net tax
   owing** (collected − ITCs), plus a T2125-style prep section
   (gross business income, expenses grouped by category) so filing
   season starts from organized numbers instead of a shoebox.
2. **`threshold`** — CRA's small-supplier test done properly:
   your taxable income over the **last 4 calendar quarters**
   against the **$30,000** limit, with your exact headroom — or a
   clear alarm that you crossed it and registration is required.

> **Disclaimer:** this tool is a tracking and calculation aid
> only. It is **not tax advice** and it is **not a CRA filing**.
> Verify your figures and obligations with the CRA or a qualified
> accountant before filing. It never computes penalties or
> interest.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your ledger never leaves your machine
- Script-friendly exit codes: `report` exits `0` on success;
  `threshold` exits `0` while you are a small supplier and `1`
  when the threshold is crossed, so a script can catch the alarm;
  `2` = error

## Province rates (as of 2026-11 — override any rate)

These are the published GST/HST rates as of November 2026. They
are defaults, **not live facts** — provinces change them (Nova
Scotia just did). Override any rate per run with
`--rate PROV=PCT`.

| Province / territory | Rate | Tax |
|---|---|---|
| AB, BC, MB, NT, NU, SK, YT | 5% | GST |
| ON | 13% | HST |
| NB, NL, PE | 15% | HST |
| NS | **14%** | HST (was 15% until 2025-03-31) |
| QC | 5% | GST — federal part only, see the Quebec boundary |

**The Quebec boundary, plainly.** The net figure in this tool is
the federal GST/HST figure only. Quebec's QST (9.975%) is a
separate tax administered by Revenu Québec, and QST is **never**
included in the net GST/HST owing. If you add a `qst` amount to a
Quebec row, the tool tracks QST collected / paid as separate memo
totals so you can see them — nothing more. The other provincial
sales taxes (BC PST, SK PST, MB RST) are likewise out of scope:
for those provinces the tool applies the 5% GST only.

## The model (the choices are deliberate — and stated)

- **Net tax owing = GST/HST collected − ITCs**, per calendar
  quarter (Jan–Mar = Q1, and so on). A negative net means ITCs
  exceed tax collected: a refund position on the return, not cash
  in hand.
- **`tax` is optional per row.** Leave it out and the tool
  computes it from the province rate. Supply it when you know the
  actual amount (mixed-rate invoices, partial ITCs). Enter `0`
  for a zero-rated supply — an explicit 0 is respected, never
  "corrected" back to the province rate.
- **The threshold test is CRA's, not an approximation:** total
  taxable supplies over the last 4 calendar quarters ending at
  your latest transaction's quarter. CRA's wording is **exceeds**
  $30,000 — sitting at exactly $30,000 is still a small supplier,
  and the tool says so rather than crying wolf.
- The threshold counts **income only** (taxable supplies).
  Expenses never reduce it. Exempt supplies (residential rent,
  most financial services) are not taxable supplies and should
  not be entered as income.
- The T2125-style section is a **preparation aid**: gross
  business income and expenses grouped by the row's `category`
  (common categories are matched to T2125-style names like
  *Office expenses*, *Rent*, *Travel*; anything else passes
  through as typed, uncategorized expenses land in *Other
  expenses*). Final line placement on the real form is the
  filer's — or their accountant's — job.

## Input format

One row per transaction, as JSON (a list, or an object with a
`"transactions"` key) or as CSV with the same headers:

| Field | Required | Meaning |
|---|---|---|
| `date` | yes | `YYYY-MM-DD`, a real calendar date |
| `kind` | yes | `income` or `expense` |
| `description` | yes | what it was |
| `amount` | yes | the **pre-tax** amount in CAD, ≥ 0 |
| `province` | yes | `AB BC MB NB NL NS NT NU ON PE QC SK YT` |
| `tax` | no | GST/HST charged (income) or paid (expense) in CAD; omit to compute from the province rate; `0` = zero-rated |
| `qst` | no | QC rows only: the QST amount in CAD — tracked separately, never in the net |
| `category` | no | expenses only: T2125-style grouping (default *Other expenses*) |

Bad rows are rejected with the row number named — no silent
zeros, no tracebacks.

## Usage

```bash
# 1. The quarterly report (JSON or CSV input)
python3 src/gst_hst_tracker.py report examples/sample.json
python3 src/gst_hst_tracker.py report examples/sample.csv

# 2. One quarter only (or one year: --period 2026)
python3 src/gst_hst_tracker.py report examples/sample.json --period 2026-Q1

# 3. The small-supplier alarm (exit 1 if crossed)
python3 src/gst_hst_tracker.py threshold examples/sample.json

# 4. The same numbers as one JSON object (for scripts and agents)
python3 src/gst_hst_tracker.py report examples/sample.json --json
python3 src/gst_hst_tracker.py threshold examples/sample.json --json

# 5. Also print INR equivalents (rate per 1 CAD)
python3 src/gst_hst_tracker.py report examples/sample.json --cad-to-inr 67.97

# 6. Override a province rate when it changes
python3 src/gst_hst_tracker.py report examples/sample.json --rate NS=15
```

## Use with AI agents

Every command takes `--json`: one JSON object with the same
numbers and exit codes as the text report (errors come back as
`{"error": ...}`):

```bash
python3 src/gst_hst_tracker.py report examples/sample.json --json
python3 src/gst_hst_tracker.py threshold examples/sample.json --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full JSON
schemas, exit codes, and the honesty rules (this is a tracking
aid, never tax advice; the rates are Nov-2026 defaults, never
quote them as live fact; exactly-at-threshold is not crossed).

## Real runs (verbatim)

The bundled sample is a small Ontario/Nova Scotia/BC ledger: a
$4,000 website build, a $1,500 logo package, $1,000 of zero-rated
export work, a laptop and hosting as expenses, a $2,500 NS
consulting invoice, and conference travel.

```text
$ python3 src/gst_hst_tracker.py report examples/sample.json
gst-hst-tracker v0.1.0 — report for sample.json (7 transaction(s))
Tax rates: defaults as of 2026-11 — override any rate with --rate PROV=PCT (e.g. --rate NS=14).
Amounts in CAD.

2026-Q1
  Income (pre-tax): 6,500.00 · GST/HST collected: 595.00
  Expenses (pre-tax): 300.00 · ITCs (tax paid): 39.00
  NET TAX OWING: 556.00 (collected − ITCs)
  T2125-style prep: gross business income 6,500.00 · expenses — Office expenses 300.00 · total expenses 300.00

2026-Q2
  Income (pre-tax): 2,500.00 · GST/HST collected: 350.00
  Expenses (pre-tax): 800.00 · ITCs (tax paid): 40.00
  NET TAX OWING: 310.00 (collected − ITCs)
  T2125-style prep: gross business income 2,500.00 · expenses — Travel 800.00 · total expenses 800.00

TOTALS (periods shown)
  Income (pre-tax): 9,000.00 · GST/HST collected: 945.00
  Expenses (pre-tax): 1,100.00 · ITCs (tax paid): 79.00
  NET TAX OWING: 866.00 (collected − ITCs)
  T2125-style prep: gross business income 9,000.00 · expenses — Office expenses 300.00 · Travel 800.00 · total expenses 1,100.00

Net = GST/HST collected − ITCs. A negative net means ITCs exceed tax collected — a refund position on the return, not cash in hand.
Quebec: QST is a separate Revenu Québec tax and is never part of the net above; supplied QST amounts appear as memo lines only.
Disclaimer: This tool is a tracking and calculation aid only. It is not tax advice and it is not a CRA filing. Verify your figures and obligations with the CRA or a qualified accountant before filing.
(exit code: 0)
```

Every number in that report is checkable by hand: Q1 collected is
520 (13% of the Ontario build) + 75 (5% of the BC logo) + 0 (the
zero-rated export) = **595**; ITCs are 26 (given on the laptop) +
13 (13% computed on the hosting) = **39**; net **556**. Q2's
consulting is Nova Scotia at the *current* 14% — 350, not the 375
the old 15% rate would have produced.

One quarter at a time, verbatim:

```text
$ python3 src/gst_hst_tracker.py report examples/sample.json --period 2026-Q1
gst-hst-tracker v0.1.0 — report for sample.json (5 transaction(s)) — period 2026-Q1
Tax rates: defaults as of 2026-11 — override any rate with --rate PROV=PCT (e.g. --rate NS=14).
Amounts in CAD.

2026-Q1
  Income (pre-tax): 6,500.00 · GST/HST collected: 595.00
  Expenses (pre-tax): 300.00 · ITCs (tax paid): 39.00
  NET TAX OWING: 556.00 (collected − ITCs)
  T2125-style prep: gross business income 6,500.00 · expenses — Office expenses 300.00 · total expenses 300.00

Net = GST/HST collected − ITCs. A negative net means ITCs exceed tax collected — a refund position on the return, not cash in hand.
Quebec: QST is a separate Revenu Québec tax and is never part of the net above; supplied QST amounts appear as memo lines only.
Disclaimer: This tool is a tracking and calculation aid only. It is not tax advice and it is not a CRA filing. Verify your figures and obligations with the CRA or a qualified accountant before filing.
(exit code: 0)
```

And the alarm, on the same sample:

```text
$ python3 src/gst_hst_tracker.py threshold examples/sample.json
gst-hst-tracker v0.1.0 — small-supplier threshold for sample.json
Rule (as of 2026-11): registration is required once taxable supplies EXCEED 30,000.00 over the last 4 calendar quarters. Exactly at the limit does not cross it.
Window: the last 4 calendar quarters ending 2026-Q2 (the quarter of the latest transaction, 2026-05-01):
  2025-Q3: 0.00
  2025-Q4: 0.00
  2026-Q1: 6,500.00
  2026-Q2: 2,500.00
Rolling 4-quarter taxable income: 9,000.00 of 30,000.00
UNDER THRESHOLD — 21,000.00 of headroom remains. You are still a small supplier on these figures.
The window counts income (taxable supplies) only; exempt supplies are not taxable supplies and should not be entered as income.
Disclaimer: This tool is a tracking and calculation aid only. It is not tax advice and it is not a CRA filing. Verify your figures and obligations with the CRA or a qualified accountant before filing.
(exit code: 0)
```

What the alarm sounds like when it fires — a $20,000 contract in
Q1 and $10,001 of follow-on work in Q2:

```text
$ python3 src/gst_hst_tracker.py threshold crossed.json
gst-hst-tracker v0.1.0 — small-supplier threshold for crossed.json
Rule (as of 2026-11): registration is required once taxable supplies EXCEED 30,000.00 over the last 4 calendar quarters. Exactly at the limit does not cross it.
Window: the last 4 calendar quarters ending 2026-Q2 (the quarter of the latest transaction, 2026-05-10):
  2025-Q3: 0.00
  2025-Q4: 0.00
  2026-Q1: 20,000.00
  2026-Q2: 10,001.00
Rolling 4-quarter taxable income: 30,001.00 of 30,000.00
⚠ THRESHOLD CROSSED — the rolling total exceeds 30,000.00 by 1.00. You are no longer a small supplier on these figures: GST/HST registration is required.
The window counts income (taxable supplies) only; exempt supplies are not taxable supplies and should not be entered as income.
Disclaimer: This tool is a tracking and calculation aid only. It is not tax advice and it is not a CRA filing. Verify your figures and obligations with the CRA or a qualified accountant before filing.
(exit code: 1 — threshold crossed)
```

One dollar over is over. That is exactly the moment to learn it
from a tool instead of from a CRA notice.

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 59 tests — OK
```

The suite covers both directions: the sample's net-tax figures
worked by hand from the published rates (not copied from the
tool's own output), the rolling 4-quarter window across year
boundaries, a crossing case, the exactly-$30,000 boundary (still
a small supplier), the QST boundary (tracked, never in the net,
rejected on non-Quebec rows), quarter bucketing at year edges,
malformed rows failing with their row numbers in text and JSON
modes, `--rate` overrides changing results by exactly the
hand-computed delta, and CSV/JSON agreement on the same data.

## Internal use

This tool does a real job for its author: it is the GST/HST
bookkeeping prep for the author's own Canadian corporation and
freelance income — the quarterly collected/ITC/net figures and
the rolling threshold check are run from the same ledger the
accountant receives, so the $30,000 question is answered every
quarter instead of discovered at tax time.

## Known limits

- **Not tax advice, not a filing.** The tool adds up what you
  entered. It does not know your filing frequency, your
  registration effective date, or your industry's special rules
  (place-of-supply for services can differ from the row's
  province — when it does, supply the actual `tax` amount).
- **The threshold window is anchored to your latest
  transaction.** If your ledger is months stale, the window is
  too. Keep the ledger current; the tool can only test the data
  it is given.
- **Quebec is memo-only** (see the boundary above), and the other
  provincial sales taxes (PST/RST) are out of scope entirely.
- **One currency: CAD.** The INR figures from `--cad-to-inr` are
  display equivalents only; they do not convert the books.
- Penalties and interest are **never** computed — if you crossed
  the threshold in an earlier window, that conversation belongs
  with the CRA or an accountant, not with this tool.

## Privacy

What it touches: only the ledger file you point it at. What it
stores: nothing. What it sends: nothing — there is no network
code in this tool.

## Support

If this catches the threshold before the CRA does, consider
sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
