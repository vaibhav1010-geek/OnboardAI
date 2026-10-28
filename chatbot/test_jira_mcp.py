
import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient


# Load environment variables from .env in the current directory.
load_dotenv()

# Test ticket details
TEST_SUMMARY = "Test ticket from onboarding chatbot"
TEST_DESCRIPTION = (
    "This is a test issue created through the onboarding "
    "assistant using the Atlassian MCP integration."
)


def validate_config():
    """Check that the required Jira configuration exists."""
    required_vars = [
        "JIRA_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_PROJECT_KEY",
    ]

    missing = [
        name for name in required_vars
        if not os.getenv(name, "").strip()
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables in .env: "
            + ", ".join(missing)
        )


async def main():
    validate_config()

    jira_url = os.environ["JIRA_URL"].rstrip("/")
    project_key = os.environ["JIRA_PROJECT_KEY"].strip()

    command = os.getenv("JIRA_MCP_COMMAND", "uvx")
    args = os.getenv("JIRA_MCP_ARGS", "mcp-atlassian").split()

    print("Connecting to Jira MCP server...")
    print(f"Jira URL: {jira_url}")
    print(f"Project key: {project_key}")

    client = MultiServerMCPClient(
        {
            "jira": {
                "transport": "stdio",
                "command": command,
                "args": args,
                "env": {
                    "JIRA_URL": jira_url,
                    "JIRA_USERNAME": os.environ["JIRA_EMAIL"],
                    "JIRA_API_TOKEN": os.environ["JIRA_API_TOKEN"],
                },
            }
        }
    )

    # Discover the tools exposed by the MCP server.
    tools = await client.get_tools()

    print(f"\nDiscovered {len(tools)} Jira MCP tools.")

    for tool in tools:
        print(f"- {tool.name}")

    # Find the issue-creation tool.
    create_tool = next(
        (
            tool for tool in tools
            if tool.name.endswith("jira_create_issue")
        ),
        None,
    )

    if create_tool is None:
        raise RuntimeError(
            "The Jira MCP server did not expose jira_create_issue."
        )

    print("\nIssue-creation tool found.")
    print(f"Accepted arguments: {list(create_tool.args.keys())}")

    # Build arguments supported by the discovered tool.
    wanted_arguments = {
        "project_key": project_key,
        "summary": TEST_SUMMARY,
        "issue_type": os.getenv("JIRA_ISSUE_TYPE", "Task"),
        "description": TEST_DESCRIPTION,
    }

    accepted_arguments = set(create_tool.args.keys())

    arguments = {
        key: value
        for key, value in wanted_arguments.items()
        if key in accepted_arguments
    }

    required_arguments = {
        "project_key",
        "summary",
        "issue_type",
    }

    missing_arguments = required_arguments - set(arguments)

    if missing_arguments:
        raise RuntimeError(
            "The MCP tool does not accept required arguments: "
            + ", ".join(sorted(missing_arguments))
        )

    # This call creates a REAL Jira issue.
    # Run this test only once to avoid creating duplicate tickets.
    print("\nCreating Jira issue...")
    print(f"Summary: {TEST_SUMMARY}")

    result = await create_tool.ainvoke(arguments)

    print("\nMCP creation response:")
    print(result)

    # Do not report success unless the tool returned without an error.
    print("\nThe MCP tool returned a response.")
    print("Verify the issue in Jira before running this test again.")
    print(f"Open your Jira site: {jira_url}")

    if isinstance(result, dict):
        issue_key = result.get("key") or result.get("issue_key")

        if issue_key:
            print(f"Issue key: {issue_key}")
            print(f"Issue URL: {jira_url}/browse/{issue_key}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}")
        print(
            "\nIf the request may have reached Jira, "
            "check your project before retrying."
        )
        sys.exit(1)
