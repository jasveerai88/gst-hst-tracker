#!/usr/bin/env python3
"""Tests for gst-hst-tracker. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The tax-math tests use numbers worked by hand from the published
rates (GST 5%, HST ON 13%, HST NS 14% since 2025-04-01) — not
numbers copied out of the tool's own output. Both directions are
covered: a clean ledger reports and exits 0; the threshold alarm
exits 1 when crossed and 0 at exactly $30,000 (CRA's test is
EXCEEDS); malformed input exits 2 with the row number named, in
text AND in --json mode.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "gst_hst_tracker.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import gst_hst_tracker as gst  # noqa: E402

RATES = gst.TaxRates()


def txn(**over):
    base = {"date": "2026-01-15", "kind": "income",
            "description": "Work", "amount": 100.0,
            "province": "ON", "tax": None, "qst": None,
            "category": None}
    base.update(over)
    if isinstance(base["date"], str):
        from datetime import date
        base["date"] = date.fromisoformat(base["date"])
    return base


def raw(**over):
    """A raw (pre-validation) row, as load_rows would receive it."""
    base = {"date": "2026-01-15", "kind": "income",
            "description": "Work", "amount": 100.0,
            "province": "ON"}
    base.update(over)
    return base


def run_cli(*args):
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True)


def write_tmp(content, suffix):
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                    encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestNetTaxMath(unittest.TestCase):
    """Hand-checked: collected − ITCs, per calendar quarter."""

    def test_sample_q1_by_hand(self):
        # Q1 income: 4000 ON @13% = 520 · 1500 BC @5% = 75 ·
        # 1000 zero-rated = 0  -> collected 595
        # Q1 expenses: 200 with tax 26 given · 100 ON @13% = 13
        # -> ITCs 39 · net 595 − 39 = 556
        rows = gst.load_rows(EXAMPLES / "sample.json")
        periods, totals = gst.compute_report(rows, RATES)
        q1 = periods[0]
        self.assertEqual(q1["period"], "2026-Q1")
        self.assertAlmostEqual(q1["income_total"], 6500.00)
        self.assertAlmostEqual(q1["gst_hst_collected"], 595.00)
        self.assertAlmostEqual(q1["itcs"], 39.00)
        self.assertAlmostEqual(q1["net_tax_owing"], 556.00)

    def test_sample_q2_and_totals_by_hand(self):
        # Q2: 2500 NS @14% = 350 collected · 800 expense, tax 40
        # given -> net 310. Totals: collected 945, ITCs 79, net 866.
        rows = gst.load_rows(EXAMPLES / "sample.json")
        periods, totals = gst.compute_report(rows, RATES)
        q2 = periods[1]
        self.assertEqual(q2["period"], "2026-Q2")
        self.assertAlmostEqual(q2["gst_hst_collected"], 350.00)
        self.assertAlmostEqual(q2["net_tax_owing"], 310.00)
        self.assertAlmostEqual(totals["income_total"], 9000.00)
        self.assertAlmostEqual(totals["gst_hst_collected"], 945.00)
        self.assertAlmostEqual(totals["itcs"], 79.00)
        self.assertAlmostEqual(totals["net_tax_owing"], 866.00)

    def test_negative_net_is_refund_position(self):
        rows = [txn(amount=100.0),                      # +13 collected
                txn(kind="expense", amount=1000.0)]     # −130 ITCs
        periods, totals = gst.compute_report(rows, RATES)
        self.assertAlmostEqual(totals["net_tax_owing"], -117.00)

    def test_explicit_tax_beats_computed(self):
        t = txn(amount=100.0, tax=7.50)
        self.assertAlmostEqual(gst.effective_tax(t, RATES), 7.50)

    def test_explicit_zero_tax_is_respected(self):
        # a zero-rated supply: tax 0 given, never "corrected" to 13
        t = txn(amount=100.0, tax=0.0)
        self.assertAlmostEqual(gst.effective_tax(t, RATES), 0.0)

    def test_computed_tax_by_province(self):
        for prov, expected in (("ON", 13.0), ("BC", 5.0),
                               ("NS", 14.0), ("NB", 15.0),
                               ("AB", 5.0), ("QC", 5.0)):
            t = txn(amount=100.0, province=prov)
            self.assertAlmostEqual(gst.effective_tax(t, RATES),
                                   expected, msg=prov)

    def test_rate_override_changes_computed_tax(self):
        custom = gst.TaxRates()
        custom.rates["NS"] = 15.0
        t = txn(amount=2500.0, province="NS")
        self.assertAlmostEqual(gst.effective_tax(t, RATES), 350.00)
        self.assertAlmostEqual(gst.effective_tax(t, custom), 375.00)

    def test_t2125_grouping(self):
        rows = gst.load_rows(EXAMPLES / "sample.json")
        periods, totals = gst.compute_report(rows, RATES)
        q1 = periods[0]
        self.assertAlmostEqual(
            q1["t2125"]["gross_business_income"], 6500.00)
        self.assertEqual(
            q1["t2125"]["expenses_by_category"],
            {"Office expenses": 300.00})
        self.assertAlmostEqual(q1["t2125"]["total_expenses"], 300.00)
        self.assertEqual(totals["expenses_by_category"],
                         {"Office expenses": 300.00,
                          "Travel": 800.00})

    def test_category_alias_and_default(self):
        rows = [txn(kind="expense", amount=10.0, category="rent"),
                txn(kind="expense", amount=20.0, category=None),
                txn(kind="expense", amount=30.0,
                    category="My Custom Thing")]
        periods, _ = gst.compute_report(rows, RATES)
        cats = periods[0]["t2125"]["expenses_by_category"]
        self.assertEqual(cats["Rent"], 10.0)
        self.assertEqual(cats["Other expenses"], 20.0)
        self.assertEqual(cats["My Custom Thing"], 30.0)

    def test_period_filter_quarter_and_year(self):
        rows = gst.load_rows(EXAMPLES / "sample.json")
        periods, _ = gst.compute_report(
            rows, RATES, gst.parse_period("2026-Q2"))
        self.assertEqual([p["period"] for p in periods], ["2026-Q2"])
        periods, totals = gst.compute_report(
            rows, RATES, gst.parse_period("2026"))
        self.assertEqual(len(periods), 2)
        self.assertAlmostEqual(totals["net_tax_owing"], 866.00)

    def test_period_with_no_data_is_clean_error(self):
        rows = gst.load_rows(EXAMPLES / "sample.json")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.compute_report(rows, RATES,
                               gst.parse_period("2027-Q1"))
        self.assertIn("no transactions in period", str(ctx.exception))


class TestThreshold(unittest.TestCase):
    def test_sample_under_with_headroom(self):
        rows = gst.load_rows(EXAMPLES / "sample.json")
        r = gst.compute_threshold(rows)
        self.assertEqual(r["window_end_quarter"], "2026-Q2")
        self.assertEqual([q["quarter"] for q in r["quarters"]],
                         ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"])
        self.assertAlmostEqual(r["rolling_total"], 9000.00)
        self.assertAlmostEqual(r["headroom"], 21000.00)
        self.assertFalse(r["crossed"])
        self.assertEqual(r["status"], "under")

    def test_window_rolls_across_year_boundary(self):
        # latest transaction in 2026-Q1 -> window starts 2025-Q2;
        # a Dec-2025 sale counts, a Feb-2025 sale (2025-Q1) does not
        rows = [txn(date="2025-02-10", amount=5000.0),
                txn(date="2025-12-10", amount=7000.0),
                txn(date="2026-02-01", amount=3000.0)]
        r = gst.compute_threshold(rows)
        self.assertEqual([q["quarter"] for q in r["quarters"]],
                         ["2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"])
        by_q = {q["quarter"]: q["income"] for q in r["quarters"]}
        self.assertEqual(by_q["2025-Q4"], 7000.0)
        self.assertAlmostEqual(r["rolling_total"], 10000.00)

    def test_crossing_case(self):
        rows = [txn(date="2026-01-10", amount=20000.0),
                txn(date="2026-05-10", amount=10000.01)]
        r = gst.compute_threshold(rows)
        self.assertTrue(r["crossed"])
        self.assertEqual(r["status"], "crossed")
        self.assertAlmostEqual(r["over_by"], 0.01)
        self.assertAlmostEqual(r["headroom"], 0.0)

    def test_exactly_at_threshold_is_not_crossed(self):
        # CRA's wording is EXCEEDS $30,000: exactly 30,000 is still
        # a small supplier, with zero headroom.
        rows = [txn(date="2026-01-10", amount=15000.0),
                txn(date="2026-08-10", amount=15000.0)]
        r = gst.compute_threshold(rows)
        self.assertAlmostEqual(r["rolling_total"], 30000.00)
        self.assertFalse(r["crossed"])
        self.assertEqual(r["status"], "at")
        self.assertAlmostEqual(r["headroom"], 0.0)

    def test_expenses_do_not_count_toward_threshold(self):
        rows = [txn(amount=29000.0),
                txn(kind="expense", amount=50000.0)]
        r = gst.compute_threshold(rows)
        self.assertAlmostEqual(r["rolling_total"], 29000.00)
        self.assertFalse(r["crossed"])

    def test_single_big_quarter_crosses(self):
        rows = [txn(amount=31000.0)]
        r = gst.compute_threshold(rows)
        self.assertTrue(r["crossed"])
        self.assertAlmostEqual(r["over_by"], 1000.00)


class TestQuarterBucketing(unittest.TestCase):
    def test_quarter_boundaries(self):
        from datetime import date
        self.assertEqual(gst.quarter_of(date(2026, 3, 31)), (2026, 1))
        self.assertEqual(gst.quarter_of(date(2026, 4, 1)), (2026, 2))
        self.assertEqual(gst.quarter_of(date(2025, 12, 31)), (2025, 4))
        self.assertEqual(gst.quarter_of(date(2026, 1, 1)), (2026, 1))

    def test_add_quarters_across_years(self):
        self.assertEqual(gst.add_quarters((2026, 1), -1), (2025, 4))
        self.assertEqual(gst.add_quarters((2025, 4), 1), (2026, 1))
        self.assertEqual(gst.add_quarters((2026, 2), -3), (2025, 3))

    def test_dec_and_jan_land_in_different_periods(self):
        rows = [txn(date="2025-12-15", amount=100.0),
                txn(date="2026-01-15", amount=200.0)]
        periods, _ = gst.compute_report(rows, RATES)
        self.assertEqual([p["period"] for p in periods],
                         ["2025-Q4", "2026-Q1"])
        self.assertAlmostEqual(periods[0]["income_total"], 100.0)
        self.assertAlmostEqual(periods[1]["income_total"], 200.0)


class TestQstBoundary(unittest.TestCase):
    def test_qst_tracked_separately_never_in_net(self):
        rows = [txn(province="QC", amount=1000.0, qst=99.75),
                txn(province="QC", kind="expense", amount=200.0,
                    qst=19.95)]
        periods, totals = gst.compute_report(rows, RATES)
        # net is GST only: 5% of 1000 − 5% of 200 = 50 − 10 = 40
        self.assertAlmostEqual(totals["net_tax_owing"], 40.00)
        self.assertAlmostEqual(totals["qst_collected"], 99.75)
        self.assertAlmostEqual(totals["qst_paid"], 19.95)

    def test_qst_on_non_qc_row_is_an_error(self):
        path = write_tmp(json.dumps(
            [raw(province="ON", qst=9.99)]), ".json")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn("row 1", str(ctx.exception))
        self.assertIn("qst", str(ctx.exception))


class TestValidation(unittest.TestCase):
    def _bad(self, rows, needle):
        path = write_tmp(json.dumps(rows), ".json")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn(needle, str(ctx.exception))

    def test_bad_date_format_names_row(self):
        self._bad([raw(), raw(date="15/01/2026")], "row 2")

    def test_impossible_date(self):
        self._bad([raw(date="2026-02-30")], "not a real calendar date")

    def test_unknown_kind(self):
        self._bad([raw(kind="refund")], "'kind'")

    def test_unknown_province(self):
        self._bad([raw(province="XX")], "'province'")

    def test_negative_amount(self):
        self._bad([raw(amount=-5)], "row 1")

    def test_negative_tax(self):
        self._bad([raw(tax=-1)], "'tax'")

    def test_missing_amount(self):
        row = raw()
        del row["amount"]
        self._bad([row], "missing required field 'amount'")

    def test_empty_description(self):
        self._bad([raw(description="  ")], "description")

    def test_nan_rejected(self):
        path = write_tmp('[{"date": "2026-01-15", "kind": "income",'
                         ' "description": "X", "amount": NaN,'
                         ' "province": "ON"}]', ".json")
        with self.assertRaises(gst.ToolError):
            gst.load_rows(Path(path))

    def test_bool_is_not_a_number(self):
        self._bad([raw(amount=True)], "row 1")

    def test_row_not_an_object(self):
        self._bad([42], "row 1")

    def test_empty_file(self):
        path = write_tmp("[]", ".json")
        with self.assertRaises(gst.ToolError):
            gst.load_rows(Path(path))

    def test_malformed_json(self):
        path = write_tmp("{not json", ".json")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_object_without_transactions_key(self):
        path = write_tmp('{"rows": []}', ".json")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn("transactions", str(ctx.exception))

    def test_csv_bad_number_names_line(self):
        path = write_tmp(
            "date,kind,description,amount,province\n"
            "2026-01-15,income,Good,100,ON\n"
            "2026-01-16,income,Bad,$50,ON\n", ".csv")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn("row 3", str(ctx.exception))
        self.assertIn("not a number", str(ctx.exception))

    def test_csv_bad_date_names_line(self):
        path = write_tmp(
            "date,kind,description,amount,province\n"
            "2026-13-01,income,Bad month,100,ON\n", ".csv")
        with self.assertRaises(gst.ToolError) as ctx:
            gst.load_rows(Path(path))
        self.assertIn("row 2", str(ctx.exception))

    def test_lowercase_province_and_kind_accepted(self):
        rows = gst.load_rows(Path(write_tmp(json.dumps(
            [raw(province="on", kind="Income")]), ".json")))
        self.assertEqual(rows[0]["province"], "ON")
        self.assertEqual(rows[0]["kind"], "income")


class TestCsvJsonAgreement(unittest.TestCase):
    def test_sample_files_agree(self):
        a = gst.load_rows(EXAMPLES / "sample.json")
        b = gst.load_rows(EXAMPLES / "sample.csv")
        _, totals_a = gst.compute_report(a, RATES)
        _, totals_b = gst.compute_report(b, RATES)
        for key in ("income_total", "gst_hst_collected", "itcs",
                    "net_tax_owing"):
            self.assertAlmostEqual(totals_a[key], totals_b[key],
                                   msg=key)
        self.assertAlmostEqual(totals_a["net_tax_owing"], 866.00)
        thr_a = gst.compute_threshold(a)
        thr_b = gst.compute_threshold(b)
        self.assertAlmostEqual(thr_a["rolling_total"],
                               thr_b["rolling_total"])


class TestCli(unittest.TestCase):
    def test_report_sample_exit_0(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("NET TAX OWING: 866.00", p.stdout)
        self.assertIn("Disclaimer:", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_report_period_flag(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--period", "2026-Q1")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("NET TAX OWING: 556.00", p.stdout)
        self.assertNotIn("2026-Q2", p.stdout)

    def test_report_bad_period_is_clean_error(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--period", "Q1-2026")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_report_json_mode(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"), "--json")
        self.assertEqual(p.returncode, 0)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["tool"], "gst-hst-tracker")
        self.assertEqual(obj["version"], "0.1.0")
        self.assertEqual(obj["currency"], "CAD")
        self.assertAlmostEqual(obj["totals"]["net_tax_owing"], 866.00)
        self.assertEqual(obj["totals"]["t2125"]
                         ["expenses_by_category"],
                         {"Office expenses": 300.00,
                          "Travel": 800.00})
        self.assertIn("not tax advice", obj["disclaimer"])
        self.assertEqual(obj["rates"]["provinces"]["NS"]
                         ["rate_pct"], 14.0)

    def test_json_and_text_agree(self):
        text = run_cli("report", str(EXAMPLES / "sample.json"))
        js = run_cli("report", str(EXAMPLES / "sample.json"),
                     "--json")
        self.assertEqual(text.returncode, js.returncode)
        obj = json.loads(js.stdout)
        self.assertIn(f"{obj['totals']['net_tax_owing']:,.2f}",
                      text.stdout)

    def test_threshold_sample_exit_0(self):
        p = run_cli("threshold", str(EXAMPLES / "sample.json"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("UNDER THRESHOLD", p.stdout)
        self.assertIn("21,000.00 of headroom", p.stdout)
        self.assertIn("Disclaimer:", p.stdout)

    def test_threshold_crossed_exit_1(self):
        path = write_tmp(json.dumps(
            [raw(amount=31000.0)]), ".json")
        p = run_cli("threshold", path)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("THRESHOLD CROSSED", p.stdout)

    def test_threshold_exactly_at_exit_0(self):
        path = write_tmp(json.dumps(
            [raw(amount=30000.0)]), ".json")
        p = run_cli("threshold", path)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("AT THRESHOLD", p.stdout)

    def test_threshold_json_mode(self):
        p = run_cli("threshold", str(EXAMPLES / "sample.json"),
                    "--json")
        self.assertEqual(p.returncode, 0)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["command"], "threshold")
        self.assertFalse(obj["crossed"])
        self.assertAlmostEqual(obj["rolling_total"], 9000.00)
        self.assertAlmostEqual(obj["headroom"], 21000.00)
        self.assertEqual([q["quarter"] for q in obj["quarters"]],
                         ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"])
        self.assertIn("not tax advice", obj["disclaimer"])

    def test_missing_file_clean_error(self):
        p = run_cli("report", "/nonexistent/ledger.json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR: file not found", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_missing_file_json_error_object(self):
        p = run_cli("report", "/nonexistent/ledger.json", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout),
                         {"error": "file not found: "
                                   "/nonexistent/ledger.json"})

    def test_bad_row_json_error_object(self):
        path = write_tmp(json.dumps([raw(amount=-3)]), ".json")
        p = run_cli("report", path, "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("row 1", json.loads(p.stdout)["error"])

    def test_argparse_error_is_json_in_json_mode(self):
        p = run_cli("report", "--json")  # missing the file argument
        self.assertEqual(p.returncode, 2)
        self.assertIn("error", json.loads(p.stdout))

    def test_wrong_extension(self):
        path = write_tmp("[]", ".txt")
        p = run_cli("report", path)
        self.assertEqual(p.returncode, 2)
        self.assertIn(".json or .csv", p.stdout)

    def test_rate_override_flag_changes_cli_result(self):
        # NS at the old 15% instead of 14%: Q2 collected 350 -> 375,
        # totals net 866 -> 891.
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--rate", "NS=15", "--json")
        obj = json.loads(p.stdout)
        self.assertAlmostEqual(obj["totals"]["gst_hst_collected"],
                               970.00)
        self.assertAlmostEqual(obj["totals"]["net_tax_owing"], 891.00)
        self.assertEqual(obj["rates"]["provinces"]["NS"]
                         ["default_pct"], 14.0)

    def test_bad_rate_flag_is_clean_error(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--rate", "XX=5")
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown province", p.stdout)

    def test_cad_to_inr_fields(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--cad-to-inr", "67.97", "--json")
        obj = json.loads(p.stdout)
        self.assertAlmostEqual(obj["totals"]["net_tax_owing_inr"],
                               round(866.00 * 67.97, 2), places=1)
        p2 = run_cli("report", str(EXAMPLES / "sample.json"),
                     "--cad-to-inr", "67.97")
        self.assertIn("₹", p2.stdout)

    def test_bad_cad_to_inr(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--cad-to-inr", "-5")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR", p.stdout)

    def test_bad_limit(self):
        p = run_cli("threshold", str(EXAMPLES / "sample.json"),
                    "--limit", "0")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR", p.stdout)


if __name__ == "__main__":
    unittest.main()
