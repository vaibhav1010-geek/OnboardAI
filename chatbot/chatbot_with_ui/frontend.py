import uuid

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

import actions
import rag
from backend import (
    chatbot,
    format_thread_title,
    get_pending_approval,
    retrieve_all_threads,
    retrieve_thread_title,
)

load_dotenv()

APP_NAME = "Onboarding Assistant"
EMPTY_STATE_TITLE = f"Welcome to {actions.COMPANY_NAME} 👋"
EMPTY_STATE_HINT = "Ask about leave, benefits, IT setup, or request access to a tool."

# (material icon, prompt shown on the card and sent when clicked)
SUGGESTIONS = [
    (":material/vpn_lock:", "How do I set up the VPN?"),
    (":material/event_available:", "How many leave days do I get and how do I apply?"),
    (":material/key:", "I need GitHub access for my first project"),
]

TYPING_HTML = '<div class="typing"><span></span><span></span><span></span></div>'

st.set_page_config(
    page_title=APP_NAME,
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="expanded",
)


# ============================= themes ==================================
# Every colour used by the CSS comes from one of these palettes.
# To add a theme, add a palette here (the toggle switches between the
# first two entries). Base Streamlit colours in .streamlit/config.toml
# should match the default (light) palette.

PALETTES = {
    "light": {
        "bg": "#FFFFFF",
        "surface": "#F7F7F5",          # sidebar, code blocks
        "surface-strong": "#EFEFEC",   # hover rows, user bubble
        "input-bg": "#FFFFFF",
        "ink": "#1A1A1A",
        "muted": "#6B6B66",
        "border": "#E6E5E1",
        "border-strong": "#D4D3CE",
        "accent": "#17695E",
        "accent-soft": "rgba(23, 105, 94, 0.14)",
        "accent-fg": "#FFFFFF",        # text/icon colour on top of accent
        "btn-bg": "#1A1A1A",           # solid "New chat" button
        "btn-fg": "#FFFFFF",
        "btn-hover": "#333333",
        "shadow": "rgba(0, 0, 0, 0.06)",
    },
    "dark": {
        "bg": "#0E1117",
        "surface": "#161922",
        "surface-strong": "#262730",
        "input-bg": "#161922",
        "ink": "#FAFAFA",
        "muted": "#9AA0AE",
        "border": "#2E303B",
        "border-strong": "#3D404D",
        "accent": "#F28C38",
        "accent-soft": "rgba(242, 140, 56, 0.20)",
        "accent-fg": "#0E1117",
        "btn-bg": "#FAFAFA",
        "btn-fg": "#0E1117",
        "btn-hover": "#D9D9D9",
        "shadow": "rgba(0, 0, 0, 0.45)",
    },
}
DEFAULT_THEME = "light"


def theme_css(name):
    variables = "\n".join(f"--{key}: {value};" for key, value in PALETTES[name].items())
    return f"<style>:root {{ {variables} color-scheme: {name}; }}</style>"


# ============================ styling ==================================
STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap');

:root {
    --font-sans: 'Geist', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* ---- typography ---- */
.stApp, .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp textarea, .stApp input,
[data-testid="stMarkdownContainer"] {
    font-family: var(--font-sans) !important;
}
code, pre, [data-testid="stCode"] * { font-family: var(--font-mono) !important; }

/* ---- base surfaces and text (drive Streamlit's own elements from the palette) ---- */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: var(--bg);
    color: var(--ink);
}
.stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp label, .stApp td, .stApp th {
    color: var(--ink);
}
.stApp a { color: var(--accent); }
[data-testid="stIconMaterial"] { color: inherit; }
header[data-testid="stHeader"] { background: transparent; }
header[data-testid="stHeader"] button,
header[data-testid="stHeader"] svg,
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapsedControl"] button { color: var(--ink); }
footer, [data-testid="stDecoration"] { display: none; }

.block-container {
    max-width: 47rem;
    padding-top: 2rem;
    padding-bottom: 7rem;
}
* { scrollbar-width: thin; scrollbar-color: var(--border-strong) transparent; }

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {
    background: var(--surface);
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding: 1.25rem 0.5rem 4.5rem; /* bottom space keeps the theme toggle clear of the list */
}
.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    color: var(--ink);
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin: 0 0 1.25rem 0.35rem;
}
.sidebar-brand .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 8px;
    background: var(--btn-bg);
    color: var(--btn-fg);
    font-size: 0.8rem;
    font-weight: 600;
}
.sidebar-section {
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--muted);
    margin: 1.6rem 0 0.4rem 0.6rem;
}

/* New chat: the one solid element in the sidebar */
.st-key-new_chat button {
    width: 100%;
    justify-content: flex-start;
    gap: 0.4rem;
    padding: 0.6rem 0.85rem;
    border: none;
    border-radius: 10px;
    background: var(--btn-bg);
    color: var(--btn-fg);
    font-weight: 500;
    transition: background 0.15s ease;
}
.st-key-new_chat button p,
.st-key-new_chat button span { color: var(--btn-fg); }
.st-key-new_chat button:hover { background: var(--btn-hover); }

/* Role picker in the sidebar */
section[data-testid="stSidebar"] [data-testid="stSelectbox"] label p {
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 500;
}
[data-baseweb="select"] > div {
    background: var(--input-bg);
    border-color: var(--border);
    border-radius: 10px;
}
[data-baseweb="select"] * { color: var(--ink); }
[data-baseweb="popover"] ul,
[data-baseweb="popover"] [role="listbox"] { background: var(--bg); }
[data-baseweb="popover"] li { color: var(--ink); }
[data-baseweb="popover"] li:hover { background: var(--surface-strong); }

/* Re-index button: quiet text row */
.st-key-reindex button {
    width: 100%;
    justify-content: flex-start;
    gap: 0.4rem;
    border: none;
    border-radius: 8px;
    padding: 0.45rem 0.7rem;
    background: transparent;
    color: var(--muted);
    font-size: 0.85rem;
    font-weight: 400;
}
.st-key-reindex button p { color: var(--muted); font-size: 0.85rem; }
.st-key-reindex button:hover { background: var(--surface-strong); }

/* Conversation list: flat rows, left aligned, truncated */
[class*="st-key-thread-"] button {
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 0.7rem;
    background: transparent;
    color: var(--ink);
    font-weight: 400;
    transition: background 0.15s ease;
}
[class*="st-key-thread-"] button p {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.9rem;
    color: var(--ink);
}
[class*="st-key-thread-"] button:hover { background: var(--surface-strong); }
/* Active conversation is rendered as the "primary" button type */
[class*="st-key-thread-"] button[kind="primary"],
[class*="st-key-thread-"] button[kind="primary"]:hover {
    background: var(--surface-strong);
    box-shadow: inset 2px 0 0 var(--accent);
    font-weight: 500;
}

/* ---- theme toggle: pinned to the bottom-left corner ---- */
.st-key-theme_toggle {
    position: fixed !important;
    bottom: 1rem !important;
    left: 1rem !important;
    width: auto !important;
    /* Streamlit's sidebar sits at z-index ~1000000, so this must be higher
       or the button is drawn underneath it */
    z-index: 1000010 !important;
}
.st-key-theme_toggle button {
    gap: 0.45rem;
    padding: 0.45rem 0.9rem;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    background: var(--bg);
    color: var(--ink);
    font-size: 0.85rem;
    font-weight: 500;
    box-shadow: 0 2px 8px var(--shadow);
    transition: background 0.15s ease, border-color 0.15s ease;
}
.st-key-theme_toggle button p { color: var(--ink); font-size: 0.85rem; }
.st-key-theme_toggle button:hover {
    background: var(--surface-strong);
    border-color: var(--accent);
}
@media (max-width: 640px) {
    .st-key-theme_toggle { bottom: 5.5rem !important; } /* stay above the chat input on phones */
}

/* ---- messages ---- */
[data-testid="stChatMessage"] {
    background: transparent;
    padding: 0.6rem 0;
    gap: 0.75rem;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] { display: none; }

[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] li {
    font-size: 0.97rem;
    line-height: 1.7;
}
[data-testid="stChatMessageContent"] p { margin: 0 0 0.7rem; }
[data-testid="stChatMessageContent"] p:last-child { margin-bottom: 0 !important; }

/* user messages: right-aligned bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] {
    flex: 0 1 auto;
    max-width: 82%;
    background: var(--surface-strong);
    border-radius: 18px;
    padding: 0.65rem 1.1rem;
    display: flex;
    align-items: center;
}
/* remove the extra space Streamlit adds around markdown inside the bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] > div,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] {
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] p {
    margin: 0 !important;
    line-height: 1.55;
}

/* code and tables inside answers */
:not(pre) > code {
    background: var(--surface-strong);
    color: var(--ink);
    border-radius: 6px;
    padding: 0.12em 0.4em;
    font-size: 0.87em;
}
[data-testid="stCode"],
[data-testid="stCode"] pre {
    background: var(--surface) !important;
}
[data-testid="stCode"] {
    border: 1px solid var(--border);
    border-radius: 10px;
}
[data-testid="stCode"] code { color: var(--ink); }
[data-testid="stChatMessageContent"] table { font-size: 0.9rem; }
[data-testid="stChatMessageContent"] th,
[data-testid="stChatMessageContent"] td { border-color: var(--border); }
[data-testid="stChatMessageContent"] th { background: var(--surface); }

/* typing indicator shown until the first token arrives */
.typing { display: inline-flex; gap: 5px; padding: 0.7rem 0; }
.typing span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--muted);
    animation: typing-pulse 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing-pulse {
    0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
    40%           { opacity: 1;    transform: translateY(-3px); }
}
@media (prefers-reduced-motion: reduce) {
    .typing span { animation: none; opacity: 0.6; }
}

/* ---- access-request confirmation card ---- */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--border-strong);
    border-radius: 14px;
}
[data-testid="stMain"] [class*="st-key-approval-reason-"] [data-baseweb="textarea"] {
    background-color: #294A78;
    border-color: #7FA7D8;
    border-radius: 10px;
}
[data-testid="stMain"] [class*="st-key-approval-reason-"] [data-baseweb="textarea"] > div {
    background-color: #294A78;
}
[data-testid="stMain"] [class*="st-key-approval-reason-"] [data-baseweb="textarea"] textarea {
    background-color: transparent;
    color: #FFFFFF;
    -webkit-text-fill-color: #FFFFFF;
    caret-color: #FFFFFF;
}
[data-testid="stMain"] [class*="st-key-approval-reason-"] [data-baseweb="textarea"] textarea::placeholder {
    color: #FFFFFF;
    -webkit-text-fill-color: #FFFFFF;
    opacity: 1;
}
.approval-title { font-weight: 600; margin: 0 0 0.35rem; }
.approval-meta { color: var(--muted); font-size: 0.9rem; line-height: 1.6; margin: 0 0 0.75rem; }
.st-key-approval_confirm button {
    background: var(--accent);
    border: none;
    border-radius: 10px;
}
.st-key-approval_confirm button,
.st-key-approval_confirm button p { color: var(--accent-fg); }
.st-key-approval_cancel button {
    background: transparent;
    border: 1px solid var(--border-strong);
    border-radius: 10px;
}
.st-key-approval_cancel button p { color: var(--ink); }

/* ---- input ---- */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] { background: var(--bg); }
[data-testid="stChatInput"] {
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 2px 12px var(--shadow);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent);
    box-shadow: 0 2px 14px var(--accent-soft);
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: var(--ink);
    font-size: 0.97rem;
}
[data-testid="stChatInput"] textarea::placeholder { color: var(--muted); opacity: 1; }
[data-testid="stChatInputSubmitButton"] {
    background: var(--accent);
    border-radius: 10px;
}
[data-testid="stChatInputSubmitButton"],
[data-testid="stChatInputSubmitButton"] * { color: var(--accent-fg); }
[data-testid="stChatInputSubmitButton"]:disabled {
    background: var(--surface-strong);
}
[data-testid="stChatInputSubmitButton"]:disabled,
[data-testid="stChatInputSubmitButton"]:disabled * { color: var(--muted); }

/* ---- empty state ---- */
.empty-state { text-align: center; margin: 18vh 0 2rem; }
.empty-state h2 {
    font-size: 1.85rem;
    font-weight: 600;
    letter-spacing: -0.025em;
    margin: 0 0 0.4rem;
    padding: 0;
}
.empty-state p { color: var(--muted); margin: 0; }

[class*="st-key-suggest-"] { max-width: 30rem; margin: 0 auto; }
[class*="st-key-suggest-"] button {
    width: 100%;
    justify-content: flex-start;
    gap: 0.5rem;
    text-align: left;
    padding: 0.8rem 1rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--bg);
    color: var(--ink);
    font-weight: 400;
    transition: background 0.15s ease, border-color 0.15s ease;
}
[class*="st-key-suggest-"] button p { color: var(--ink); }
[class*="st-key-suggest-"] button:hover {
    background: var(--surface);
    border-color: var(--border-strong);
}
</style>
"""


def inject_styles():
    st.markdown(theme_css(st.session_state["theme"]), unsafe_allow_html=True)
    st.markdown(STYLES, unsafe_allow_html=True)


# ========================= utility functions ===========================
def generate_thread_id():
    return str(uuid.uuid4())


def add_thread(thread_id):
    thread_id = str(thread_id)
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].insert(0, thread_id)


def reset_chat():
    st.session_state["thread_id"] = generate_thread_id()
    add_thread(st.session_state["thread_id"])
    st.session_state["message_history"] = []


def load_conversation(thread_id):
    state = chatbot.get_state(config={"configurable": {"thread_id": str(thread_id)}})
    return state.values.get("messages", [])


def messages_to_history(messages):
    """Convert LangChain messages into the {'role', 'content'} dicts used by the UI.

    Tool calls and empty AI messages are skipped so only visible turns remain.
    """
    history = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            history.append({"role": "assistant", "content": msg.content})
    return history


def init_session_state():
    if "message_history" not in st.session_state:
        st.session_state["message_history"] = []
    if "thread_id" not in st.session_state:
        st.session_state["thread_id"] = generate_thread_id()
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = actions.ROLES[0]
    if "theme" not in st.session_state:
        # The theme is mirrored in the URL (?theme=dark) so it survives a page refresh.
        requested = st.query_params.get("theme", DEFAULT_THEME)
        st.session_state["theme"] = requested if requested in PALETTES else DEFAULT_THEME
    # Refresh the persistent ordering so recently active conversations come first.
    st.session_state["chat_threads"] = retrieve_all_threads()
    add_thread(st.session_state["thread_id"])


# ============================== sidebar ================================
def render_sidebar():
    with st.sidebar:
        st.markdown(
            f'<div class="sidebar-brand"><span class="mark">O</span>{APP_NAME}</div>',
            unsafe_allow_html=True,
        )

        if st.button("New chat", key="new_chat", icon=":material/add:"):
            reset_chat()
            st.rerun()

        st.markdown('<div class="sidebar-section">Your profile</div>', unsafe_allow_html=True)
        st.selectbox(
            "Your role",
            actions.ROLES,
            key="user_role",
            help="Used to tailor answers and check which tools you can request.",
        )

        st.markdown('<div class="sidebar-section">Conversations</div>', unsafe_allow_html=True)

        for thread_id in st.session_state["chat_threads"]:
            is_active = thread_id == st.session_state["thread_id"]
            clicked = st.button(
                retrieve_thread_title(thread_id),
                key=f"thread-{thread_id}",
                type="primary" if is_active else "secondary",
            )
            if clicked:
                st.session_state["thread_id"] = thread_id
                st.session_state["message_history"] = messages_to_history(
                    load_conversation(thread_id)
                )
                st.rerun()

        st.markdown('<div class="sidebar-section">Knowledge base</div>', unsafe_allow_html=True)
        if st.button("Re-index documents", key="reindex", icon=":material/sync:"):
            with st.spinner("Indexing documents..."):
                try:
                    count = rag.ingest()
                    st.caption(f"Indexed {count} chunks from the docs folder.")
                except Exception as error:
                    st.caption(f"Indexing failed: {error}")


def render_theme_toggle():
    """Pill button fixed to the bottom-left corner of the screen (positioned by CSS)."""
    is_dark = st.session_state["theme"] == "dark"
    label = "Light mode" if is_dark else "Dark mode"
    icon = ":material/light_mode:" if is_dark else ":material/dark_mode:"

    if st.button(label, key="theme_toggle", icon=icon):
        new_theme = "light" if is_dark else "dark"
        st.session_state["theme"] = new_theme
        st.query_params["theme"] = new_theme
        st.rerun()


# ============================ chat area ================================
def render_empty_state():
    st.markdown(
        f"""
        <div class="empty-state">
            <h2>{EMPTY_STATE_TITLE}</h2>
            <p>{EMPTY_STATE_HINT}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for i, (icon, prompt) in enumerate(SUGGESTIONS):
        if st.button(prompt, key=f"suggest-{i}", icon=icon):
            st.session_state["pending_prompt"] = prompt
            st.rerun()


def render_history():
    for message in st.session_state["message_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_approval_card(pending):
    """Shown while the agent is paused, waiting for the user to confirm an access request."""
    thread_id = str(st.session_state["thread_id"])
    with st.container(border=True):
        st.markdown('<div class="approval-title">Confirm access request</div>', unsafe_allow_html=True)
        meta = (
            f"Tool: {pending.get('tool')}<br>"
            f"Your role: {pending.get('role')}<br>"
            f"Approver: {pending.get('approver')}<br>"
            f"Typical turnaround: {pending.get('turnaround')}"
        )
        if pending.get("note"):
            meta += f"<br>Note: {pending['note']}"
        st.markdown(f'<div class="approval-meta">{meta}</div>', unsafe_allow_html=True)

        justification = st.text_area(
            "Reason (you can edit this)",
            value=pending.get("justification", ""),
            key=f"approval-reason-{thread_id}",
        )
        st.caption("Nothing is created until you confirm. This only requests access; an approver grants it.")

        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button("Create ticket", key="approval_confirm", icon=":material/check:"):
                st.session_state["pending_decision"] = {
                    "approved": True,
                    "justification": justification,
                }
                st.rerun()
        with cancel_col:
            if st.button("Cancel", key="approval_cancel"):
                st.session_state["pending_decision"] = {"approved": False}
                st.rerun()


def build_graph_input(user_input, config):
    """Attach a title to the thread the first time it is used, and pass the user's role."""
    current_state = chatbot.get_state(config=config).values
    title = current_state.get("title")

    if not title:
        first_user_message = user_input
        for message in current_state.get("messages", []):
            if isinstance(message, HumanMessage) and isinstance(message.content, str):
                first_user_message = message.content
                break
        title = format_thread_title(first_user_message) or "New conversation"

    return {
        "messages": [HumanMessage(content=user_input)],
        "title": title,
        "user_role": st.session_state["user_role"],
    }


def stream_ai_response(graph_input, config, on_first_token=None):
    """Yield only assistant text tokens (skip tool-call chunks).

    graph_input is either a normal input dict or Command(resume=...) after an approval.
    """
    is_first = True
    for chunk, _metadata in chatbot.stream(graph_input, config=config, stream_mode="messages"):
        if isinstance(chunk, AIMessage) and not chunk.tool_calls and chunk.content:
            if is_first:
                is_first = False
                if on_first_token:
                    on_first_token()
            yield chunk.content


def last_ai_text(thread_id):
    """Fallback for replies produced without token streaming (e.g. the fixed escalation message)."""
    messages = load_conversation(thread_id)
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage) and not last.tool_calls and isinstance(last.content, str):
            return last.content
    return ""


def make_config(thread_id):
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {"thread_id": thread_id, "user_role": st.session_state["user_role"]},
        "run_name": "onboarding_turn",
    }


def run_assistant_turn(graph_input, config):
    thread_id = config["configurable"]["thread_id"]

    with st.chat_message("assistant"):
        typing = st.empty()
        typing.markdown(TYPING_HTML, unsafe_allow_html=True)
        ai_message = st.write_stream(
            stream_ai_response(graph_input, config, on_first_token=typing.empty)
        )
        typing.empty()  # also covers replies that produced no text
        if not ai_message:
            ai_message = last_ai_text(thread_id)
            if ai_message:
                st.markdown(ai_message)

    if ai_message:
        st.session_state["message_history"].append(
            {"role": "assistant", "content": ai_message}
        )

    # If the agent paused for approval, redraw so the confirmation card appears.
    if get_pending_approval(thread_id):
        st.rerun()


def handle_user_input(user_input):
    thread_id = str(st.session_state["thread_id"])
    config = make_config(thread_id)
    graph_input = build_graph_input(user_input, config)

    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    run_assistant_turn(graph_input, config)


def handle_decision(decision):
    thread_id = str(st.session_state["thread_id"])
    run_assistant_turn(Command(resume=decision), make_config(thread_id))


# =============================== main ==================================
init_session_state()
inject_styles()
render_sidebar()
render_theme_toggle()

thread_id = str(st.session_state["thread_id"])
decision = st.session_state.pop("pending_decision", None)
pending_approval = None if decision else get_pending_approval(thread_id)

empty_slot = st.empty()  # lets us remove the welcome screen as soon as a message is sent

if st.session_state["message_history"]:
    render_history()
else:
    with empty_slot.container():
        render_empty_state()

if pending_approval:
    render_approval_card(pending_approval)

user_input = st.chat_input("Message the assistant", disabled=bool(pending_approval))
pending_prompt = st.session_state.pop("pending_prompt", None)
user_input = user_input or pending_prompt

if decision:
    handle_decision(decision)
elif user_input:
    empty_slot.empty()
    handle_user_input(user_input)