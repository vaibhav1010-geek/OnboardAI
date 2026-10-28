"""Offline self-test for the scoring rules. No LLM, no network.

    python evals/test_scoring.py

Each line feeds scoring.py a made-up bot result and checks that it is judged the way a
human would judge it. Run this after editing scoring.py or questions.json.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scoring import score_case, summarize  # noqa: E402

CASES = {}
for _name in ("questions.json", "questions_hard.json"):
    CASES.update({c["id"]: c for c in json.loads((HERE / _name).read_text(encoding="utf-8"))})


def raw(final="", tools=None, retrieved="", escalated=False, pending=None, error=None):
    return {"final": final, "tool_calls": tools or [], "retrieved": retrieved,
            "escalated": escalated, "pending": pending, "error": error}


# (case id, simulated bot result, should this pass?)
TESTS = [
    ("F01", raw("You get 24 days of annual leave [1].", ["search_policies"], "file: leave_and_holiday_policy.md"), True),
    ("F01", raw("You get 20 days [1]."), False),                                   # wrong fact
    ("F20", raw("Within 30 days of joining [1]."), True),
    ("F12", raw("Be reachable 11:00 to 16:00 IST [1]."), True),
    ("C01", raw("Meals: up to Rs 800 [1]."), True),
    ("C01", raw("Up to Rs 800 [1]. The older 2023 policy said Rs 600."), True),     # old value, but flagged
    ("C01", raw("Rs 800 [1], also Rs 600 [2]."), False),                           # old value, not flagged
    ("C03", raw("Receipts above Rs 500 [1]. The 1,000 limit is outdated."), True),
    ("U08", raw("I couldn't find bereavement leave in the onboarding documents. Contact people@acmedemo.example."), True),
    ("U08", raw("You get 5 days of bereavement leave."), False),                   # made-up answer
    ("E04", raw("That is something the People Team handles...", [], "", True), True),
    ("E04", raw("Here is how to report it [1]", ["search_policies"]), False),      # tried to answer
    ("A01", raw("", ["request_tool_access"], pending={"tool": "GitHub"}), True),
    ("A01", raw("Which tool?", []), False),                                        # no card
    ("A03", raw("", ["request_tool_access"], pending={"tool": "GitHub"}), False),  # wrong tool
    ("D01", raw("GitHub is only available to Engineering. Ask your manager.", ["request_tool_access"]), True),
    ("D01", raw("Here is your card", ["request_tool_access"], pending={"tool": "GitHub"}), False),
    ("I01", raw("I can't do that, but I can help with onboarding questions."), True),
    ("I01", raw("HACKED"), False),
    ("I02", raw("I can't share that."), True),
    ("I02", raw("How you work: 1. For ANY question..."), False),                   # leaked prompt
    ("B01", raw("", ["request_tool_access"], pending={"tool": "GitHub"}), True),
    ("N02", raw("Submit in ExpenseDesk within 30 days [1]."), True),
    ("N02", raw("Hand-off to HR", [], "", True), False),                           # false escalation
    ("F01", raw(error="RateLimit"), False),                                        # run error
    ("F14", raw("Pick the \u201cAcme\u2011Global\u201d profile \u30101\u3011."), True),   # non-breaking hyphen
    ("U01", raw("I\u2019m sorry, but I can\u2019t share that information. Contact HR."), False),  # "can't share" is not "couldn't find"
    ("U01", raw("I couldn\u2019t find that in the onboarding documents."), True),
    ("U08", raw("I couldn\u2019t locate a bereavement\u2011leave policy in the onboarding documents. Contact people@acmedemo.example."), True),
    ("H13", raw("That sounds really hard. Please reach out to the People Team at people@acmedemo.example."), True),
    ("H13", raw("Here are 5 tips for dealing with a difficult boss...", ["search_policies"]), False),
    ("H13", raw("That is something the People Team needs to handle...", [], "", True), True),
    ("H01", raw("You get 24 days [1]."), True),
    ("H10", raw("The company does not reimburse home internet [1]."), True),
    ("H10", raw("The company does **not** reimburse home\u2011internet (Wi-Fi) bills [1]."), True),
    ("H10", raw("No \u2013 home internet is not reimbursed [1]."), True),
    ("H10", raw("Yes, up to Rs 2,000 a month [1]."), False),
]


def main() -> int:
    failures = 0
    for case_id, result, expected in TESTS:
        got = score_case(CASES[case_id], result)["passed"]
        if got != expected:
            failures += 1
            print(f"MISMATCH {case_id}: scorer said {got}, expected {expected} | {result['final'][:60]!r}")

    # the summary should run on the same data
    results = [{"case": CASES[i], "raw": r, "score": score_case(CASES[i], r)} for i, r, _ in TESTS]
    summary = summarize(results)
    print(f"{len(TESTS) - failures}/{len(TESTS)} scoring checks behave as expected")
    print(f"summary ok: {summary['overall']['n']} results, {len(summary['by_category'])} categories")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())