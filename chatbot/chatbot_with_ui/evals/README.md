# Evals

70 core questions in questions.json (the fixed ruler) plus 20 harder ones in questions_hard.json. Run from the chatbot_with_ui folder.

    python evals/run_evals.py --label baseline
    python evals/run_evals.py --limit 10 --label smoke      # quick check first
    python evals/run_evals.py --judge --label baseline-judged
    python evals/run_evals.py --langsmith --label baseline  # optional: dataset + experiment in LangSmith
    python evals/run_evals.py --set all --langsmith --label full-baseline  # all 90 current cases in LangSmith
    python evals/run_evals.py --compare evals/results/<a>.json evals/results/<b>.json

Each run writes a .md report (with failures) and a .json file to evals/results/.
Change ONE thing between runs (threshold, chunk size, top_k, prompt), re-run, then --compare.

Case schema: id, category, question, role, expected_facts (list of groups; each group needs one
alternative present), expected_sources, stale_values, expected_tool, reference.

## LangSmith
    pip install -U "langsmith>=0.3.13"
    # .env: LANGSMITH_API_KEY=...   LANGSMITH_TRACING=true
    python evals/run_evals.py --langsmith --label baseline

The dataset "onboarding-evals" (change with --dataset) is synced with missing cases from both
questions.json and questions_hard.json (70 core + 20 hard). Existing datasets are supplemented
without duplicating examples, then the experiment runs only the selected set. Use `--set all` to
evaluate all 90 current cases; `--set core` and `--set hard` run only their respective cases. The
sync is additive: removed cases already in LangSmith remain in the dataset, but are not selected
unless they are present in the current local question files. Each case gets scores named "passed"
and "check_<name>". Compare experiments side by side in LangSmith. If you edit an existing case,
delete and recreate the dataset (or use a new `--dataset` name) to upload its updated inputs and
reference outputs.

## Harder set
    python evals/run_evals.py --set hard --label hard-run1
    python evals/run_evals.py --set hard --label hard-run2     # run twice: failing both times = real, once = flaky
    python evals/run_evals.py --set all --label full           # core + hard together, local

Never edit the core set to make a score look better; add new cases to questions_hard.json instead.