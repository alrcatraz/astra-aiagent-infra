#!/usr/bin/env python3
"""Verify a kdbx write did not damage the database. Run in a FRESH process.

Why this exists: an entry-count check is insufficient. The XML round-trip failure
mode (keepassxc-cli export -> import) preserves every entry and every `<Value Ref>`
while emptying the entire Binary pool, so entry counts stay perfect and the vault is
massacred. This asserts the things that actually break.

Usage:
    verify-kdbx-write.py <db.kdbx> --pw-var KEEPASS_PASSWORD \
                         [--expect-entries N] [--baseline-json FILE] [--write-baseline FILE]

  --pw-var        variable name in ~/.hermes/.env holding the db password
                  (containers often need KEEPASS_SYNC_PASSWORD, not KEEPASS_PASSWORD)
  --expect-entries  assert the entry count (excludes nothing; pykeepass kp.entries)
  --baseline-json  compare attachment stats / counts against a previously written
                   baseline (written with --write-baseline) and fail on regression
  --write-baseline record current stats as the baseline to compare against later

Exit 0 = all assertions pass. Exit 1 = at least one failed (details on stderr).
Never prints a secret value: attributes are reported as length + sha256[:8].
"""
import argparse
import hashlib
import json
import os
import sys

ENVF = os.path.expanduser("~/.hermes/.env")


def resolve_pw(var):
    """Read KEY=value from the bootstrap env. Keeps the value in-process only."""
    try:
        with open(ENVF) as fh:
            for line in fh:
                if line.startswith(var + "="):
                    return line.split("=", 1)[1].strip().strip("'").strip('"')
    except OSError as ex:
        sys.exit(f"cannot read {ENVF}: {ex}")
    sys.exit(f"ERROR: {var} not found in {ENVF}")


def h(val):
    """Short fingerprint of a value — never the value itself."""
    if val is None:
        return "EMPTY"
    raw = val if isinstance(val, bytes) else str(val).encode()
    return hashlib.sha256(raw).hexdigest()[:8] if raw else "EMPTY"


def attachment_stats(kp):
    """(total, nonzero, nonzero_bytes) across the whole db.

    The triple is the point: an XML round-trip keeps `total` identical while
    driving `nonzero` and `nonzero_bytes` to zero.
    """
    total = nonzero = nbytes = 0
    for e in kp.entries:
        for a in (e.attachments or []):
            data = a.data
            data = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
            total += 1
            if data:
                nonzero += 1
                nbytes += len(data)
    return (total, nonzero, nbytes)


def duplicate_attachment_names(kp):
    """Entries holding two attachments under the same filename.

    pykeepass add_attachment APPENDS — it does not replace a same-named attachment,
    so a naive repair leaves a 0-byte and a good copy side by side.
    """
    dupes = []
    for e in kp.entries:
        seen = {}
        for a in (e.attachments or []):
            seen[a.filename] = seen.get(a.filename, 0) + 1
        bad = [k for k, v in seen.items() if v > 1]
        if bad:
            dupes.append(f"{e.title!r}: {bad}")
    return dupes


def live_attrs(entry):
    """Attributes as they currently stand — direct <String> children only.

    A findall('.//String') also walks <History>, which reports values the entry
    held in past generations and makes a corrected entry look stale.
    """
    out = {}
    for node in entry._element.findall("./String"):
        key = node.findtext("Key")
        val = node.findtext("Value") or ""
        prot = node.find("Value").get("Protected")
        out[key] = (val, prot)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--pw-var", default="KEEPASS_PASSWORD")
    ap.add_argument("--expect-entries", type=int)
    ap.add_argument("--baseline-json")
    ap.add_argument("--write-baseline")
    ap.add_argument("--show-attrs")
    args = ap.parse_args()

    from pykeepass import PyKeePass  # deferred so --help works without pykeepass

    kp = PyKeePass(args.db, password=resolve_pw(args.pw_var))
    errors = []

    n_entries = len(kp.entries)
    a_total, a_nonzero, a_bytes = attachment_stats(kp)

    print(f"entries={n_entries}  attachments: total={a_total} "
          f"nonzero={a_nonzero} bytes={a_bytes}")

    if args.expect_entries is not None and n_entries != args.expect_entries:
        errors.append(f"entries {n_entries} != expected {args.expect_entries}")

    dupes = duplicate_attachment_names(kp)
    if dupes:
        errors.append(f"duplicate attachment filenames: {dupes}")
    else:
        print("no duplicate attachment filenames: ok")

    if args.baseline_json and os.path.exists(args.baseline_json):
        base = json.load(open(args.baseline_json))
        if a_nonzero < base["attachments_nonzero"]:
            errors.append(f"nonzero attachments regressed "
                          f"{base['attachments_nonzero']} -> {a_nonzero}")
        if a_bytes < base["attachments_bytes"]:
            errors.append(f"attachment bytes regressed "
                          f"{base['attachments_bytes']} -> {a_bytes}")
        if base["attachments_nonzero"] and a_nonzero == 0:
            errors.append("WIPE FUSE: every attachment is now empty")
        prev_entries = base.get("entries")
        if prev_entries is not None:
            print(f"baseline: entries={prev_entries} "
                  f"nonzero={base['attachments_nonzero']} "
                  f"bytes={base['attachments_bytes']}")

    if args.show_attrs:
        for e in kp.entries:
            if e.title == args.show_attrs:
                for k, (v, prot) in sorted(live_attrs(e).items()):
                    print(f"  {k:28} len={len(v):3} #{h(v)} Protected={prot}")

    if args.write_baseline:
        json.dump({
            "db": os.path.abspath(args.db),
            "entries": n_entries,
            "attachments_total": a_total,
            "attachments_nonzero": a_nonzero,
            "attachments_bytes": a_bytes,
        }, open(args.write_baseline, "w"), indent=2)
        print(f"baseline written -> {args.write_baseline}")

    if errors:
        print("RESULT: FAIL")
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
