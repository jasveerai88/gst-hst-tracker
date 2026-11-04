# Security Policy

## What this tool touches

`gst-hst-tracker` reads **one local file**: the ledger you pass
on the command line (JSON or CSV, or standard input). Nothing in
that file is executed — rows are parsed as data and validated
field by field; a malformed row is an error, never code. The
tool makes **no network requests**, writes nothing anywhere, and
collects no telemetry.

Your ledger contains your clients' names (if you put them in
descriptions), your income, and your expenses. It stays on your
machine because the program has no way to send it anywhere.
Treat sample ledgers in bug reports accordingly: strip real
client details before attaching one to a public issue.

## Reporting a vulnerability

Please report security issues **privately** through GitHub's
private vulnerability reporting: the repository's **Security**
tab → **Report a vulnerability** (GitHub Security Advisories).
That keeps the details between you and the maintainer until a
fix is out.

Correctness bugs that are not security issues — a wrong figure,
a mishandled edge case — are just as welcome as regular GitHub
issues. For a tax tool, arithmetic *is* the product: if you find
a case where the tool's number disagrees with a hand-worked
calculation from the stated rates, please open an issue with the
hand-working. (Tax *interpretation* questions can't be answered
here — the tool is not tax advice; the CRA and Revenu Québec
publish the rules it encodes.)

## Scope notes

- Pure Python 3.10+ standard library; there are no third-party
  dependencies to compromise.
- The tool reports only figures computed from the ledger you
  give it. It never fetches live rates, exchange rates, or
  deadlines — dated defaults are stamped in every output, and
  conversions use only a rate you supply.
