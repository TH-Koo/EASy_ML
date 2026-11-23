"""Compare capability scores between the committed ontology and the working copy.

Usage (repository root)::

    python scripts/check_ontology_change.py 로봇청소기
    python scripts/check_ontology_change.py 세탁기 --limit 3
    python scripts/check_ontology_change.py --file dataset/evidence_cache/02937221bedae52a1218f652.json

The "before" ontology is read from git HEAD, so nothing in the working tree is
changed. Only saved evidence caches are rescored; no crawling or API calls.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from analysis_engine import OntologyAnalysisEngine  # noqa: E402
from fides_ml.features import score_bundle  # noqa: E402


def head_ontology(target: Path, ref: str) -> None:
    names = subprocess.run(
        ["git", "ls-tree", "--name-only", ref, "ontology/"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.split()
    for name in names:
        data = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=ROOT, check=True, capture_output=True).stdout
        (target / Path(name).name).write_bytes(data)


def find_caches(keyword: str, limit: int) -> list[Path]:
    found = []
    for path in sorted(glob.glob(str(ROOT / "dataset" / "evidence_cache" / "*.json"))):
        bundle = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("bundle_kwargs", {})
        title = (bundle.get("product_json") or {}).get("title", "")
        if keyword.lower() in title.lower():
            found.append(Path(path))
            if len(found) >= limit:
                break
    return found


def summarize(result) -> dict:
    return {c["capability_id"]: c for c in result.capability_scores}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", help="product title keyword, e.g. 로봇청소기")
    parser.add_argument("--file", action="append", default=[], help="evidence cache JSON path")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--ref", default="HEAD", help="git ref of the 'before' ontology")
    parser.add_argument("--all", action="store_true", help="show unchanged capabilities too")
    args = parser.parse_args()

    files = [Path(f) for f in args.file]
    if args.keyword:
        files += find_caches(args.keyword, args.limit)
    if not files:
        parser.error("no evidence cache matched; pass a keyword or --file")

    with tempfile.TemporaryDirectory() as tmp:
        head_ontology(Path(tmp), args.ref)
        engines = {"before": OntologyAnalysisEngine(tmp), "after": OntologyAnalysisEngine(str(ROOT / "ontology"))}
        for path in files:
            bundle = json.loads(path.read_text(encoding="utf-8-sig"))["bundle_kwargs"]
            print(f"\n== {(bundle.get('product_json') or {}).get('title')}  [{path.name}]")
            results = {}
            for tag, engine in engines.items():
                with contextlib.redirect_stdout(io.StringIO()):
                    results[tag] = score_bundle(bundle, engine)
            for tag, r in results.items():
                print(f"  {tag:6s} ACCS={r.accs:6.2f} HES={r.hes:6.2f} TES={r.tes:6.2f} CES={r.ces:6.2f}  {r.verdict}")
            before, after = summarize(results["before"]), summarize(results["after"])
            print(f"  {'capability':24s} {'before':>16s} -> {'after':<16s} strong patterns (after)")
            for cap_id, a in sorted(after.items(), key=lambda kv: -kv[1]["final_score"]):
                b = before.get(cap_id, {})
                changed = (b.get("final_score") != a["final_score"]
                           or b.get("positive_claim") != a["positive_claim"]
                           or b.get("matched_strong_patterns") != a["matched_strong_patterns"])
                if not (changed or args.all):
                    continue
                fmt = lambda c: f"{c.get('final_score', 0):6.2f}{' claim' if c.get('positive_claim') else '      '}"
                print(f"  {a['capability_name_ko'][:22]:24s} {fmt(b):>16s} -> {fmt(a):<16s} "
                      f"{a['matched_strong_patterns']} missing={a['missing_required_components']}")


if __name__ == "__main__":
    main()
