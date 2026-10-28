"""Run the onboarding eval set against the real agent.

Examples (run from the chatbot_with_ui folder):
    python evals/run_evals.py                          # all 70 core cases, local scoring
    python evals/run_evals.py --category escalate,unanswerable
    python evals/run_evals.py --limit 10 --label smoke
    python evals/run_evals.py --judge                  # add LLM-judged correctness + groundedness
    python evals/run_evals.py --langsmith              # also push dataset + experiment to LangSmith
    python evals/run_evals.py --compare evals/results/a.json evals/results/b.json

Eval runs use an in-memory checkpointer and switch audit logging off, so they never
touch your chat history or analytics tables. Nothing here creates Jira tickets: access
requests stop at the confirmation card and are never approved.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from scoring import ANSWER_CATEGORIES, score_case, summarize  # noqa: E402

QUESTIONS_PATH = HERE / "questions.json"
HARD_PATH = HERE / "questions_hard.json"
RESULTS_DIR = HERE / "results"

_bot = None
_escalation_texts = None


# ------------------------------------------------------------------
# bot setup (heavy imports happen lazily so scoring can be tested alone)
# ------------------------------------------------------------------
def get_bot():
    global _bot, _escalation_texts
    if _bot is None:
        os.environ["ONBOARDING_EVAL"] = "1"  # silences audit logging (see actions.audit)
        from langgraph.checkpoint.memory import MemorySaver

        import backend

        _bot = backend.graph.compile(checkpointer=MemorySaver())
        _escalation_texts = set(backend.ESCALATION_TEXT.values())
    return _bot, _escalation_texts


def config_snapshot() -> dict:
    """What was being tested. Saved with every run so before/after tables are honest."""
    import backend
    import rag

    return {
        "llm": getattr(backend.llm, "model_name", "unknown"),
        "temperature": getattr(backend.llm, "temperature", None),
        "embedding_model": "BAAI/bge-m3",
        "chunk_size": rag.CHUNK_SIZE,
        "chunk_overlap": rag.CHUNK_OVERLAP,
        "top_k": rag.TOP_K,
        "min_relevance": rag.MIN_RELEVANCE,
        "stale_after_days": rag.STALE_AFTER_DAYS,
    }


# ------------------------------------------------------------------
# running one case
# ------------------------------------------------------------------
class DailyLimitReached(Exception):
    """The provider's per-day quota is used up. Retrying will not help until it resets."""


def _invoke_with_retry(bot, payload, config, attempts=5):
    """Per-minute rate limits clear in seconds: back off and retry.
    Per-day limits do not: stop the run cleanly instead of failing every remaining case."""
    for attempt in range(attempts):
        try:
            return bot.invoke(payload, config=config)
        except Exception as error:  # noqa: BLE001
            text = str(error).lower()
            if any(marker in text for marker in ("per day", "(tpd)", "(rpd)")) and "limit" in text:
                raise DailyLimitReached(str(error)) from error
            limited = "429" in text or ("rate" in text and "limit" in text)
            if limited and attempt < attempts - 1:
                time.sleep(5 * (2 ** attempt))
                continue
            raise


def execute_case(case: dict) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    bot, escalation_texts = get_bot()
    thread_id = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"eval_{case['id']}",
        "metadata": {"eval_case": case["id"], "category": case["category"]},
    }
    payload = {
        "messages": [HumanMessage(content=case["question"])],
        "user_role": case.get("role", "Engineering"),
    }

    try:
        _invoke_with_retry(bot, payload, config)
        snapshot = bot.get_state(config)
    except DailyLimitReached:
        raise
    except Exception as error:  # noqa: BLE001
        return {"final": "", "tool_calls": [], "retrieved": "", "escalated": False,
                "pending": None, "error": f"{type(error).__name__}: {error}"}

    messages = snapshot.values.get("messages", [])

    pending = None
    for task in snapshot.tasks:
        for interrupt_item in getattr(task, "interrupts", ()) or ():
            pending = interrupt_item.value
            break

    final = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls and message.content:
            final = message.content if isinstance(message.content, str) else str(message.content)
            break

    tool_calls = [
        call["name"]
        for message in messages if isinstance(message, AIMessage)
        for call in (message.tool_calls or [])
    ]
    search_queries = [
        call.get("args", {}).get("query", "")
        for message in messages if isinstance(message, AIMessage)
        for call in (message.tool_calls or []) if call["name"] == "search_policies"
    ]
    retrieved = "\n".join(
        str(message.content)
        for message in messages
        if isinstance(message, ToolMessage) and message.name == "search_policies"
    )
    escalated = final in escalation_texts and not tool_calls

    return {"final": final, "tool_calls": tool_calls, "retrieved": retrieved,
            "escalated": escalated, "pending": pending, "error": None,
            "search_queries": search_queries}


# ------------------------------------------------------------------
# optional LLM judge (correctness + groundedness)
# ------------------------------------------------------------------
JUDGE_PROMPT = """You are grading a company onboarding assistant.

Question: {question}
Reference answer: {reference}
Retrieved context:
{context}
Assistant answer: {answer}

Return JSON only, no other text:
{{"correct": true or false, "grounded": true or false, "reason": "one short sentence"}}

correct = the answer agrees with the reference and states nothing that contradicts it.
grounded = every factual claim in the answer is supported by the retrieved context."""


def judge_case(case: dict, raw: dict) -> dict | None:
    if case["category"] not in ANSWER_CATEGORIES or raw.get("error") or not raw.get("final"):
        return None
    from langchain_groq import ChatGroq

    import backend

    # For less self-grading bias, set EVAL_JUDGE_MODEL to a different model than the agent.
    model = os.getenv("EVAL_JUDGE_MODEL") or getattr(backend.llm, "model_name", "openai/gpt-oss-120b")
    judge = ChatGroq(model=model, temperature=0)
    prompt = JUDGE_PROMPT.format(
        question=case["question"],
        reference=case.get("reference", ""),
        context=(raw.get("retrieved") or "(nothing retrieved)")[:4000],
        answer=raw["final"][:2000],
    )
    try:
        text = judge.invoke(prompt).content
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1])
    except Exception as error:  # noqa: BLE001
        return {"correct": False, "grounded": False, "reason": f"judge failed: {error}"}


# ------------------------------------------------------------------
# reporting
# ------------------------------------------------------------------
def print_summary(summary: dict) -> None:
    overall = summary["overall"]
    print(f"\nOVERALL: {overall['passed']}/{overall['n']} passed ({overall['pct']}%)\n")
    print(f"{'category':<22}{'passed':>8}{'n':>5}{'pct':>8}")
    for category, stats in sorted(summary["by_category"].items()):
        print(f"{category:<22}{stats['passed']:>8}{stats['n']:>5}{stats['pct']:>7}%")
    if summary["secondary"]:
        print("\nsecondary metrics")
        for name, stats in summary["secondary"].items():
            print(f"  {name:<26}{stats['pct']:>6}%  (n={stats['n']})")


def write_reports(label: str, config: dict, summary: dict, results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = RESULTS_DIR / f"{stamp}_{label}"

    base.with_suffix(".json").write_text(
        json.dumps({"label": label, "config": config, "summary": summary, "results": results},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [f"# Eval run: {label}", "", f"Overall: {summary['overall']['passed']}/{summary['overall']['n']} "
             f"({summary['overall']['pct']}%)", "", "## Config", ""]
    lines += [f"- {key}: {value}" for key, value in config.items()]
    lines += ["", "## By category", "", "| Category | Passed | N | % |", "|---|---|---|---|"]
    for category, stats in sorted(summary["by_category"].items()):
        lines.append(f"| {category} | {stats['passed']} | {stats['n']} | {stats['pct']} |")
    if summary["secondary"]:
        lines += ["", "## Secondary metrics", "", "| Metric | % | N |", "|---|---|---|"]
        for name, stats in summary["secondary"].items():
            lines.append(f"| {name} | {stats['pct']} | {stats['n']} |")
    failures = [r for r in results if not r["score"]["passed"]]
    lines += ["", f"## Failures ({len(failures)})", ""]
    for item in failures:
        case, raw = item["case"], item["raw"]
        lines += [
            f"### {case['id']} ({case['category']}, role: {case.get('role', '-')})",
            f"- Question: {case['question']}",
            f"- Expected: {case.get('reference', '')}",
            f"- Why it failed: {', '.join(item['score']['reasons'])}",
            f"- Tools used: {raw.get('tool_calls')}",
            f"- Answer: {(raw.get('final') or '(none)')[:400]}",
            "",
        ]
    base.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    return base


def rescore_run(path: str) -> None:
    """Re-apply the CURRENT scoring.py and questions.json to a saved run. No model calls."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    current = {}
    for question_file in (QUESTIONS_PATH, HARD_PATH):
        if question_file.exists():
            current.update({c["id"]: c for c in json.loads(question_file.read_text(encoding="utf-8"))})
    results = []
    for item in data["results"]:
        case = current.get(item["case"]["id"], item["case"])
        entry = {"case": case, "raw": item["raw"], "score": score_case(case, item["raw"])}
        if item.get("judge"):
            entry["judge"] = item["judge"]
        results.append(entry)

    old = {r["case"]["id"]: r["score"]["passed"] for r in data["results"]}
    changed = [r["case"]["id"] for r in results if old.get(r["case"]["id"]) != r["score"]["passed"]]
    summary = summarize(results)
    print_summary(summary)
    print("\ncases whose verdict changed:", changed or "none")
    base = write_reports(f"{data['label']}-rescored", data["config"], summary, results)
    print(f"\nSaved: {base.with_suffix('.md')}\n       {base.with_suffix('.json')}")


def compare_runs(path_a: str, path_b: str) -> None:
    a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (path_a, path_b))
    print(f"A: {a['label']}   B: {b['label']}\n")
    changed = {k: (a["config"].get(k), b["config"].get(k)) for k in a["config"]
               if a["config"].get(k) != b["config"].get(k)}
    print("config changes:", changed or "none", "\n")
    print(f"{'category':<22}{'A %':>8}{'B %':>8}{'delta':>8}")
    for category in sorted(set(a["summary"]["by_category"]) | set(b["summary"]["by_category"])):
        pa = a["summary"]["by_category"].get(category, {}).get("pct", 0)
        pb = b["summary"]["by_category"].get(category, {}).get("pct", 0)
        print(f"{category:<22}{pa:>8}{pb:>8}{pb - pa:>+8.1f}")
    oa, ob = a["summary"]["overall"]["pct"], b["summary"]["overall"]["pct"]
    print(f"{'OVERALL':<22}{oa:>8}{ob:>8}{ob - oa:>+8.1f}")
    passed_a = {r["case"]["id"]: r["score"]["passed"] for r in a["results"]}
    passed_b = {r["case"]["id"]: r["score"]["passed"] for r in b["results"]}
    shared = sorted(set(passed_a) & set(passed_b))
    fixed = [i for i in shared if passed_b[i] and not passed_a[i]]
    broke = [i for i in shared if passed_a[i] and not passed_b[i]]
    print("\nnewly passing:", fixed or "none")
    print("newly failing:", broke or "none")


# ------------------------------------------------------------------
# LangSmith experiment
# Needs: pip install -U "langsmith>=0.3.13"
#        LANGSMITH_API_KEY in .env (and LANGSMITH_TRACING=true to see full agent traces)
# ------------------------------------------------------------------
LS_INPUT_KEYS = {"id", "category", "question", "role"}


def langsmith_scores(inputs: dict, outputs: dict, reference_outputs: dict) -> list[dict]:
    """One evaluator, many scores: 'passed' plus every check that applies to this case."""
    case = {**inputs, **(reference_outputs or {})}
    result = score_case(case, outputs)
    scores = [{"key": "passed", "score": int(result["passed"])}]
    scores += [{"key": f"check_{name}", "score": int(ok)} for name, ok in result["checks"].items()]
    return scores


def _langsmith_example(case: dict) -> dict:
    return {
        "inputs": {k: case[k] for k in LS_INPUT_KEYS if k in case},
        "outputs": {k: v for k, v in case.items() if k not in LS_INPUT_KEYS},
        "metadata": {"category": case["category"], "case_id": case["id"]},
    }


def sync_langsmith_dataset(client, dataset_name: str):
    """Ensure the LangSmith dataset contains every case from both local question sets."""
    all_cases = []
    for path in (QUESTIONS_PATH, HARD_PATH):
        all_cases.extend(json.loads(path.read_text(encoding="utf-8")))

    case_ids = [case["id"] for case in all_cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Question IDs must be unique across questions.json and questions_hard.json.")

    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(dataset_name=dataset_name, description="Onboarding assistant eval set")

    existing_ids = {
        example.inputs.get("id")
        for example in client.list_examples(dataset_id=dataset.id)
    }
    new_cases = [case for case in all_cases if case["id"] not in existing_ids]
    if new_cases:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[_langsmith_example(case) for case in new_cases],
        )
    print(f"LangSmith dataset '{dataset_name}': {len(existing_ids)} existing examples, "
          f"uploaded {len(new_cases)} missing current cases ({len(all_cases)} current cases).")
    return dataset


def run_langsmith(cases: list[dict], label: str, dataset_name: str, config: dict) -> None:
    from langsmith import Client

    client = Client()
    dataset = sync_langsmith_dataset(client, dataset_name)

    def target(inputs: dict) -> dict:  # the argument must be named "inputs"
        return execute_case(inputs)

    # Run only the selected cases (if --category/--limit were used), not the whole dataset.
    selected_ids = {c["id"] for c in cases}
    examples = [e for e in client.list_examples(dataset_id=dataset.id)
                if e.inputs.get("id") in selected_ids]
    matched_ids = {example.inputs.get("id") for example in examples}
    missing_ids = selected_ids - matched_ids
    if missing_ids:
        raise RuntimeError(
            f"LangSmith dataset '{dataset_name}' is missing selected case IDs: "
            f"{', '.join(sorted(missing_ids))}"
        )

    client.evaluate(
        target,
        data=examples,
        evaluators=[langsmith_scores],
        experiment_prefix=label,
        max_concurrency=1,
        metadata=config,
    )
    print(f"LangSmith experiment '{label}' submitted ({len(examples)} cases). "
          "Open Datasets & Experiments in LangSmith to compare runs.")


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Onboarding assistant evals")
    parser.add_argument("--set", dest="question_set", choices=["core", "hard", "all"], default="core",
                        help="core = 70 core cases (default), hard = 20 harder cases, all = both")
    parser.add_argument("--category", help="comma-separated categories to run")
    parser.add_argument("--limit", type=int, help="run only the first N matching cases")
    parser.add_argument("--label", default="run", help="name for this run, e.g. baseline or bigger-chunks")
    parser.add_argument("--judge", action="store_true", help="add LLM-judged correctness and groundedness")
    parser.add_argument("--sleep", type=float, default=1.5, help="seconds between cases (rate limits)")
    parser.add_argument("--langsmith", action="store_true", help="also upload dataset and run a LangSmith experiment")
    parser.add_argument("--dataset", default="onboarding-evals", help="LangSmith dataset name")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two saved result files")
    parser.add_argument("--rescore", metavar="FILE", help="re-grade a saved run with the current scoring.py (no model calls)")
    args = parser.parse_args()

    if args.rescore:
        rescore_run(args.rescore)
        return

    if args.compare:
        compare_runs(*args.compare)
        return

    paths = {"core": [QUESTIONS_PATH], "hard": [HARD_PATH], "all": [QUESTIONS_PATH, HARD_PATH]}[args.question_set]
    cases = []
    for path in paths:
        cases += json.loads(path.read_text(encoding="utf-8"))
    if args.category:
        wanted = {c.strip() for c in args.category.split(",")}
        cases = [c for c in cases if c["category"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        sys.exit("No cases selected.")

    config = config_snapshot()
    print(f"Running {len(cases)} cases with {config['llm']} (min_relevance={config['min_relevance']}) ...")

    if args.langsmith:
        run_langsmith(cases, args.label, args.dataset, config)
        return

    results = []
    stopped_early = False
    for index, case in enumerate(cases, start=1):
        try:
            raw = execute_case(case)
        except DailyLimitReached as error:
            print(f"\nSTOPPED: daily quota reached after {len(results)} of {len(cases)} cases.")
            print(f"Provider said: {str(error)[:300]}")
            print("Wait for the quota to reset (or check your Groq limits page), then re-run the rest "
                  "with --category or --limit.")
            stopped_early = True
            break
        score = score_case(case, raw)
        item = {"case": case, "raw": raw, "score": score}
        if args.judge:
            item["judge"] = judge_case(case, raw)
        results.append(item)
        status = "PASS" if score["passed"] else "FAIL"
        extra = "" if score["passed"] else f"  <- {', '.join(score['reasons'])}"
        print(f"[{index:>3}/{len(cases)}] {status} {case['id']:<5} {case['category']:<20}{extra}")
        time.sleep(args.sleep)

    if not results:
        sys.exit("No cases completed, nothing to report.")
    summary = summarize(results)
    print_summary(summary)
    label = f"{args.label}-PARTIAL" if stopped_early else args.label
    base = write_reports(label, config, summary, results)
    print(f"\nSaved: {base.with_suffix('.md')}\n       {base.with_suffix('.json')}")


if __name__ == "__main__":
    main()