"""Checks that questions.json is sound. No LLM, no network.

    python evals/check_questions.py

- ids are unique and categories are known
- every expected fact really appears in the document(s) the case points to
  (so a failing eval means the bot is wrong, not the question)
- every expected_sources file exists
"""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scoring import ANSWER_CATEGORIES, norm  # noqa: E402

DOCS = HERE.parent / "docs"
KNOWN = ANSWER_CATEGORIES | {"unanswerable", "escalate", "access_confirm", "access_denied", "injection", "no_bypass", "escalate_soft"}


def main() -> int:
    cases = []
    for name in ("questions.json", "questions_hard.json"):
        cases += json.loads((HERE / name).read_text(encoding="utf-8"))
    problems = []

    ids = [c["id"] for c in cases]
    problems += [f"duplicate id: {i}" for i, n in Counter(ids).items() if n > 1]

    for case in cases:
        cid = case["id"]
        if case["category"] not in KNOWN:
            problems.append(f"{cid}: unknown category {case['category']}")
        if case["category"] in ("access_confirm", "no_bypass") and not case.get("expected_tool"):
            problems.append(f"{cid}: missing expected_tool")

        sources = case.get("expected_sources", [])
        missing = [s for s in sources if not (DOCS / s).exists()]
        problems += [f"{cid}: source file not found: {s}" for s in missing]

        if case["category"] in ANSWER_CATEGORIES and sources and not missing:
            text = norm(" ".join((DOCS / s).read_text(encoding="utf-8") for s in sources))
            for group in case.get("expected_facts", []):
                if not any(norm(alt) in text for alt in group):
                    problems.append(f"{cid}: none of {group} appears in {sources}")

    counts = dict(Counter(c["category"] for c in cases))
    print(f"{len(cases)} cases: {counts}")
    if problems:
        print("\nPROBLEMS:")
        print("\n".join(f"  - {p}" for p in problems))
        return 1
    print("questions.json looks sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())