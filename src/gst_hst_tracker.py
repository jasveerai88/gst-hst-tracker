#!/usr/bin/env python3
"""gst-hst-tracker — GST/HST collected, ITCs, net tax owing, and the
$30,000 small-supplier alarm, for Canadian freelancers and sole
proprietors who track tax in a spreadsheet and find the registration
threshold too late.

Pure Python standard library. Local only: no network, no uploads,
no accounts. Your ledger never leaves your machine.

THIS TOOL IS A TRACKING AND CALCULATION AID ONLY. It is not tax
advice and it is not a CRA filing. Verify your figures and your
obligations with the CRA or a qualified accountant before filing.
It never computes penalties or interest.

Commands:
  report FILE.json|FILE.csv [--period YYYY | YYYY-Qn] [--json]
         [--rate PROV=PCT ...] [--cad-to-inr R]
  threshold FILE.json|FILE.csv [--limit 30000] [--json]
         [--cad-to-inr R]

Input rows (JSON list, {"transactions": [...]} object, or CSV with
the same headers):
  date        YYYY-MM-DD (required, a real calendar date)
  kind        "income" | "expense" (required)
  description non-empty text (required)
  amount      the PRE-TAX amount in CAD (required, >= 0)
  province    two-letter code: AB BC MB NB NL NS NT NU ON PE QC
              SK YT (required)
  tax         GST/HST charged (income) or paid (expense), in CAD.
              OPTIONAL: leave it out and the tool computes it from
              the province rate below. Enter 0 for a zero-rated
              supply — that is respected, never "corrected".
  qst         Quebec only: the QST amount on the row, in CAD.
              OPTIONAL and tracked SEPARATELY — see the Quebec
              boundary below. An error on any other province.
  category    expenses only, optional: groups the expense in the
              T2125-style prep section (default "Other expenses").

The model (every choice is deliberate and documented):
  NET tax owing for a period = GST/HST collected on income
  minus ITCs (GST/HST paid on expenses). A negative net is a
  refund position on the return — it is not cash in hand.
  Periods are CALENDAR quarters (Jan-Mar = Q1, ...). The report
  groups every quarter present, or one chosen --period.
  The threshold test is CRA's small-supplier rule: total taxable
  supplies over the LAST 4 CALENDAR QUARTERS ending at the latest
  transaction's quarter. EXCEEDING $30,000 ends small-supplier
  status; sitting at exactly $30,000 does not.

Province rate defaults — AS OF 2026-11, stamped here and in the
README. They are defaults, not live facts: override any of them
with --rate PROV=PCT when a province changes its rate.
  GST 5%:  AB BC MB NT NU SK YT (GST-only provinces/territories)
  HST 13%: ON
  HST 15%: NB NL PE
  HST 14%: NS (Nova Scotia moved from 15% to 14% on 2025-04-01)
  QC:      GST 5% (federal part only — see the Quebec boundary)

The Quebec boundary, plainly: this tool's net figure is the
federal GST/HST figure only. Quebec's QST (9.975%) is a separate
provincial tax administered by Revenu Québec. QST amounts are
NEVER included in the net GST/HST owing. If you supply a `qst`
amount on a Quebec row, the tool tracks QST collected / paid as
separate memo totals so you can see them — nothing more. The
other provincial sales taxes (BC PST, SK PST, MB RST) are likewise
outside this tool: the rate for those provinces is the 5% GST.

Amounts are in CAD. --cad-to-inr R also prints INR equivalents
(rate R per 1 CAD), following the CAD + INR display pattern of
payout-tracker.

Exit codes: report — 0 = report computed · threshold — 0 = under
(or exactly at) the threshold, still a small supplier · 1 =
THRESHOLD CROSSED, registration required · both — 2 = ERROR
(bad input) — clean message, never a traceback; with --json the
error is {"error": ...}.
"""
import argparse
import csv
import io
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

__version__ = "0.1.0"
TOOL = "gst-hst-tracker"
RATES_AS_OF = "2026-11"
DEFAULT_LIMIT = 30000.0

DISCLAIMER = (
    "This tool is a tracking and calculation aid only. It is not "
    "tax advice and it is not a CRA filing. Verify your figures "
    "and obligations with the CRA or a qualified accountant "
    "before filing.")

# province code -> (GST/HST rate in percent, label)
PROVINCE_DEFAULTS = {
    "AB": (5.0, "GST 5%"),
    "BC": (5.0, "GST 5%"),
    "MB": (5.0, "GST 5%"),
    "NB": (15.0, "HST 15%"),
    "NL": (15.0, "HST 15%"),
    "NS": (14.0, "HST 14%"),
    "NT": (5.0, "GST 5%"),
    "NU": (5.0, "GST 5%"),
    "ON": (13.0, "HST 13%"),
    "PE": (15.0, "HST 15%"),
    "QC": (5.0, "GST 5% (federal part only; QST is separate)"),
    "SK": (5.0, "GST 5%"),
    "YT": (5.0, "GST 5%"),
}
QST_RATE_PCT = 9.975  # documented in the rate table; never in the net

# T2125-style expense categories: lower-case alias -> display name.
# A preparation aid only — unknown categories pass through as typed.
CATEGORY_ALIASES = {
    "advertising": "Advertising",
    "meals": "Meals and entertainment",
    "meals and entertainment": "Meals and entertainment",
    "bad debts": "Bad debts",
    "insurance": "Insurance",
    "interest": "Interest",
    "office": "Office expenses",
    "office expenses": "Office expenses",
    "supplies": "Supplies",
    "professional fees": "Professional fees",
    "legal": "Professional fees",
    "accounting": "Professional fees",
    "rent": "Rent",
    "repairs": "Repairs and maintenance",
    "repairs and maintenance": "Repairs and maintenance",
    "salaries": "Salaries and wages",
    "salaries and wages": "Salaries and wages",
    "subcontracts": "Subcontracts",
    "utilities": "Utilities",
    "vehicle": "Vehicle expenses",
    "vehicle expenses": "Vehicle expenses",
    "travel": "Travel",
    "other": "Other expenses",
    "other expenses": "Other expenses",
}
DEFAULT_CATEGORY = "Other expenses"

KINDS = ("income", "expense")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PERIOD_RE = re.compile(r"^(\d{4})(?:-Q([1-4]))?$")


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# tax rates
# --------------------------------------------------------------------------

@dataclass
class TaxRates:
    rates: dict = field(default_factory=lambda: {
        code: pct for code, (pct, _label)
        in PROVINCE_DEFAULTS.items()})

    def rate_for(self, province):
        return self.rates[province]

    def as_dict(self):
        provinces = {}
        for code, (default_pct, label) in PROVINCE_DEFAULTS.items():
            entry = {"rate_pct": self.rates[code], "label": label}
            if self.rates[code] != default_pct:
                entry["default_pct"] = default_pct
            provinces[code] = entry
        return {"as_of": RATES_AS_OF, "provinces": provinces,
                "qst": {"rate_pct": QST_RATE_PCT,
                        "note": "Quebec only; tracked separately, "
                                "never part of the net GST/HST figure"}}


def _check_pct(value, label):
    if value is None or isinstance(value, bool) \
            or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ToolError(f"{label} must be a finite number "
                        f"(got {value!r})")
    if value < 0 or value >= 100:
        raise ToolError(f"{label} must be >= 0 and < 100 "
                        f"(got {value:g})")
    return float(value)


def rates_from_args(a):
    """Build TaxRates, applying any --rate PROV=PCT overrides."""
    rates = TaxRates()
    for spec in getattr(a, "rate", None) or []:
        if "=" not in spec:
            raise ToolError(f"--rate expects PROV=PCT "
                            f"(got {spec!r})")
        code, _, pct_text = spec.partition("=")
        code = code.strip().upper()
        if code not in PROVINCE_DEFAULTS:
            raise ToolError(
                f"--rate: unknown province {code!r} (expected one "
                f"of {' '.join(PROVINCE_DEFAULTS)})")
        try:
            pct = float(pct_text)
        except ValueError:
            raise ToolError(f"--rate {spec!r}: {pct_text!r} is not "
                            f"a number")
        rates.rates[code] = _check_pct(pct, f"--rate {spec}")
    return rates


# --------------------------------------------------------------------------
# dates, quarters, periods
# --------------------------------------------------------------------------

def quarter_of(d):
    """date -> (year, quarter 1-4), calendar quarters."""
    return (d.year, (d.month - 1) // 3 + 1)


def quarter_label(yq):
    return f"{yq[0]}-Q{yq[1]}"


def add_quarters(yq, n):
    """Step (year, quarter) by n quarters, across year boundaries."""
    idx = yq[0] * 4 + (yq[1] - 1) + n
    return (idx // 4, idx % 4 + 1)


def parse_period(text):
    """'YYYY' -> ('year', y) · 'YYYY-Qn' -> ('quarter', (y, n))."""
    m = _PERIOD_RE.match(text.strip()) \
        if isinstance(text, str) else None
    if not m:
        raise ToolError(f"--period expects YYYY or YYYY-Q1..Q4 "
                        f"(got {text!r})")
    year = int(m.group(1))
    if m.group(2) is None:
        return ("year", year)
    return ("quarter", (year, int(m.group(2))))


def period_matches(yq, period):
    kind, value = period
    if kind == "year":
        return yq[0] == value
    return yq == value


def period_label(period):
    kind, value = period
    return str(value) if kind == "year" else quarter_label(value)


# --------------------------------------------------------------------------
# input loading + validation (every error names its row)
# --------------------------------------------------------------------------

def _fail_row(row_no, msg):
    raise ToolError(f"row {row_no}: {msg}")


def _num_field(row, field_name, row_no, required=True):
    """A >= 0 finite number, or None when absent and not required."""
    raw = row.get(field_name)
    if raw is None or raw == "":
        if required:
            _fail_row(row_no, f"missing required field "
                              f"'{field_name}'")
        return None
    if isinstance(raw, bool):
        _fail_row(row_no, f"'{field_name}' must be a number, not "
                          f"true/false")
    if isinstance(raw, str):
        try:
            value = float(raw.strip())
        except ValueError:
            _fail_row(row_no, f"'{field_name}' is not a number: "
                              f"{raw!r}")
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        _fail_row(row_no, f"'{field_name}' must be a number "
                          f"(got {raw!r})")
    if not math.isfinite(value):
        _fail_row(row_no, f"'{field_name}' must be finite "
                          f"(got {raw!r})")
    if value < 0:
        _fail_row(row_no, f"'{field_name}' must be >= 0 "
                          f"(got {value:g})")
    return value


def normalize_row(row, row_no):
    """Validate one raw row dict -> a clean transaction dict.
    `tax`/`qst` stay None when absent: None tax means "compute
    from the province rate" at calculation time."""
    if not isinstance(row, dict):
        _fail_row(row_no, f"expected an object of fields, "
                          f"got {row!r}")
    raw_date = row.get("date")
    if not isinstance(raw_date, str) \
            or not _DATE_RE.match(raw_date.strip()):
        _fail_row(row_no, f"'date' must be YYYY-MM-DD "
                          f"(got {raw_date!r})")
    try:
        txn_date = date.fromisoformat(raw_date.strip())
    except ValueError:
        _fail_row(row_no, f"'date' is not a real calendar date: "
                          f"{raw_date!r}")
    kind = row.get("kind")
    if not isinstance(kind, str) \
            or kind.strip().lower() not in KINDS:
        _fail_row(row_no, f"'kind' must be 'income' or 'expense' "
                          f"(got {kind!r})")
    description = row.get("description")
    if not isinstance(description, str) or not description.strip():
        _fail_row(row_no, "'description' is required and must be "
                          "a non-empty string")
    province = row.get("province")
    if not isinstance(province, str) \
            or province.strip().upper() not in PROVINCE_DEFAULTS:
        _fail_row(row_no, f"'province' must be one of "
                          f"{' '.join(PROVINCE_DEFAULTS)} "
                          f"(got {province!r})")
    province = province.strip().upper()
    category = row.get("category")
    if category is not None:
        if not isinstance(category, str):
            _fail_row(row_no, f"'category' must be text "
                              f"(got {category!r})")
        category = category.strip() or None
    qst = _num_field(row, "qst", row_no, required=False)
    if qst is not None and province != "QC":
        _fail_row(row_no, "'qst' applies to Quebec (QC) rows only "
                          "— QST is a Quebec tax")
    return {
        "date": txn_date,
        "kind": kind.strip().lower(),
        "description": description.strip(),
        "amount": _num_field(row, "amount", row_no),
        "province": province,
        "tax": _num_field(row, "tax", row_no, required=False),
        "qst": qst,
        "category": category,
    }


def _reject_json_constant(name):
    raise ValueError(f"invalid constant {name}")


def load_rows(path):
    """Read a .json or .csv file -> list of normalized transactions."""
    if not path.is_file():
        raise ToolError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(f"could not read {path.name} "
                            f"({exc.__class__.__name__})")
        try:
            data = json.loads(text, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise ToolError(f"{path.name} is not valid JSON: {exc}")
        if isinstance(data, dict):
            if "transactions" not in data:
                raise ToolError(f"{path.name}: a JSON object must "
                                f"hold the rows under a "
                                f"\"transactions\" key")
            data = data["transactions"]
        if not isinstance(data, list):
            raise ToolError(f"{path.name}: expected a JSON list of "
                            f"transactions (or an object with "
                            f"\"transactions\")")
        raw_rows = [(i + 1, row) for i, row in enumerate(data)]
    elif suffix == ".csv":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(f"could not read {path.name} "
                            f"({exc.__class__.__name__})")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ToolError(f"{path.name}: empty CSV — no header row")
        raw_rows = [(reader.line_num, row) for row in reader]
    else:
        raise ToolError(f"expected a .json or .csv file (got "
                        f"{path.name})")
    if not raw_rows:
        raise ToolError(f"{path.name}: no transactions found — "
                        f"nothing to report")
    return [normalize_row(row, row_no) for row_no, row in raw_rows]


# --------------------------------------------------------------------------
# the math
# --------------------------------------------------------------------------

def effective_tax(txn, rates):
    """The GST/HST on one row: the supplied `tax` when present
    (an explicit 0 for a zero-rated supply is respected), otherwise
    amount x the province rate."""
    if txn["tax"] is not None:
        return txn["tax"]
    return txn["amount"] * rates.rate_for(txn["province"]) / 100.0


def category_name(txn):
    if txn["kind"] != "expense":
        return None
    if not txn["category"]:
        return DEFAULT_CATEGORY
    return CATEGORY_ALIASES.get(txn["category"].lower(),
                                txn["category"])


def compute_period(txns, rates):
    """One quarter's transactions -> its totals block."""
    income_total = sum(t["amount"] for t in txns
                       if t["kind"] == "income")
    expense_total = sum(t["amount"] for t in txns
                        if t["kind"] == "expense")
    collected = sum(effective_tax(t, rates) for t in txns
                    if t["kind"] == "income")
    itcs = sum(effective_tax(t, rates) for t in txns
               if t["kind"] == "expense")
    qst_collected = sum(t["qst"] for t in txns
                        if t["kind"] == "income"
                        and t["qst"] is not None)
    qst_paid = sum(t["qst"] for t in txns
                   if t["kind"] == "expense"
                   and t["qst"] is not None)
    by_category = {}
    for t in txns:
        if t["kind"] == "expense":
            name = category_name(t)
            by_category[name] = by_category.get(name, 0.0) \
                + t["amount"]
    return {
        "income_total": income_total,
        "expense_total": expense_total,
        "gst_hst_collected": collected,
        "itcs": itcs,
        "net_tax_owing": collected - itcs,
        "qst_collected": qst_collected,
        "qst_paid": qst_paid,
        "qst_rows": sum(1 for t in txns if t["qst"] is not None),
        "transactions": len(txns),
        "t2125": {
            "gross_business_income": income_total,
            "expenses_by_category": dict(sorted(by_category.items())),
            "total_expenses": expense_total,
        },
    }


def compute_report(txns, rates, period=None):
    """Group transactions by calendar quarter -> (periods, totals).
    `period` optionally restricts to one year or one quarter."""
    groups = {}
    for t in txns:
        groups.setdefault(quarter_of(t["date"]), []).append(t)
    periods = []
    for yq in sorted(groups):
        if period is not None and not period_matches(yq, period):
            continue
        block = compute_period(groups[yq], rates)
        block["period"] = quarter_label(yq)
        block["quarter"] = list(yq)
        periods.append(block)
    if period is not None and not periods:
        raise ToolError(f"no transactions in period "
                        f"{period_label(period)}")
    totals = {
        "income_total": sum(p["income_total"] for p in periods),
        "expense_total": sum(p["expense_total"] for p in periods),
        "gst_hst_collected": sum(p["gst_hst_collected"]
                                 for p in periods),
        "itcs": sum(p["itcs"] for p in periods),
        "qst_collected": sum(p["qst_collected"] for p in periods),
        "qst_paid": sum(p["qst_paid"] for p in periods),
        "qst_rows": sum(p["qst_rows"] for p in periods),
        "transactions": sum(p["transactions"] for p in periods),
        "expenses_by_category": {},
    }
    totals["net_tax_owing"] = totals["gst_hst_collected"] \
        - totals["itcs"]
    for p in periods:
        for name, value in \
                p["t2125"]["expenses_by_category"].items():
            merged = totals["expenses_by_category"]
            merged[name] = merged.get(name, 0.0) + value
    totals["expenses_by_category"] = dict(
        sorted(totals["expenses_by_category"].items()))
    return periods, totals


def compute_threshold(txns, limit=DEFAULT_LIMIT):
    """CRA's small-supplier test on the last 4 calendar quarters
    ending at the latest transaction's quarter. Crossed only when
    the rolling total EXCEEDS the limit — exactly at it is still
    a small supplier."""
    latest = max(t["date"] for t in txns)
    end = quarter_of(latest)
    window = [add_quarters(end, -3 + i) for i in range(4)]
    income_by_quarter = {yq: 0.0 for yq in window}
    for t in txns:
        if t["kind"] == "income":
            yq = quarter_of(t["date"])
            if yq in income_by_quarter:
                income_by_quarter[yq] += t["amount"]
    rolling_total = sum(income_by_quarter.values())
    crossed = rolling_total > limit
    if crossed:
        status = "crossed"
    elif rolling_total == limit:
        status = "at"
    else:
        status = "under"
    return {
        "latest_transaction": latest.isoformat(),
        "window_end_quarter": quarter_label(end),
        "quarters": [{"quarter": quarter_label(yq),
                      "income": income_by_quarter[yq]}
                     for yq in window],
        "rolling_total": rolling_total,
        "limit": limit,
        "headroom": (limit - rolling_total) if not crossed else 0.0,
        "over_by": (rolling_total - limit) if crossed else 0.0,
        "crossed": crossed,
        "status": status,
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _fmt(value, cad_to_inr=None):
    text = f"{value:,.2f}"
    if cad_to_inr is not None:
        text += f" (₹{value * cad_to_inr:,.0f})"
    return text


def _money(value):
    return round(value, 2)


def _with_inr(obj, fields, cad_to_inr):
    if cad_to_inr is None:
        return obj
    for f in fields:
        if obj.get(f) is not None:
            obj[f + "_inr"] = round(obj[f] * cad_to_inr, 2)
    return obj


_MONEY_FIELDS = ("income_total", "expense_total",
                 "gst_hst_collected", "itcs", "net_tax_owing",
                 "qst_collected", "qst_paid")


def _period_as_json(p, cad_to_inr):
    obj = {"period": p["period"], "quarter": p["quarter"]}
    for f in _MONEY_FIELDS:
        obj[f] = _money(p[f])
    obj["transactions"] = p["transactions"]
    obj["t2125"] = {
        "gross_business_income": _money(
            p["t2125"]["gross_business_income"]),
        "expenses_by_category": {
            k: _money(v) for k, v in
            p["t2125"]["expenses_by_category"].items()},
        "total_expenses": _money(p["t2125"]["total_expenses"]),
    }
    return _with_inr(obj, _MONEY_FIELDS, cad_to_inr)


def report_as_json(periods, totals, source_name, rates, cad_to_inr,
                   period):
    totals_obj = {}
    for f in _MONEY_FIELDS:
        totals_obj[f] = _money(totals[f])
    totals_obj["transactions"] = totals["transactions"]
    totals_obj["t2125"] = {
        "gross_business_income": _money(totals["income_total"]),
        "expenses_by_category": {
            k: _money(v) for k, v in
            totals["expenses_by_category"].items()},
        "total_expenses": _money(totals["expense_total"]),
    }
    _with_inr(totals_obj, _MONEY_FIELDS, cad_to_inr)
    return {
        "tool": TOOL, "version": __version__, "command": "report",
        "file": source_name,
        "currency": "CAD",
        "rates": rates.as_dict(),
        "cad_to_inr": cad_to_inr,
        "period_filter": (period_label(period)
                          if period is not None else None),
        "periods": [_period_as_json(p, cad_to_inr)
                    for p in periods],
        "totals": totals_obj,
        "disclaimer": DISCLAIMER,
    }


def threshold_as_json(result, source_name, cad_to_inr):
    obj = {
        "tool": TOOL, "version": __version__,
        "command": "threshold",
        "file": source_name,
        "currency": "CAD",
        "cad_to_inr": cad_to_inr,
        "latest_transaction": result["latest_transaction"],
        "window_end_quarter": result["window_end_quarter"],
        "quarters": [
            _with_inr({"quarter": q["quarter"],
                       "income": _money(q["income"])},
                      ("income",), cad_to_inr)
            for q in result["quarters"]],
        "rolling_total": _money(result["rolling_total"]),
        "limit": _money(result["limit"]),
        "headroom": _money(result["headroom"]),
        "over_by": _money(result["over_by"]),
        "crossed": result["crossed"],
        "status": result["status"],
        "rule": "small-supplier status ends when taxable supplies "
                "EXCEED the limit over the last 4 calendar "
                "quarters; exactly at the limit does not cross it",
        "disclaimer": DISCLAIMER,
    }
    return _with_inr(obj, ("rolling_total", "headroom", "over_by"),
                     cad_to_inr)


def _period_lines(block, cad_to_inr):
    lines = [
        f"  Income (pre-tax): "
        f"{_fmt(block['income_total'], cad_to_inr)} · GST/HST "
        f"collected: {_fmt(block['gst_hst_collected'], cad_to_inr)}",
        f"  Expenses (pre-tax): "
        f"{_fmt(block['expense_total'], cad_to_inr)} · ITCs (tax "
        f"paid): {_fmt(block['itcs'], cad_to_inr)}",
        f"  NET TAX OWING: "
        f"{_fmt(block['net_tax_owing'], cad_to_inr)} "
        f"(collected − ITCs)",
    ]
    if block["qst_rows"]:
        lines.append(
            f"  QST (memo only, NOT in the net): collected "
            f"{_fmt(block['qst_collected'], cad_to_inr)} · paid "
            f"{_fmt(block['qst_paid'], cad_to_inr)}")
    cats = block["t2125"]["expenses_by_category"]
    cat_text = " · ".join(f"{name} {_fmt(value, cad_to_inr)}"
                          for name, value in cats.items()) \
        if cats else "none"
    lines.append(
        f"  T2125-style prep: gross business income "
        f"{_fmt(block['t2125']['gross_business_income'], cad_to_inr)}"
        f" · expenses — {cat_text} · total expenses "
        f"{_fmt(block['t2125']['total_expenses'], cad_to_inr)}")
    return lines


def render_report_text(periods, totals, source_name, rates,
                       cad_to_inr, period):
    scope = (f" — period {period_label(period)}"
             if period is not None else "")
    lines = [
        f"gst-hst-tracker v{__version__} — report for "
        f"{source_name} ({totals['transactions']} transaction(s))"
        f"{scope}",
        f"Tax rates: defaults as of {RATES_AS_OF} — override any "
        f"rate with --rate PROV=PCT (e.g. --rate NS=14).",
        "Amounts in CAD."
        + (f" INR equivalents at {cad_to_inr:g} per CAD."
           if cad_to_inr is not None else ""),
        "",
    ]
    for p in periods:
        lines.append(p["period"])
        lines.extend(_period_lines(p, cad_to_inr))
        lines.append("")
    if len(periods) > 1:
        lines.append("TOTALS (periods shown)")
        total_block = dict(totals)
        total_block["t2125"] = {
            "gross_business_income": totals["income_total"],
            "expenses_by_category":
                totals["expenses_by_category"],
            "total_expenses": totals["expense_total"],
        }
        lines.extend(_period_lines(total_block, cad_to_inr))
        lines.append("")
    lines.append("Net = GST/HST collected − ITCs. A negative net "
                 "means ITCs exceed tax collected — a refund "
                 "position on the return, not cash in hand.")
    lines.append("Quebec: QST is a separate Revenu Québec tax and "
                 "is never part of the net above; supplied QST "
                 "amounts appear as memo lines only.")
    lines.append(f"Disclaimer: {DISCLAIMER}")
    return "\n".join(lines)


def render_threshold_text(result, source_name, cad_to_inr):
    lines = [
        f"gst-hst-tracker v{__version__} — small-supplier "
        f"threshold for {source_name}",
        f"Rule (as of {RATES_AS_OF}): registration is required "
        f"once taxable supplies EXCEED "
        f"{_fmt(result['limit'], cad_to_inr)} over the last 4 "
        f"calendar quarters. Exactly at the limit does not cross "
        f"it.",
        f"Window: the last 4 calendar quarters ending "
        f"{result['window_end_quarter']} (the quarter of the "
        f"latest transaction, {result['latest_transaction']}):",
    ]
    for q in result["quarters"]:
        lines.append(f"  {q['quarter']}: "
                     f"{_fmt(q['income'], cad_to_inr)}")
    lines.append(f"Rolling 4-quarter taxable income: "
                 f"{_fmt(result['rolling_total'], cad_to_inr)} of "
                 f"{_fmt(result['limit'], cad_to_inr)}")
    if result["status"] == "crossed":
        lines.append(
            f"⚠ THRESHOLD CROSSED — the rolling total exceeds "
            f"{_fmt(result['limit'], cad_to_inr)} by "
            f"{_fmt(result['over_by'], cad_to_inr)}. You are no "
            f"longer a small supplier on these figures: GST/HST "
            f"registration is required.")
    elif result["status"] == "at":
        lines.append(
            f"AT THRESHOLD — exactly "
            f"{_fmt(result['limit'], cad_to_inr)}. CRA's test is "
            f"EXCEEDS, so you are still a small supplier — but "
            f"any further taxable income in this window crosses "
            f"it.")
    else:
        lines.append(
            f"UNDER THRESHOLD — "
            f"{_fmt(result['headroom'], cad_to_inr)} of headroom "
            f"remains. You are still a small supplier on these "
            f"figures.")
    lines.append("The window counts income (taxable supplies) "
                 "only; exempt supplies are not taxable supplies "
                 "and should not be entered as income.")
    lines.append(f"Disclaimer: {DISCLAIMER}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json
    mode ({"error": ...} on stdout, same exit code 2) — an agent
    driving this tool with --json never gets plain text or a
    traceback. The flag lives on the class so subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _cad_to_inr(a):
    rate = getattr(a, "cad_to_inr", None)
    if rate is None:
        return None
    if not math.isfinite(rate) or rate <= 0:
        raise ToolError(f"--cad-to-inr must be a positive finite "
                        f"number (got {rate!r})")
    return rate


def cmd_report(a):
    rates = rates_from_args(a)
    cad_to_inr = _cad_to_inr(a)
    period = parse_period(a.period) if a.period else None
    path = Path(a.file)
    txns = load_rows(path)
    periods, totals = compute_report(txns, rates, period)
    if a.json:
        print(json.dumps(report_as_json(periods, totals, path.name,
                                        rates, cad_to_inr, period),
                         indent=2))
    else:
        print(render_report_text(periods, totals, path.name, rates,
                                 cad_to_inr, period))
    return 0


def cmd_threshold(a):
    cad_to_inr = _cad_to_inr(a)
    limit = a.limit if a.limit is not None else DEFAULT_LIMIT
    if not math.isfinite(limit) or limit <= 0:
        raise ToolError(f"--limit must be a positive finite number "
                        f"(got {limit!r})")
    path = Path(a.file)
    txns = load_rows(path)
    result = compute_threshold(txns, limit)
    if a.json:
        print(json.dumps(threshold_as_json(result, path.name,
                                           cad_to_inr), indent=2))
    else:
        print(render_threshold_text(result, path.name, cad_to_inr))
    return 1 if result["crossed"] else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="GST/HST collected, ITCs, net tax owing and "
                    "the $30,000 small-supplier alarm for Canadian "
                    "freelancers and sole proprietors (stdlib "
                    "only, local only). A tracking aid, not tax "
                    "advice and not a CRA filing.")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_rep = sub.add_parser(
        "report", help="per-quarter GST/HST collected, ITCs, net "
                       "tax owing, and a T2125-style prep section")
    p_rep.add_argument("file", help="ledger file (.json or .csv)")
    p_rep.add_argument("--period", default=None,
                       help="restrict to one year (YYYY) or one "
                            "calendar quarter (YYYY-Q1..Q4); "
                            "default: every quarter in the file")
    p_rep.add_argument("--rate", action="append", default=None,
                       metavar="PROV=PCT",
                       help="override a province's GST/HST rate, "
                            "e.g. --rate NS=14 (repeatable)")
    p_rep.add_argument("--cad-to-inr", type=float, default=None,
                       help="also print INR equivalents at this "
                            "rate per 1 CAD")
    p_rep.add_argument("--json", action="store_true",
                       help="print one JSON object instead of the "
                            "text report")
    p_rep.set_defaults(func=cmd_report)

    p_thr = sub.add_parser(
        "threshold", help="the small-supplier alarm: rolling "
                          "last-4-calendar-quarters taxable income "
                          "vs the $30,000 registration threshold")
    p_thr.add_argument("file", help="ledger file (.json or .csv)")
    p_thr.add_argument("--limit", type=float, default=None,
                       help=f"threshold amount (default "
                            f"{DEFAULT_LIMIT:,.0f})")
    p_thr.add_argument("--cad-to-inr", type=float, default=None,
                       help="also print INR equivalents at this "
                            "rate per 1 CAD")
    p_thr.add_argument("--json", action="store_true",
                       help="print one JSON object instead of the "
                            "text report")
    p_thr.set_defaults(func=cmd_threshold)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
