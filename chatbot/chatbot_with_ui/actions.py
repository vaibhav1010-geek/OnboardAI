"""Things the onboarding agent can DO (as opposed to answer).

- Tool catalog + eligibility rules (who may request what)
- Access-request tickets: created in Jira through an MCP server (mcp-atlassian) if
  configured, otherwise saved to a local log
- Audit log of every question, escalation and action (feeds your metrics later)
"""

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "onboarding_actions.db"

COMPANY_NAME = os.getenv("COMPANY_NAME", "Acme Demo Co")
HR_CONTACT = "people@acmedemo.example (Slack: #ask-hr)"
IT_CONTACT = "it-help@acmedemo.example (Slack: #it-help)"
ETHICS_CONTACT = "ethics@acmedemo.example (confidential)"

ROLES = ["Engineering", "Sales", "Design", "HR", "Other"]

# Keep this in sync with docs/tool_access_matrix.md
TOOL_CATALOG = {
    "github": {
        "label": "GitHub",
        "aliases": ["github", "git hub", "gh", "source code"],
        "roles": ["Engineering"],
        "approver": "Engineering manager",
        "turnaround": "1 business day",
    },
    "aws": {
        "label": "AWS Console",
        "aliases": ["aws", "aws console", "amazon web services"],
        "roles": ["Engineering"],
        "approver": "Engineering manager and Security team",
        "turnaround": "3 business days",
        "note": "Requires the security awareness training to be completed first.",
    },
    "jira": {
        "label": "Jira",
        "aliases": ["jira", "atlassian"],
        "roles": ["Engineering", "Design"],
        "approver": "Team lead",
        "turnaround": "1 business day",
    },
    "figma": {
        "label": "Figma",
        "aliases": ["figma"],
        "roles": ["Design", "Engineering"],
        "approver": "Design lead",
        "turnaround": "1 business day",
    },
    "salesforce": {
        "label": "Salesforce",
        "aliases": ["salesforce", "sfdc", "crm"],
        "roles": ["Sales"],
        "approver": "Sales manager",
        "turnaround": "2 business days",
    },
    "vpn": {
        "label": "VPN",
        "aliases": ["vpn", "acme secure connect", "secure connect"],
        "roles": ROLES,  # everyone
        "approver": "IT Team",
        "turnaround": "1 business day",
    },
}

AUTO_PROVISIONED = ["company email", "Slack", "Google Workspace", "1Password"]


# ------------------------------------------------------------------
# database helpers
# ------------------------------------------------------------------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT UNIQUE,
            thread_id TEXT, role TEXT, tool TEXT, justification TEXT,
            ticket_key TEXT, ticket_url TEXT, mode TEXT, created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, thread_id TEXT, kind TEXT, detail TEXT
        )"""
    )
    return conn


def audit(kind: str, detail: dict, thread_id: str | None = None) -> None:
    """Record an event. Never lets logging break the chat."""
    if os.getenv("ONBOARDING_EVAL"):  # eval runs must not pollute real analytics
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, thread_id, kind, detail) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), thread_id, kind, json.dumps(detail)),
            )
    except Exception:
        pass


# ------------------------------------------------------------------
# tool catalog and eligibility
# ------------------------------------------------------------------
def resolve_tool(name: str) -> str | None:
    """Map free text like 'git hub' or 'AWS' to a catalog key."""
    text = (name or "").strip().lower()
    if not text:
        return None
    for key, info in TOOL_CATALOG.items():
        if text == key or text in info["aliases"]:
            return key
    for key, info in TOOL_CATALOG.items():
        if any(alias in text for alias in info["aliases"]):
            return key
    return None


def list_requestable_tools() -> str:
    return ", ".join(info["label"] for info in TOOL_CATALOG.values())


def check_eligibility(tool_key: str, role: str) -> tuple[bool, str]:
    info = TOOL_CATALOG[tool_key]
    if role in info["roles"]:
        return True, ""
    allowed = ", ".join(info["roles"])
    return False, (
        f"{info['label']} access is only available to these roles: {allowed}. "
        f"The user's role is {role}. No request was created. Tell the user to ask their "
        f"manager to raise the request for them if they really need it."
    )


def build_ticket_preview(tool_key: str, role: str, justification: str) -> dict:
    info = TOOL_CATALOG[tool_key]
    return {
        "type": "access_request",
        "tool_key": tool_key,
        "tool": info["label"],
        "role": role,
        "approver": info["approver"],
        "turnaround": info["turnaround"],
        "note": info.get("note", ""),
        "summary": f"Access request: {info['label']} for new joiner ({role})",
        "justification": justification,
    }


# ------------------------------------------------------------------
# ticket creation
# ------------------------------------------------------------------
def jira_configured() -> bool:
    return all(
        os.getenv(var)
        for var in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY")
    )


# ---- Jira through MCP -------------------------------------------------
# Streamlit code is synchronous but MCP clients are async. One background event
# loop (created once per process) runs all MCP calls, and sync code waits on it.
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()
_mcp_client = None
_create_tool = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True).start()
        return _loop


def _run_async(coro, timeout: int = 120):
    # The first call can be slow: uvx may download the MCP server on first use.
    return asyncio.run_coroutine_threadsafe(coro, _get_loop()).result(timeout=timeout)


def _get_client():
    global _mcp_client
    if _mcp_client is None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        _mcp_client = MultiServerMCPClient(
            {
                "jira": {
                    "transport": "stdio",
                    "command": os.getenv("JIRA_MCP_COMMAND", "uvx"),
                    "args": os.getenv("JIRA_MCP_ARGS", "mcp-atlassian").split(),
                    "env": {
                        "JIRA_URL": os.environ["JIRA_BASE_URL"],
                        "JIRA_USERNAME": os.environ["JIRA_EMAIL"],
                        "JIRA_API_TOKEN": os.environ["JIRA_API_TOKEN"],
                    },
                }
            }
        )
    return _mcp_client


async def _get_create_tool():
    global _create_tool
    if _create_tool is None:
        tools = await _get_client().get_tools()
        _create_tool = next((t for t in tools if t.name.endswith("jira_create_issue")), None)
        if _create_tool is None:
            names = ", ".join(t.name for t in tools) or "none"
            raise RuntimeError(f"The Jira MCP server has no jira_create_issue tool (found: {names})")
    return _create_tool


def _accepted_args(tool) -> set[str] | None:
    """Argument names the tool declares, so we only send ones it understands."""
    try:
        return set(tool.args.keys())
    except Exception:
        return None


def _extract_issue_key(result, project_key: str) -> str | None:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    match = re.search(rf"\b({re.escape(project_key)}-\d+)\b", text)
    return match.group(1) if match else None


async def _create_issue_async(summary: str, description: str) -> tuple[str, str]:
    project_key = os.environ["JIRA_PROJECT_KEY"]
    tool = await _get_create_tool()

    wanted = {
        "project_key": project_key,
        "summary": summary,
        "issue_type": os.getenv("JIRA_ISSUE_TYPE", "Task"),
        "description": description,
    }
    accepted = _accepted_args(tool)
    arguments = {k: v for k, v in wanted.items() if accepted is None or k in accepted}

    result = await tool.ainvoke(arguments)

    key = _extract_issue_key(result, project_key)
    if not key:
        raise RuntimeError(
            "The Jira MCP call finished but no issue key was found in its reply. "
            "The issue may have been created, so check the Jira board before retrying. "
            f"Reply was: {str(result)[:200]}"
        )
    return key, f"{os.environ['JIRA_BASE_URL'].rstrip('/')}/browse/{key}"


def _create_jira_issue(summary: str, description: str) -> tuple[str, str]:
    return _run_async(_create_issue_async(summary, description))


def create_access_ticket(thread_id: str, role: str, tool_key: str, justification: str) -> dict:
    """Create the ticket once. A repeat call with the same details returns the original."""
    info = TOOL_CATALOG[tool_key]
    justification = justification.strip()
    dedupe_key = hashlib.sha256(
        f"{thread_id}|{tool_key}|{justification.lower()}".encode()
    ).hexdigest()

    with _connect() as conn:
        existing = conn.execute(
            "SELECT ticket_key, ticket_url, mode FROM access_requests WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if existing:
            return {"key": existing[0], "url": existing[1], "mode": existing[2], "duplicate": True}

    summary = f"Access request: {info['label']} for new joiner ({role})"
    description = (
        f"Tool: {info['label']}\nRequester role: {role}\n"
        f"Approver: {info['approver']}\nReason: {justification}\n"
        f"Created by the onboarding assistant after the employee confirmed the request."
    )

    if jira_configured():
        key, url = _create_jira_issue(summary, description)
        mode = "jira"
    else:
        mode = "local"
        key = url = ""

    with _connect() as conn:
        cursor = conn.execute(
            """INSERT INTO access_requests
               (dedupe_key, thread_id, role, tool, justification, ticket_key, ticket_url, mode, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dedupe_key, thread_id, role, tool_key, justification, key, url, mode,
             datetime.now(timezone.utc).isoformat()),
        )
        if mode == "local":
            key = f"LOCAL-{cursor.lastrowid}"
            conn.execute("UPDATE access_requests SET ticket_key = ? WHERE id = ?", (key, cursor.lastrowid))

    return {"key": key, "url": url, "mode": mode, "duplicate": False}