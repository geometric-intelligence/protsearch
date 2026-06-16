#!/usr/bin/env python3
"""
Dump PubMed/Europe PMC retrieval + UniProt block + the exact summarization user prompt
used by the backend, for manual LLM evaluation (no API calls).

Examples:
  backend/.venv/Scripts/python.exe scripts/summaryraghelper.py --manual ACE "this protein is important in kidney function"
  backend/.venv/Scripts/python.exe scripts/summaryraghelper.py --manual ACE,BRCA1 --together "paired evaluation note"

Writes under scripts/ by default (Markdown with the user prompt in a fenced block).

Use the backend virtualenv so imports (e.g. thefuzz) match the API. Multiple symbols: put them in the first argument separated by commas; add --together for AND semantics (same as the app "search together" option).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_SRC = ROOT / "backend" / "api" / "src"


def _setup_imports() -> None:
    if str(BACKEND_SRC) not in sys.path:
        sys.path.insert(0, str(BACKEND_SRC))


def _safe_filename_part(s: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE).strip("._")
    return (s[:80] if s else "export")


def _default_export_path(protein_names: List[str]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sym = _safe_filename_part("_".join(protein_names))
    return SCRIPT_DIR / f"manual_summary_{sym}_{stamp}.md"


def _md_fence(content: str, info: str = "text") -> str:
    n = 3
    while True:
        fence = "`" * n
        if fence not in content:
            return f"{fence}{info}\n{content}\n{fence}\n"
        n += 1


def _write_prompt_file(path: Path, protein_names: List[str], llm_user_prompt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    title = ", ".join(protein_names)
    text = (
        f"# Manual summary export\n\n"
        f"Proteins: `{title}`\n\n"
        f"## LLM user prompt (paste this)\n\n"
        f"This is the exact **user** message the backend sends (after UniProt + papers + instructions). "
        f"Copy from the fence below.\n\n"
        f"{_md_fence(llm_user_prompt, 'text')}"
    )
    path.write_text(text, encoding="utf-8")


def run_manual(
    symbols: List[str],
    manual_trailing_text: str,
    evaluator_notes: str,
    search_together: bool,
    search_terms: Optional[List[Dict[str, Any]]],
    user_question: str,
    has_openai_key: bool,
    write_path: Path,
) -> str:
    _setup_imports()
    from services.pubmedhelper import query_pubmed  # noqa: WPS433
    from services.uniprothelper import build_uniprot_function_block  # noqa: WPS433
    from services.summarizationwrapper import build_summarization_prompt  # noqa: WPS433

    protein_names = [s.strip().upper() for s in symbols if s.strip()]
    if not protein_names:
        raise SystemExit("No protein symbols provided.")

    papers = query_pubmed(
        protein_names,
        search_together=search_together,
        additional_terms=search_terms,
        has_openai_key=has_openai_key,
    )
    uniprot_block = build_uniprot_function_block(protein_names)
    llm_user_prompt, _prompt_meta = build_summarization_prompt(
        papers,
        protein_names,
        custom_question=user_question,
        uniprot_functions=uniprot_block,
        evaluator_notes=evaluator_notes,
    )

    _write_prompt_file(write_path, protein_names, llm_user_prompt)
    return llm_user_prompt


def main() -> None:
    env_path = ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

    parser = argparse.ArgumentParser(
        description="Export papers + UniProt + exact summarization prompt for manual evaluation.",
    )
    parser.add_argument(
        "--manual",
        nargs="+",
        metavar=("SYMBOL", "NOTES"),
        required=True,
        help='Symbol then optional text: trailing text becomes app-style User Question (§6), not only a notes block.',
    )
    parser.add_argument(
        "--together",
        action="store_true",
        help="Use search-together mode (same as app when searching multiple symbols as one query).",
    )
    parser.add_argument(
        "--search-terms-json",
        type=Path,
        help="Path to JSON array of search term objects (same shape as app search_terms).",
    )
    parser.add_argument(
        "--user-question",
        default="",
        help="Overrides section 6 (User Question). If omitted, trailing --manual text is used there (same as the app question box).",
    )
    parser.add_argument(
        "--evaluator-notes",
        default="",
        help="Optional extra === EVALUATOR NOTES === block (not in the app's numbered list). Usually leave unset.",
    )
    parser.add_argument(
        "--openai-fetch",
        action="store_true",
        help="If set and OPENAI_API_KEY is in the environment, fetch full text like the app (slower).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write to this path (default: scripts/manual_summary_<SYMBOLS>_<UTC>.md).",
    )

    args = parser.parse_args()
    raw = list(args.manual)
    first = raw[0].strip()
    if "," in first and not args.together:
        symbols = [x.strip() for x in first.split(",") if x.strip()]
        notes = " ".join(raw[1:]).strip() if len(raw) > 1 else ""
    else:
        symbols = [first]
        notes = " ".join(raw[1:]).strip() if len(raw) > 1 else ""

    search_terms: Optional[List[Dict[str, Any]]] = None
    if args.search_terms_json:
        search_terms = json.loads(args.search_terms_json.read_text(encoding="utf-8"))
        if not isinstance(search_terms, list):
            raise SystemExit("--search-terms-json must contain a JSON array")

    has_openai = bool(args.openai_fetch and (os.environ.get("OPENAI_API_KEY") or "").strip())

    explicit_uq = (args.user_question or "").strip()
    eval_notes = (args.evaluator_notes or "").strip()
    effective_uq = explicit_uq if explicit_uq else notes

    protein_names_preview = [s.strip().upper() for s in symbols if s.strip()]
    if args.output:
        out_path = args.output.expanduser()
        if not out_path.suffix:
            out_path = out_path.with_suffix(".md")
        out_path = out_path.resolve()
    else:
        out_path = _default_export_path(protein_names_preview)

    run_manual(
        symbols=symbols,
        manual_trailing_text=notes,
        evaluator_notes=eval_notes,
        search_together=args.together,
        search_terms=search_terms,
        user_question=effective_uq,
        has_openai_key=has_openai,
        write_path=out_path,
    )
    print(f"Wrote: {out_path}", flush=True)


if __name__ == "__main__":
    main()
