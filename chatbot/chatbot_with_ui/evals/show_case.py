"""Show exactly what the bot did for one eval case (from the latest results file).

    python evals/show_case.py M05
    python evals/show_case.py M05 --file evals/results/20261025_120000_baseline.json
    python evals/show_case.py M05 --full      # also print the full retrieved passages
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    # Windows consoles default to a legacy encoding and crash on characters like U+2011 or U+3010.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--file", help="results .json (default: newest in evals/results)")
    parser.add_argument("--full", action="store_true", help="print full retrieved passages")
    args = parser.parse_args()

    path = Path(args.file) if args.file else None
    if path is None:
        files = sorted((HERE / "results").glob("*.json"))
        if not files:
            sys.exit("No results files found in evals/results/")
        path = files[-1]

    data = json.loads(path.read_text(encoding="utf-8"))
    item = next((r for r in data["results"] if r["case"]["id"] == args.case_id), None)
    if item is None:
        sys.exit(f"{args.case_id} not found in {path.name}")

    case, raw, score = item["case"], item["raw"], item["score"]
    print(f"file: {path.name}")
    print(f"{case['id']} [{case['category']}] role={case.get('role', '-')}  ->  {'PASS' if score['passed'] else 'FAIL'}")
    print(f"question : {case['question']}")
    print(f"expected : {case.get('reference', '')}")
    print(f"checks   : {score['checks']}")
    print(f"tools    : {raw.get('tool_calls')}   escalated={raw.get('escalated')}   card={raw.get('pending')}")

    retrieved = raw.get("retrieved") or ""
    print("\nRETRIEVED PASSAGES (what the search handed the model):")
    if not retrieved:
        print("  (none)")
    elif args.full:
        print(retrieved)
    else:
        for line in re.findall(r"^\[\d+\].*$", retrieved, flags=re.MULTILINE):
            print("  " + line)
        print("  (use --full to see the text)")

    print("\nFINAL ANSWER:\n" + (raw.get("final") or "(none)"))


if __name__ == "__main__":
    main()
