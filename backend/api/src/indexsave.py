import os
import time
import json
import uuid
import queue
import threading
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
# Services
from services.genealias import (
    load_gene_aliases, find_gene_and_aliases, create_search_query,
    _normalize_aliases, _normalize_token, _is_gene_like, _match_score,
)
from services.uniprothelper import build_uniprot_function_block
from services.pubmedhelper import (
    iterate_pubmed, query_pubmed, parse_pubmed_record, _build_pubmed_query,
)
from services.llmhelper import setup_openai, generate_with_gemini_rest, count_tokens
from services.summarizationwrapper import (
    summarize_papers_with_llm, ensure_results_directory, save_results_to_txt,
)
from services.confighelper import load_config
# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
load_dotenv(override=False)
app = Flask(__name__)
from flask import make_response
# Handle preflight for any route that might get POSTed to
@app.before_request
def handle_preflight():
  if request.method == "OPTIONS":
    resp = make_response("", 204)
    # Set CORS headers for cross-origin requests
    origin = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp
# Add CORS headers to all responses
@app.after_request
def after_request(response):
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
CORS(app)
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("protsearch")
# In-memory session cache
app.papers_cache: Dict[str, Dict] = {}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _looks_like_google_api_key(key: Optional[str]) -> bool:
    return isinstance(key, str) and key.strip().startswith("AIza") and len(key.strip()) > 20

def _sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# -----------------------------------------------------------------------------
# Worker
# -----------------------------------------------------------------------------
def _start_pubmed_job(session_id: str, protein_names: List[str], search_together: bool,
                      additional_terms: Optional[List[Dict]], question: str):
    try:
        sess = app.papers_cache.get(session_id)
        if not sess:
            log.warning(f"[{session_id}] Worker started but session not found.")
            return
        sess["status"] = "running"
        q: "queue.Queue[Dict[str, Any]]" = sess["queue"]

        if search_together:
            log.info(f"[{session_id}] worker start (together) for {protein_names}")
            paper_count = 0
            for item in iterate_pubmed(protein_names, True, additional_terms):
                t = item["type"]
                if t == "meta":
                    q.put({"type": "meta", "count": item.get("count", 0)})
                elif t == "paper":
                    paper = item["paper"]
                    paper_count += 1
                    log.info(f"[{session_id}] Found paper {paper_count}: {paper.get('Title', '')[:50]}...")
                    sess["papers"].append(paper)
                    q.put({"type": "paper", "paper": paper})
                elif t == "error":
                    q.put({"type": "error", "message": item.get("message", "unknown")})
        else:
            log.info(f"[{session_id}] worker start (separate) for {protein_names}")
            for protein in protein_names:
                try:
                    paper_count = 0
                    for item in iterate_pubmed([protein], True, additional_terms):
                        t = item["type"]
                        if t == "meta":
                            q.put({"type": "meta", "protein": protein, "count": item.get("count", 0)})
                        elif t == "paper":
                            paper = item["paper"]
                            paper_count += 1
                            log.info(f"[{session_id}] Found paper {paper_count} for {protein}: {paper.get('Title', '')[:50]}...")
                            if sess["papers_by_protein"] is not None:
                                sess["papers_by_protein"].setdefault(protein, []).append(paper)
                            q.put({"type": "paper", "protein": protein, "paper": paper})
                        elif t == "error":
                            q.put({"type": "error", "protein": protein, "message": item.get("message", "unknown")})
                except Exception as e:
                    log.exception(f"[{session_id}] Error processing protein {protein}: {e}")
                    q.put({"type": "error", "protein": protein, "message": str(e)})

        sess["status"] = "done"
        q.put({"type": "done"})
        log.info(f"[{session_id}] worker done")
    except Exception as e:
        log.exception(f"[{session_id}] worker error: {e}")
        try:
            if session_id in app.papers_cache:
                app.papers_cache[session_id]["status"] = "error"
                app.papers_cache[session_id]["queue"].put({"type": "error", "message": str(e)})
                app.papers_cache[session_id]["queue"].put({"type": "done"})
        except Exception:
            pass

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.route("/api/search_start", methods=["POST"])
def search_start_endpoint():
    try:
        data = request.json or {}

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key

        proteins_input = (data.get("proteins") or "").strip()
        if not proteins_input:
            return jsonify({"error": "No proteins specified"}), 400
        protein_names = [p.strip().upper() for p in proteins_input.split(",") if p.strip()]

        search_together = bool(data.get("search_proteins_together", False))
        search_terms = data.get("search_terms", []) or []
        question = data.get("question", "") or ""
        session_id = (data.get("session_id") or str(uuid.uuid4())).strip()

        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        app.papers_cache[session_id] = {
            "timestamp": datetime.now().isoformat(),
            "protein_names": protein_names,
            "question": question,
            "search_together": search_together,
            "search_terms": search_terms,
            "status": "queued",
            "queue": q,
            "papers": [] if search_together else None,
            "papers_by_protein": {} if not search_together else None,
        }

        t = threading.Thread(
            target=_start_pubmed_job,
            args=(session_id, protein_names, search_together, search_terms, question),
            daemon=True,
        )
        t.start()

        payload = {
            "success": True,
            "mode": "together" if search_together else "separate",
            "session_id": session_id,
            "proteins": protein_names,
            "papers": [] if search_together else None,
            "results": [{"protein": p, "papers": [], "summary": None, "saved_file": None} for p in protein_names] if not search_together else None,
            "summaryLoading": True,
            "summaryError": None,
        }
        log.info(f"[{session_id}] search started for proteins: {protein_names}")
        return jsonify(payload)
    except Exception as e:
        log.exception("search_start failed")
        return jsonify({"error": str(e)}), 500

@app.route("/api/search_events", methods=["GET"])
def search_events_endpoint():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id or session_id not in app.papers_cache:
        return jsonify({"error": "Session not found"}), 404

    def event_stream():
        sess = app.papers_cache.get(session_id)
        if not sess:
            log.error(f"[{session_id}] SSE stream started but session disappeared.")
            return

        mode = "together" if sess.get("search_together") else "separate"
        proteins: List[str] = sess.get("protein_names", [])
        q: "queue.Queue[Dict[str, Any]]" = sess["queue"]

        yield "retry: 60000\n\n"
        yield _sse_event("started", {"mode": mode, "proteins": proteins})
        log.info(f"[{session_id}] SSE stream connected (mode={mode})")
        
        keepalive_deadline = time.time() + 20

        while True:
            try:
                # Block for up to 1 second waiting for an item
                item = q.get(timeout=1.0)
                t = item.get("type")

                log.info(f"[{session_id}] SSE sending event: {t}")
                yield _sse_event(t, {k: v for k, v in item.items() if k != "type"})
                
                keepalive_deadline = time.time() + 20

                if t == "done":
                    log.info(f"[{session_id}] SSE stream sent 'done' event and is closing.")
                    break

            except queue.Empty:
                # If queue is empty, check if the worker is finished.
                if sess.get("status") in ("done", "error"):
                    log.warning(f"[{session_id}] Worker is finished, but queue is empty. Sending final 'done' and closing stream.")
                    yield _sse_event("done", {})
                    break
                
                # If worker is not done, send a keepalive comment to prevent timeout
                if time.time() >= keepalive_deadline:
                    yield ": keep-alive\n\n"
                    keepalive_deadline = time.time() + 20
                
                continue # Go back to the start of the loop to check the queue again
            
            except Exception as e:
                log.error(f"[{session_id}] Unhandled error in SSE event stream: {e}")
                yield _sse_event("error", {"message": str(e)})
                break

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(event_stream()), headers=headers)

@app.route("/api/session_status", methods=["GET"])
def session_status_endpoint():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id or session_id not in app.papers_cache:
        return jsonify({"status": "missing"}), 404
    sess = app.papers_cache[session_id]
    return jsonify({
        "status": sess.get("status", "unknown"),
        "mode": "together" if sess.get("search_together") else "separate",
        "protein_names": sess.get("protein_names", []),
        "counts": {
            "total": len(sess.get("papers", [])) if sess.get("papers") is not None else None,
            "per_protein": {k: len(v or []) for k, v in (sess.get("papers_by_protein") or {}).items()} if sess.get("papers_by_protein") is not None else None,
        },
    })

@app.route("/api/suggest", methods=["POST"])
def suggest_endpoint():
    try:
        data = request.json or {}
        raw = data.get("proteins")
        if isinstance(raw, list):
            tokens = [str(x).strip() for x in raw if str(x).strip()]
        else:
            tokens = [t.strip() for t in str(raw or "").split(",") if t.strip()]
        if not tokens:
            return jsonify({"suggestions": []})

        project_root = Path(__file__).parent.parent
        tsv_path = project_root / "proteinatlas_search.tsv"
        genes_df = load_gene_aliases(tsv_path)
        if genes_df is None or genes_df.empty or "Gene" not in genes_df.columns:
            return jsonify({"suggestions": [], "warning": "Gene alias table unavailable"}), 200

        results = []
        for tok in tokens:
            exact = False
            try:
                t = _normalize_token(tok)
                exact = not genes_df[genes_df["Gene"].astype(str).map(_normalize_token) == t].empty
                if not exact:
                    for aliases in genes_df.get("Aliases", pd.Series([])).fillna("").astype(str):
                        for a in _normalize_aliases(aliases):
                            if _normalize_token(a) == t:
                                exact = True
                                break
                        if exact:
                            break
            except Exception:
                exact = False

            variant_to_canonical: Dict[str, str] = {}
            rows_by_gene: Dict[str, Any] = {}
            for _, row in genes_df.iterrows():
                canonical = str(row.get("Gene", "")).strip()
                if not canonical:
                    continue
                rows_by_gene[canonical] = row
                variant_to_canonical[canonical] = canonical
                for alias in _normalize_aliases(row.get("Aliases", "")):
                    if _is_gene_like(alias):
                        variant_to_canonical[alias] = canonical

            variant_names = list(variant_to_canonical.keys())
            norm_map: Dict[str, str] = {name: _normalize_token(name) for name in variant_names}
            reverse_norm: Dict[str, List[str]] = {}
            for original, normed in norm_map.items():
                reverse_norm.setdefault(normed, []).append(original)

            norm_variants = list(reverse_norm.keys())
            norm_token = _normalize_token(tok)
            if not norm_token or not norm_variants:
                results.append({"input": tok, "exact": bool(exact), "suggestions": [], "details": []})
                continue

            from thefuzz import process, fuzz
            raw_matches = process.extract(norm_token, norm_variants, limit=50, scorer=fuzz.ratio)

            best_by_canonical: Dict[str, int] = {}
            for norm_name, _ in raw_matches:
                originals = reverse_norm.get(norm_name, [])
                for original in originals:
                    canonical = variant_to_canonical.get(original)
                    if not canonical:
                        continue
                    score = _match_score(tok, original)
                    prev = best_by_canonical.get(canonical, -1)
                    if score > prev:
                        best_by_canonical[canonical] = score

            MIN_SCORE = 70
            filtered = [(g, s) for g, s in best_by_canonical.items() if s >= MIN_SCORE]
            ranked = sorted(filtered, key=lambda x: x[1], reverse=True)[:5]
            details = []
            for canonical, score in ranked:
                row_data = rows_by_gene.get(canonical, {})
                details.append(
                    {
                        "gene": canonical,
                        "aliases": row_data.get("Aliases", ""),
                        "gene_name": row_data.get("Gene name", ""),
                        "score": int(score),
                    }
                )

            results.append(
                {
                    "input": tok,
                    "exact": bool(exact),
                    "suggestions": [d["gene"] for d in details],
                    "details": details,
                }
            )

        return jsonify({"suggestions": results})
    except Exception as e:
        log.exception("suggest failed")
        return jsonify({"error": str(e)}), 500

@app.route("/api/search", methods=["POST"])
def search_endpoint():
    try:
        data = request.json or {}

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key

        proteins_input = (data.get("proteins") or "").strip()
        if not proteins_input:
            return jsonify({"error": "No proteins specified"}), 400

        protein_names = [p.strip().upper() for p in proteins_input.split(",") if p.strip()]
        search_together = bool(data.get("search_proteins_together", False))
        search_terms = data.get("search_terms", []) or []
        question = data.get("question", "") or ""
        session_id = (data.get("session_id") or str(uuid.uuid4())).strip()
        fetch_papers_only = bool(data.get("fetch_papers_only", False))

        if search_together:
            papers = query_pubmed(protein_names, True, search_terms)
            papers_for_response = [
                {
                    "pmid": paper.get("PMID", ""),
                    "title": paper.get("Title", ""),
                    "authors": paper.get("Authors", ""),
                    "journal": paper.get("Journal", ""),
                    "year": paper.get("Year", ""),
                    "abstract": paper.get("Abstract", ""),
                    "doi": paper.get("DOI", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('PMID', '')}/",
                }
                for paper in papers
            ]
            if fetch_papers_only:
                app.papers_cache[session_id] = {
                    "papers": papers,
                    "protein_names": protein_names,
                    "question": question,
                    "timestamp": datetime.now().isoformat(),
                }
                return jsonify({"success": True, "mode": "together", "session_id": session_id, "proteins": protein_names, "papers": papers_for_response})

            if not papers:
                return jsonify({"success": True, "mode": "together", "proteins": protein_names, "papers": [], "summary": "No papers found matching your search criteria."})

            uniprot_block = build_uniprot_function_block(protein_names)
            summary = summarize_papers_with_llm(papers, protein_names, question, uniprot_block)
            results_dir = ensure_results_directory()
            saved_file = save_results_to_txt(summary, "_".join(protein_names), results_dir)
            return jsonify({"success": True, "mode": "together", "proteins": protein_names, "papers": papers_for_response, "summary": summary, "saved_file": saved_file or None})

        # separate
        all_results = []
        all_papers_data = []
        for protein in protein_names:
            papers = query_pubmed([protein], True, search_terms)
            all_papers_data.append({"protein": protein, "papers": papers})
            papers_for_response = [
                {
                    "pmid": paper.get("PMID", ""),
                    "title": paper.get("Title", ""),
                    "authors": paper.get("Authors", ""),
                    "journal": paper.get("Journal", ""),
                    "year": paper.get("Year", ""),
                    "abstract": paper.get("Abstract", ""),
                    "doi": paper.get("DOI", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('PMID', '')}/",
                }
                for paper in papers
            ]
            if fetch_papers_only:
                all_results.append({"protein": protein, "papers": papers_for_response, "summary": None})
            else:
                if papers:
                    uniprot_block = build_uniprot_function_block([protein])
                    protein_summary = summarize_papers_with_llm(papers, [protein], question, uniprot_block)
                    results_dir = ensure_results_directory()
                    saved_file = save_results_to_txt(protein_summary, protein, results_dir)
                else:
                    protein_summary = f"No papers found for {protein}."
                    saved_file = None
                all_results.append({"protein": protein, "papers": papers_for_response, "summary": protein_summary, "saved_file": saved_file})

        if fetch_papers_only:
            app.papers_cache[session_id] = {
                "papers_by_protein": {r["protein"]: all_papers_data[i]["papers"] for i, r in enumerate(all_results)},
                "protein_names": protein_names,
                "question": question,
                "timestamp": datetime.now().isoformat(),
            }
            return jsonify({"success": True, "mode": "separate", "session_id": session_id, "results": all_results})

        return jsonify({"success": True, "mode": "separate", "results": all_results})
    except Exception as e:
        log.exception("search failed")
        return jsonify({"error": str(e)}), 500

@app.route("/api/summarize", methods=["POST"])
def summarize_endpoint():
    try:
        data = request.json or {}
        session_id = (data.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
        if session_id not in app.papers_cache:
            return jsonify({"error": "Session expired or not found"}), 404

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key

        cached_data = app.papers_cache[session_id]
        question = data.get("question") or cached_data.get("question", "")
        search_together = cached_data.get("search_together", False)

        if search_together:
            # Handle 'together' mode
            papers = cached_data.get("papers", [])
            if not papers:
                 return jsonify({"success": True, "summary": "No papers found to summarize.", "saved_file": None})
            
            protein_names = cached_data.get("protein_names", [])
            uniprot_block = build_uniprot_function_block(protein_names)
            summary = summarize_papers_with_llm(papers, protein_names, question, uniprot_block)
            results_dir = ensure_results_directory()
            saved_file = save_results_to_txt(summary, "_".join(protein_names), results_dir)
            return jsonify({"success": True, "summary": summary, "saved_file": saved_file})

        else:
            # Handle 'separate' mode
            all_papers_data = cached_data.get("papers_by_protein", {})
            summaries = []
            for protein, papers in all_papers_data.items():
                if not papers:
                    summaries.append({"protein": protein, "summary": f"No papers found for {protein}.", "saved_file": None})
                    continue
                uniprot_block = build_uniprot_function_block([protein])
                protein_summary = summarize_papers_with_llm(papers, [protein], question, uniprot_block)
                results_dir = ensure_results_directory()
                saved_file = save_results_to_txt(protein_summary, protein, results_dir)
                summaries.append({"protein": protein, "summary": protein_summary, "saved_file": saved_file})
            return jsonify({"success": True, "summaries": summaries})

    except Exception as e:
        log.exception("summarize failed")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "ProtSearch API is running", "cache_size": len(app.papers_cache)})

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
def cleanup_expired_sessions():
    current_time = datetime.now()
    expired_sessions: List[str] = []
    for session_id, data in list(app.papers_cache.items()):
        try:
            timestamp_str = data.get("timestamp", "")
            if not timestamp_str:
                expired_sessions.append(session_id)
                continue
            timestamp = datetime.fromisoformat(timestamp_str)
            elapsed = current_time - timestamp
            if elapsed.total_seconds() > 3600:
                expired_sessions.append(session_id)
        except Exception:
            expired_sessions.append(session_id)
    for session_id in expired_sessions:
        if session_id in app.papers_cache:
            del app.papers_cache[session_id]
            log.info(f"Cleaned up expired session: {session_id}")

@app.route("/api/cleanup", methods=["POST"])
def cleanup_endpoint():
    cleanup_expired_sessions()
    return jsonify({"success": True, "message": "Cache cleaned up", "remaining_sessions": len(app.papers_cache)})

def start_cleanup_scheduler():
    def cleanup_task():
        while True:
            time.sleep(3600)
            cleanup_expired_sessions()
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()

start_cleanup_scheduler()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080, threaded=True)
