"""Knowledge base for the onboarding agent: ingest documents once, search them later.

Usage:
    python rag.py --ingest                 # (re)build the index from ./docs
    python rag.py --query "how do I set up the VPN?"
"""

import argparse
import hashlib
import os
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:  # older installs
    from langchain_community.embeddings import HuggingFaceEmbeddings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = Path(os.getenv("DOCS_DIR", BASE_DIR / "docs"))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", BASE_DIR / "chroma_db"))
COLLECTION = "onboarding_policies"

CHUNK_SIZE = 900        # characters (~200 tokens): small enough for precise matches
CHUNK_OVERLAP = 120
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# Cosine similarity below this is treated as "no relevant document".
# Tune it with your eval questions (run: python rag.py --query "...").
MIN_RELEVANCE = float(os.getenv("RAG_MIN_SCORE", "0.35"))
STALE_AFTER_DAYS = 365

HEADER_RE = re.compile(r"^(last updated|applies to|owner)\s*:\s*(.+)$", re.IGNORECASE)


# ------------------------------------------------------------------
# models and store (loaded once per process)
# ------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=1)
def get_vectorstore():
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )


# ------------------------------------------------------------------
# loading and chunking
# ------------------------------------------------------------------
def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Pull 'Last updated / Applies to / Owner' lines out of the top of a document."""
    meta, kept = {}, []
    for index, line in enumerate(text.splitlines()):
        match = HEADER_RE.match(line.strip())
        if match and index < 12:
            meta[match.group(1).lower().replace(" ", "_")] = match.group(2).strip()
        else:
            kept.append(line)
    return meta, "\n".join(kept)


def _file_date(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def _load_markdown_or_text(path: Path) -> list[Document]:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(raw)
    title_match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ").title()

    sections = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=True,
    ).split_text(body)

    docs = []
    for section in sections:
        heading = section.metadata.get("h3") or section.metadata.get("h2") or section.metadata.get("h1") or ""
        # Put the breadcrumb in the text itself so every chunk carries its context.
        breadcrumb = title if heading in ("", title) else f"{title} > {heading}"
        docs.append(
            Document(
                page_content=f"{breadcrumb}\n{section.page_content}".strip(),
                metadata={
                    "source": path.name,
                    "title": title,
                    "section": heading,
                    "last_updated": meta.get("last_updated", _file_date(path)),
                    "applies_to": meta.get("applies_to", "All employees"),
                    "owner": meta.get("owner", ""),
                },
            )
        )
    return docs


def _load_pdf(path: Path) -> list[Document]:
    from langchain_community.document_loaders import PyPDFLoader  # needs pypdf

    docs = []
    for page in PyPDFLoader(str(path)).load():
        docs.append(
            Document(
                page_content=page.page_content,
                metadata={
                    "source": path.name,
                    "title": path.stem.replace("_", " ").title(),
                    "section": f"page {page.metadata.get('page', 0) + 1}",
                    "last_updated": _file_date(path),
                    "applies_to": "All employees",
                    "owner": "",
                },
            )
        )
    return docs


def load_documents(docs_dir: Path = DOCS_DIR) -> list[Document]:
    docs = []
    for path in sorted(Path(docs_dir).rglob("*")):
        if path.suffix.lower() in (".md", ".txt"):
            docs.extend(_load_markdown_or_text(path))
        elif path.suffix.lower() == ".pdf":
            docs.extend(_load_pdf(path))
    return docs


def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return splitter.split_documents(docs)


# ------------------------------------------------------------------
# ingestion
# ------------------------------------------------------------------
def ingest(docs_dir: Path = DOCS_DIR) -> int:
    """Rebuild the whole index from scratch (the document set is small)."""
    chunks = chunk_documents(load_documents(docs_dir))
    if not chunks:
        raise RuntimeError(f"No .md/.txt/.pdf files found in {docs_dir}")

    store = get_vectorstore()
    try:
        store.delete_collection()
    except Exception:
        pass
    get_vectorstore.cache_clear()
    store = get_vectorstore()

    ids = [
        hashlib.sha1(f"{c.metadata['source']}|{i}|{c.page_content}".encode()).hexdigest()[:20]
        for i, c in enumerate(chunks)
    ]
    store.add_documents(chunks, ids=ids)
    return len(chunks)


def _ensure_index():
    store = get_vectorstore()
    if store._collection.count() == 0:  # first run: build automatically
        ingest()


# ------------------------------------------------------------------
# search
# ------------------------------------------------------------------
def _days_old(last_updated: str) -> int | None:
    try:
        return (date.today() - date.fromisoformat(last_updated)).days
    except ValueError:
        return None


def _audience_ok(applies_to: str, role: str | None) -> bool:
    """Relevance filter (not a security boundary): skip docs aimed at other roles."""
    if not role or not applies_to or "all" in applies_to.lower():
        return True
    return role.lower() in applies_to.lower()


def _search_queries(query: str) -> list[str]:
    queries = [query]
    is_day_30_onboarding = (
        re.search(r"\b(?:first\s+)?(?:30|thirty)[ -]days?\b|\bday\s+30\b", query, re.IGNORECASE)
        and re.search(r"\b(onboard\w*|new hire|new employee|join\w*|task\w*)\b", query, re.IGNORECASE)
    )
    if is_day_30_onboarding:
        queries.append(
            "new employee by day 30 enroll health insurance BenefitsHub "
            "submit first expense claims"
        )
    return queries


def search(query: str, role: str | None = None, k: int = TOP_K) -> list[dict]:
    _ensure_index()
    store = get_vectorstore()
    best_hits = {}
    for search_query in _search_queries(query):
        for doc, score in store.similarity_search_with_relevance_scores(search_query, k=k * 2):
            if score < MIN_RELEVANCE:
                continue
            key = (doc.metadata.get("source", ""), doc.metadata.get("section", ""), doc.page_content)
            if key not in best_hits or score > best_hits[key][1]:
                best_hits[key] = (doc, score)

    results = []
    hits = sorted(best_hits.values(), key=lambda hit: hit[1], reverse=True)
    for doc, score in hits:
        meta = doc.metadata
        if not _audience_ok(meta.get("applies_to", ""), role):
            continue
        age = _days_old(meta.get("last_updated", ""))
        results.append(
            {
                "text": doc.page_content,
                "source": meta.get("source", ""),
                "title": meta.get("title", ""),
                "section": meta.get("section", ""),
                "last_updated": meta.get("last_updated", "unknown"),
                "score": round(float(score), 3),
                "stale": age is not None and age > STALE_AFTER_DAYS,
            }
        )
        if len(results) == k:
            break
    return results


def format_for_llm(results: list[dict]) -> str:
    if not results:
        return (
            "NO_RELEVANT_DOCUMENTS: nothing in the onboarding documents matches this question. "
            "Do not answer from memory. Say you could not find it and point to the right contact."
        )
    blocks = []
    for number, hit in enumerate(results, start=1):
        flag = "  [OUTDATED: older than 1 year, may no longer apply]" if hit["stale"] else ""
        section = f" - {hit['section']}" if hit["section"] else ""
        blocks.append(
            f"[{number}] {hit['title']}{section} (file: {hit['source']}, "
            f"last updated: {hit['last_updated']}){flag}\n{hit['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def search_as_text(query: str, role: str | None = None) -> str:
    return format_for_llm(search(query, role=role))


# ------------------------------------------------------------------
# command line
# ------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding knowledge base")
    parser.add_argument("--ingest", action="store_true", help="rebuild the index from ./docs")
    parser.add_argument("--query", type=str, help="run a test search and show scores")
    args = parser.parse_args()

    if args.ingest:
        print(f"Indexed {ingest()} chunks from {DOCS_DIR}")
    if args.query:
        _ensure_index()
        raw = get_vectorstore().similarity_search_with_relevance_scores(args.query, k=6)
        print(f"Threshold: {MIN_RELEVANCE}\n")
        for doc, score in raw:
            marker = "KEEP" if score >= MIN_RELEVANCE else "drop"
            print(f"{score:.3f}  {marker}  {doc.metadata['source']} | {doc.metadata['section']}")
