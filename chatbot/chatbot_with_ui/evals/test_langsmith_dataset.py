"""Offline tests for syncing core and hard cases to a LangSmith dataset."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_evals import HARD_PATH, QUESTIONS_PATH, sync_langsmith_dataset  # noqa: E402


class FakeLangSmithClient:
    def __init__(self, existing_cases=()):
        self.dataset = None
        self.examples = []
        if existing_cases:
            self.dataset = SimpleNamespace(id="existing-dataset", name="onboarding-evals")
            self.examples = [
                SimpleNamespace(inputs={"id": case["id"]})
                for case in existing_cases
            ]
        self.created_examples = []

    def has_dataset(self, dataset_name):
        return self.dataset is not None and self.dataset.name == dataset_name

    def create_dataset(self, dataset_name, description):
        self.dataset = SimpleNamespace(id="new-dataset", name=dataset_name)
        return self.dataset

    def read_dataset(self, dataset_name):
        assert self.dataset.name == dataset_name
        return self.dataset

    def list_examples(self, dataset_id):
        assert self.dataset.id == dataset_id
        return self.examples

    def create_examples(self, dataset_id, examples):
        assert self.dataset.id == dataset_id
        self.created_examples.extend(examples)
        self.examples.extend(
            SimpleNamespace(inputs=example["inputs"])
            for example in examples
        )


def all_cases():
    cases = []
    for path in (QUESTIONS_PATH, HARD_PATH):
        cases.extend(json.loads(path.read_text(encoding="utf-8")))
    return cases


def main() -> int:
    cases = all_cases()
    core_cases = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if len(core_cases) != 70 or len(cases) != 90:
        raise AssertionError(
            f"Expected 70 core and 90 total cases, found {len(core_cases)} and {len(cases)}"
        )

    client = FakeLangSmithClient()
    sync_langsmith_dataset(client, "onboarding-evals")
    if len(client.created_examples) != 90:
        raise AssertionError(f"New dataset upload created {len(client.created_examples)} cases")

    # Re-syncing must not duplicate any case.
    sync_langsmith_dataset(client, "onboarding-evals")
    if len(client.created_examples) != 90:
        raise AssertionError("Re-sync duplicated already-uploaded examples")

    # A legacy dataset with the old core set retains removed A02/D03, adding only hard cases.
    existing_client = FakeLangSmithClient(core_cases + [{"id": "A02"}, {"id": "D03"}])
    sync_langsmith_dataset(existing_client, "onboarding-evals")
    if len(existing_client.created_examples) != 20:
        raise AssertionError(
            f"Expected 20 missing hard cases to upload, got {len(existing_client.created_examples)}"
        )
    print("LangSmith dataset sync tests passed (90 initial, idempotent, legacy +20 hard cases).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
