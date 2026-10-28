"""Find out why LangSmith shows no datasets.   Run from chatbot_with_ui:

    python evals/check_langsmith.py

It prints which endpoint, key and workspace the SDK is really using (key is masked), then tries to
list your datasets and projects, and to create and delete a throwaway dataset. Paste the output
back if something fails.
"""

import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_ENDPOINT = "https://api.smith.langchain.com"


def mask(value):
    return f"set (ends with ...{value[-4:]})" if value else "NOT SET"


def main():
    endpoint = os.getenv("LANGSMITH_ENDPOINT") or DEFAULT_ENDPOINT
    print("--- environment ---")
    print(f"LANGSMITH_API_KEY      : {mask(os.getenv('LANGSMITH_API_KEY'))}")
    print(f"LANGSMITH_ENDPOINT     : {os.getenv('LANGSMITH_ENDPOINT') or '(not set, using US default)'}")
    print(f"endpoint in use        : {endpoint}")
    print(f"LANGSMITH_WORKSPACE_ID : {os.getenv('LANGSMITH_WORKSPACE_ID') or '(not set)'}")
    print(f"LANGSMITH_TRACING      : {os.getenv('LANGSMITH_TRACING') or os.getenv('LANGCHAIN_TRACING_V2') or '(not set)'}")

    if not os.getenv("LANGSMITH_API_KEY"):
        sys.exit("\nNo API key found. Add LANGSMITH_API_KEY to your .env (same folder level you use for GROQ_API_KEY).")

    try:
        from langsmith import Client
    except ImportError:
        sys.exit('\nlangsmith is not installed. Run: pip install -U "langsmith>=0.3.13"')

    client = Client()
    print(f"\nclient api_url         : {getattr(client, 'api_url', '?')}")

    print("\n--- read access ---")
    try:
        datasets = list(client.list_datasets(limit=10))
        print(f"datasets visible to this key: {len(datasets)}")
        for dataset in datasets:
            print(f"  - {dataset.name}")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED to list datasets: {type(error).__name__}: {str(error)[:300]}")

    try:
        projects = list(client.list_projects(limit=8))
        print(f"projects visible (experiments and traces show up here): {len(projects)}")
        for project in projects:
            print(f"  - {project.name}")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED to list projects: {type(error).__name__}: {str(error)[:300]}")

    print("\n--- write access ---")
    name = f"connection-test-{uuid.uuid4().hex[:6]}"
    try:
        dataset = client.create_dataset(dataset_name=name, description="temporary, safe to delete")
        print(f"created dataset '{name}'  -> check the LangSmith UI now; it should appear")
        client.delete_dataset(dataset_id=dataset.id)
        print("deleted it again")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED to create a dataset: {type(error).__name__}: {str(error)[:300]}")

    print("\nIf the lists above are empty or errors appear, the usual causes are:")
    print("  1. Your account is in the EU (or another) region but LANGSMITH_ENDPOINT is not set.")
    print("  2. The key is scoped to an organization and needs LANGSMITH_WORKSPACE_ID.")
    print("  3. The web app is showing a different workspace than the one the key belongs to.")


if __name__ == "__main__":
    main()
