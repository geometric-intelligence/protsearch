import os
import sys
from pathlib import Path

# Add the current directory to Python path FIRST, before any other imports
# This ensures services can be imported as 'from services.xxx import ...'
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import time
import json
import uuid
import queue
import threading
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# Setup logging early
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("protsearch")

# Debug: Log sys.path and verify services directory exists
log.info(f"Current file: {__file__}")
log.info(f"Current dir: {current_dir}")
log.info(f"sys.path: {sys.path}")
services_dir = current_dir / "services"
log.info(f"Services directory exists: {services_dir.exists()}")
if services_dir.exists():
    log.info(f"Services directory contents: {list(services_dir.iterdir())}")
    # Test if we can import services directly
    try:
        import services
        log.info(f"Successfully imported services package: {services}")
        log.info(f"services.__file__: {getattr(services, '__file__', 'N/A')}")
        log.info(f"services.__path__: {getattr(services, '__path__', 'N/A')}")
    except Exception as e:
        log.error(f"Failed to import services package: {e}")
        import traceback
        log.error(traceback.format_exc())
else:
    log.error(f"Services directory NOT FOUND at: {services_dir}")

try:
    import pandas as pd
except ImportError as e:
    log.error(f"Failed to import pandas: {e}")
    pd = None

from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context, make_response, g
from flask_cors import CORS

# -----------------------------------------------------------------------------
# Safe helpers for diagnostics
# -----------------------------------------------------------------------------
def _env_present(name: str) -> bool:
    try:
        return bool(os.environ.get(name))
    except Exception:
        return False

def _service_status() -> Dict[str, Any]:
    return {
        "pubmed_imported": iterate_pubmed is not None,
        "iterate_callable": callable(iterate_pubmed) if iterate_pubmed is not None else False,
        "query_imported": query_pubmed is not None,
        "query_callable": callable(query_pubmed) if query_pubmed is not None else False,
        "uniprot_available": build_uniprot_function_block is not None,
        "summarization_available": summarize_papers_with_llm is not None
            and ensure_results_directory is not None
            and save_results_to_txt is not None,
        "genealias_available": all([
            load_gene_aliases is not None,
            _normalize_aliases is not None,
            _normalize_token is not None,
            _is_gene_like is not None,
            _match_score is not None,
        ]),
        "env_openai_set": _env_present("OPENAI_API_KEY"),
        "env_google_set": _env_present("GOOGLE_API_KEY"),
    }

def _jsonify_with_diag(payload: Dict[str, Any], status: int = 200, route: str = ""):
    rid = getattr(g, "rid", None) or ""
    body = dict(payload)
    body["diag"] = {
        "rid": rid,
        "route": route,
        "services": _service_status(),
        "server_time": datetime.utcnow().isoformat() + "Z",
    }
    resp = jsonify(body)
    resp.status_code = status
    # Echo breadcrumb headers
    resp.headers["X-Request-Id"] = rid
    if "mode" in payload:
        resp.headers["X-Mode"] = str(payload["mode"])
    if "error" in payload:
        resp.headers["X-Error"] = str(payload["error"])[:200]
    return resp

def _log_with_rid(level: str, msg: str, **fields):
    rid = getattr(g, "rid", None) or fields.pop("rid", "-")
    kv = " ".join([f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()])
    line = f"[{rid}] {msg}" + (f" | {kv}" if kv else "")
    if level == "debug":
        log.debug(line)
    elif level == "warning":
        log.warning(line)
    elif level == "error":
        log.error(line)
    else:
        log.info(line)

# -----------------------------------------------------------------------------
# Services - import with error handling (allow app to start even if some fail)
# -----------------------------------------------------------------------------
try:
    from services.genealias import (
        load_gene_aliases, find_gene_and_aliases, create_search_query,
        _normalize_aliases, _normalize_token, _is_gene_like, _match_score,
    )
except Exception as e:
    log.warning("Failed to import genealias services. Some features may not work.")
    log.exception("genealias import failure")
    load_gene_aliases = None
    find_gene_and_aliases = None
    create_search_query = None
    _normalize_aliases = None
    _normalize_token = None
    _is_gene_like = None
    _match_score = None

try:
    from services.uniprothelper import build_uniprot_function_block
except Exception as e:
    log.warning("Failed to import uniprothelper. Some features may not work.")
    log.exception("uniprothelper import failure")
    build_uniprot_function_block = None

# Import only what we actually call here to avoid confusion
try:
    from services.pubmedhelper import iterate_pubmed, query_pubmed
except Exception as e:
    log.warning("Failed to import pubmedhelper. PubMed features unavailable.")
    log.exception("pubmedhelper import failure")
    iterate_pubmed = None  # type: ignore
    query_pubmed = None  # type: ignore

try:
    from services.llmhelper import setup_openai, generate_with_gemini_rest, count_tokens
except Exception as e:
    log.warning("Failed to import llmhelper. Some features may not work.")
    log.exception("llmhelper import failure")
    setup_openai = None
    generate_with_gemini_rest = None
    count_tokens = None

try:
    from services.summarizationwrapper import (
        summarize_papers_with_llm, ensure_results_directory, save_results_to_txt,
    )
except Exception as e:
    log.warning("Failed to import summarizationwrapper. Some features may not work.")
    log.exception("summarizationwrapper import failure")
    summarize_papers_with_llm = None
    ensure_results_directory = None
    save_results_to_txt = None

try:
    from services.confighelper import load_config
except Exception as e:
    log.warning("Failed to import confighelper. Some features may not work.")
    log.exception("confighelper import failure")
    load_config = None

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
load_dotenv(override=False)
app = Flask(__name__)

# Configure CORS properly - allow all origins but handle credentials correctly
CORS(app,
     resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"],
                       "allow_headers": ["Content-Type", "Authorization"],
                       "supports_credentials": False}},
     supports_credentials=False)

log.info("Flask app and CORS configured")
# Test print to verify console output works
import sys
print("[DEBUG] ========== FLASK APP STARTING ==========", flush=True)
sys.stdout.flush()

# Assign a Request ID for every request (breadcrumb)
@app.before_request
def assign_request_id():
    try:
        g.rid = request.headers.get("X-Debug-Id") or request.headers.get("X-Request-Id") or str(uuid.uuid4())
        _log_with_rid("info", "request_start", method=request.method, path=request.path)
    except Exception:
        # Avoid blocking requests if logging fails
        pass

# Handle preflight requests explicitly
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        origin = request.headers.get("Origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
        else:
            resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Request-Id, X-Debug-Id"
        resp.headers["Access-Control-Max-Age"] = "3600"
        resp.headers["X-Request-Id"] = getattr(g, "rid", "")
        return resp

# Add CORS headers and X-Request-Id to all responses
@app.after_request
def after_request(response):
    try:
        origin = request.headers.get("Origin")
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Request-Id, X-Debug-Id"
        response.headers["Access-Control-Max-Age"] = "3600"
        response.headers["X-Request-Id"] = getattr(g, "rid", "")
        _log_with_rid("info", "request_end", status_code=response.status_code, path=request.path)
    except Exception:
        pass
    return response

# In-memory session cache
# NOTE: This is NOT shared between gunicorn workers. If using multiple workers,
# sessions created in one worker won't be visible to other workers.
# Solution: Use 1 worker OR implement Redis/database-backed session storage.
app.papers_cache: Dict[str, Dict] = {}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _looks_like_google_api_key(key: Optional[str]) -> bool:
    return isinstance(key, str) and key.strip().startswith("AIza") and len(key.strip()) > 20

def _sse_event(event: str, data: Dict[str, Any], rid: Optional[str] = None) -> str:
    try:
        payload = dict(data) if data else {}
        payload["rid"] = rid or getattr(g, "rid", None) or ""
        # Ensure all values are JSON-serializable
        clean_payload = {}
        for k, v in payload.items():
            if v is None:
                clean_payload[k] = ""
            elif isinstance(v, (str, int, float, bool, list, dict)):
                clean_payload[k] = v
            else:
                clean_payload[k] = str(v)
        json_data = json.dumps(clean_payload, ensure_ascii=False)
        return f"event: {event}\ndata: {json_data}\n\n"
    except Exception as e:
        log.error(f"Error creating SSE event: {e}, event={event}, data={data}")
        # Return a safe error event
        safe_payload = {"error": "Failed to serialize event data", "rid": rid or getattr(g, "rid", None) or ""}
        return f"event: error\ndata: {json.dumps(safe_payload, ensure_ascii=False)}\n\n"

# Service availability guards
def _require_pubmed_available() -> Optional[str]:
    if iterate_pubmed is None or not callable(iterate_pubmed):
        return "PubMed service unavailable on server (module import failed)"
    return None

def _require_query_pubmed_available() -> Optional[str]:
    if query_pubmed is None or not callable(query_pubmed):
        return "PubMed service unavailable on server (module import failed)"
    return None

def _require_summarization_available() -> Optional[str]:
    if build_uniprot_function_block is None:
        return "UniProt helper unavailable on server (module import failed)"
    if summarize_papers_with_llm is None or ensure_results_directory is None or save_results_to_txt is None:
        return "Summarization service unavailable on server (module import failed)"
    return None

# -----------------------------------------------------------------------------
# Worker
# -----------------------------------------------------------------------------
def _start_pubmed_job(session_id: str, protein_names: List[str], search_together: bool,
                      additional_terms: Optional[List[Dict]], question: str):
    # We don't have Flask g here, so pull rid from the session for breadcrumbs
    sess_rid = None
    try:
        sess = app.papers_cache.get(session_id)
        sess_rid = (sess or {}).get("rid")
        if not sess:
            log.warning(f"[{sess_rid or '-'}] [{session_id}] Worker started but session not found.")
            return
        sess["status"] = "running"
        q: "queue.Queue[Dict[str, Any]]" = sess["queue"]

        # Guard: ensure iterate_pubmed is available
        pubmed_err = _require_pubmed_available()
        if pubmed_err:
            log.error(f"[{sess_rid or '-'}] [{session_id}] {pubmed_err}")
            sess["status"] = "error"
            q.put({"type": "error", "message": pubmed_err, "rid": sess_rid})
            q.put({"type": "done", "rid": sess_rid})
            return

        # Get has_openai_key from session
        has_openai_key = sess.get("has_openai_key", False)
        
        if search_together:
            log.info(f"[{sess_rid or '-'}] [{session_id}] worker start (together) proteins={protein_names} terms={additional_terms} has_openai_key={has_openai_key}")
            paper_count = 0
            for item in iterate_pubmed(protein_names, True, additional_terms, has_openai_key=has_openai_key):
                t = item.get("type")
                if t == "meta":
                    q.put({"type": "meta", "count": item.get("count", 0), "rid": sess_rid})
                elif t == "paper":
                    paper = item.get("paper", {})
                    paper_count += 1
                    log.info(f"[{sess_rid or '-'}] [{session_id}] paper#{paper_count} title={paper.get('Title', '')[:80]}")
                    sess["papers"].append(paper)
                    # Strip FullText from paper sent to frontend (only needed for backend summarization)
                    paper_for_frontend = {k: v for k, v in paper.items() if k != "FullText"}
                    q.put({"type": "paper", "paper": paper_for_frontend, "rid": sess_rid})
                elif t == "error":
                    error_msg = item.get("message", "unknown")
                    # Don't send parse_failed errors to frontend - they're not critical
                    if error_msg != "parse_failed":
                        q.put({"type": "error", "message": error_msg, "rid": sess_rid})
                    # Log parse_failed errors but don't send them to frontend
                    elif error_msg == "parse_failed":
                        log.debug(f"[{sess_rid or '-'}] [{session_id}] Skipping parse_failed error (non-critical)")
        else:
            log.info(f"[{sess_rid or '-'}] [{session_id}] worker start (separate) proteins={protein_names} terms={additional_terms} has_openai_key={has_openai_key}")
            for protein in protein_names:
                try:
                    paper_count = 0
                    for item in iterate_pubmed([protein], True, additional_terms, has_openai_key=has_openai_key):
                        t = item.get("type")
                        if t == "meta":
                            q.put({"type": "meta", "protein": protein, "count": item.get("count", 0), "rid": sess_rid})
                        elif t == "paper":
                            paper = item.get("paper", {})
                            paper_count += 1
                            log.info(f"[{sess_rid or '-'}] [{session_id}] {protein} paper#{paper_count} title={paper.get('Title', '')[:80]}")
                            if sess["papers_by_protein"] is not None:
                                sess["papers_by_protein"].setdefault(protein, []).append(paper)
                            # Strip FullText from paper sent to frontend (only needed for backend summarization)
                            paper_for_frontend = {k: v for k, v in paper.items() if k != "FullText"}
                            q.put({"type": "paper", "protein": protein, "paper": paper_for_frontend, "rid": sess_rid})
                        elif t == "error":
                            error_msg = item.get("message", "unknown")
                            # Don't send parse_failed errors to frontend - they're not critical
                            if error_msg != "parse_failed":
                                q.put({"type": "error", "protein": protein, "message": error_msg, "rid": sess_rid})
                            # Log parse_failed errors but don't send them to frontend
                            elif error_msg == "parse_failed":
                                log.debug(f"[{sess_rid or '-'}] [{session_id}] Skipping parse_failed error (non-critical)")
                except Exception as e:
                    log.exception(f"[{sess_rid or '-'}] [{session_id}] Error processing protein {protein}: {e}")
                    q.put({"type": "error", "protein": protein, "message": str(e), "rid": sess_rid})

        sess["status"] = "done"
        q.put({"type": "done", "rid": sess_rid})
        log.info(f"[{sess_rid or '-'}] [{session_id}] worker done")
    except Exception as e:
        log.exception(f"[{sess_rid or '-'}] [{session_id}] worker error: {e}")
        try:
            if session_id in app.papers_cache:
                app.papers_cache[session_id]["status"] = "error"
                app.papers_cache[session_id]["queue"].put({"type": "error", "message": str(e), "rid": sess_rid})
                app.papers_cache[session_id]["queue"].put({"type": "done", "rid": sess_rid})
        except Exception:
            pass

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.route("/api/search_start", methods=["POST"])
def search_start_endpoint():
    try:
        data = request.json or {}
        _log_with_rid("info", "search_start_received", body_keys=list(data.keys()))

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        has_openai_key = False  # Track if OpenAI key is being used
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key
                has_openai_key = True
                print(f"[DEBUG] search_start: Storing OpenAI key in session, length: {len(api_key)}", flush=True)
                import sys
                sys.stdout.flush()

        # Guard: don't start session if PubMed module missing
        pubmed_err = _require_pubmed_available()
        if pubmed_err:
            _log_with_rid("error", "search_start_pubmed_unavailable", error=pubmed_err)
            return _jsonify_with_diag({"error": pubmed_err}, status=503, route="search_start")

        proteins_input = (data.get("proteins") or "").strip()
        if not proteins_input:
            return _jsonify_with_diag({"error": "No proteins specified"}, status=400, route="search_start")
        protein_names = [p.strip().upper() for p in proteins_input.split(",") if p.strip()]

        search_together = bool(data.get("search_proteins_together", False))
        search_terms = data.get("search_terms", []) or []
        question = data.get("question", "") or ""
        
        # Always generate a fresh session_id for a new search
        # This ensures each search gets a completely new session
        provided_session_id = (data.get("session_id") or "").strip()
        session_id = str(uuid.uuid4())
        
        # Clean up any provided session_id if it exists (user starting a new search)
        if provided_session_id and provided_session_id in app.papers_cache:
            _log_with_rid("info", "search_start_cleaning_existing_session", 
                         old_session_id=provided_session_id,
                         new_session_id=session_id)
            old_sess = app.papers_cache.get(provided_session_id)
            if old_sess and "queue" in old_sess:
                try:
                    # Drain the old queue to prevent memory leaks
                    while not old_sess["queue"].empty():
                        old_sess["queue"].get_nowait()
                except:
                    pass
            del app.papers_cache[provided_session_id]
            _log_with_rid("info", "search_start_old_session_removed", old_session_id=provided_session_id)
        
        # Clean up only very old expired sessions (don't be too aggressive)
        # Only clean up sessions older than 4 hours to avoid removing active ones
        try:
            current_time = datetime.now()
            very_old_sessions: List[str] = []
            for sid, sess_data in list(app.papers_cache.items()):
                try:
                    ts_str = sess_data.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str)
                        if (current_time - ts).total_seconds() > 14400:  # 4 hours
                            very_old_sessions.append(sid)
                except:
                    pass
            for sid in very_old_sessions:
                if sid in app.papers_cache:
                    del app.papers_cache[sid]
                    log.debug(f"[search_start] Removed very old session {sid}")
        except Exception as e:
            log.warning(f"[search_start] Error during selective cleanup: {e}")
        
        _log_with_rid("info", "search_start_creating_new_session", 
                     session_id=session_id,
                     cache_size_before=len(app.papers_cache),
                     provided_session_id=provided_session_id if provided_session_id else None)

        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        app.papers_cache[session_id] = {
            "timestamp": datetime.now().isoformat(),
            "rid": getattr(g, "rid", None),
            "protein_names": protein_names,
            "question": question,
            "search_together": search_together,
            "search_terms": search_terms,
            "status": "queued",
            "queue": q,
            "papers": [] if search_together else None,
            "papers_by_protein": {} if not search_together else None,
            "has_openai_key": has_openai_key,  # Store whether OpenAI key is being used
            "api_key": api_key if api_key and not _looks_like_google_api_key(api_key) else None,  # Store the API key for later use in summarize (only if it's an OpenAI key)
        }

        t = threading.Thread(
            target=_start_pubmed_job,
            args=(session_id, protein_names, search_together, search_terms, question),
            daemon=True,
        )
        t.start()

        # Verify session was created and log all sessions for debugging
        if session_id not in app.papers_cache:
            _log_with_rid("error", "search_start_session_not_in_cache_after_creation", session_id=session_id)
            return _jsonify_with_diag({"error": "Failed to create session"}, status=500, route="search_start")
        
        # Log all current sessions for debugging (helps identify multi-instance issues)
        all_sessions = list(app.papers_cache.keys())
        _log_with_rid("info", "search_start_session_created", 
                     session_id=session_id,
                     cache_size=len(app.papers_cache),
                     all_session_ids=all_sessions[:10])  # Log first 10 for debugging
        
        payload = {
            "success": True,
            "mode": "together" if search_together else "separate",
            "session_id": session_id,
            "proteins": protein_names,
            "papers": [] if search_together else None,
            "results": [{"protein": p, "papers": [], "summary": None, "saved_file": None} for p in protein_names] if not search_together else None,
            "summaryLoading": True,
            "summaryError": None,
            "new_session": True,  # Flag to indicate this is a fresh session - frontend should clear old data
        }
        _log_with_rid("info", "search_start_ok", 
                     session_id=session_id, 
                     mode=payload["mode"], 
                     proteins=protein_names, 
                     terms=search_terms,
                     cache_size=len(app.papers_cache),
                     session_verified=True,
                     session_exists_in_cache=session_id in app.papers_cache)
        return _jsonify_with_diag(payload, route="search_start")
    except Exception as e:
        log.exception("search_start failed")
        return _jsonify_with_diag({"error": str(e)}, status=500, route="search_start")

@app.route("/api/search_events", methods=["GET"])
def search_events_endpoint():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        # Return SSE error event for missing session_id
        def error_stream():
            error_payload = {
                "error": "session_id parameter required",
                "rid": getattr(g, "rid", None) or ""
            }
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'rid': getattr(g, 'rid', None) or ''}, ensure_ascii=False)}\n\n"
        
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": getattr(g, "rid", ""),
        }
        return Response(stream_with_context(error_stream()), headers=headers, status=400)
    
    if session_id not in app.papers_cache:
        available_sessions = list(app.papers_cache.keys())[:10]
        _log_with_rid("warning", "search_events_session_not_found", 
                     requested_session_id=session_id,
                     cache_size=len(app.papers_cache),
                     available_sessions=available_sessions)
        
        # Return SSE error event instead of JSON (since this is an SSE endpoint)
        def error_stream():
            error_payload = {
                "error": "Session not found",
                "requested_session_id": session_id,
                "cache_size": len(app.papers_cache),
                "available_sessions": available_sessions,
                "hint": "Session may have expired or been cleaned up. Start a new search.",
                "rid": getattr(g, "rid", None) or ""
            }
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'rid': getattr(g, 'rid', None) or ''}, ensure_ascii=False)}\n\n"
        
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": getattr(g, "rid", ""),
        }
        return Response(stream_with_context(error_stream()), headers=headers, status=404)

    def event_stream():
        sess = app.papers_cache.get(session_id)
        if not sess:
            log.error(f"[{getattr(g, 'rid', '-')}] [{session_id}] SSE stream started but session disappeared.")
            return

        mode = "together" if sess.get("search_together") else "separate"
        proteins: List[str] = sess.get("protein_names", [])
        q: "queue.Queue[Dict[str, Any]]" = sess["queue"]
        sess_rid = sess.get("rid") or getattr(g, "rid", None) or ""

        yield "retry: 60000\n\n"
        yield _sse_event("started", {"mode": mode, "proteins": proteins}, rid=sess_rid)
        log.info(f"[{sess_rid}] [{session_id}] SSE stream connected (mode={mode})")

        keepalive_deadline = time.time() + 20

        while True:
            try:
                item = q.get(timeout=1.0)
                if not isinstance(item, dict):
                    log.error(f"[{sess_rid}] [{session_id}] Invalid queue item type: {type(item)}")
                    continue
                
                t = item.get("type")
                if not t:
                    log.warning(f"[{sess_rid}] [{session_id}] Queue item missing 'type' field: {item}")
                    continue
                
                log.info(f"[{sess_rid}] [{session_id}] SSE event={t}")
                
                # Filter out 'type' and ensure all values are JSON-serializable
                event_data = {}
                for k, v in item.items():
                    if k != "type":
                        # Convert None to empty string, ensure other values are serializable
                        if v is None:
                            event_data[k] = ""
                        elif isinstance(v, (str, int, float, bool, list, dict)):
                            event_data[k] = v
                        else:
                            event_data[k] = str(v)
                
                yield _sse_event(t, event_data, rid=sess_rid)
                keepalive_deadline = time.time() + 20
                if t == "done":
                    log.info(f"[{sess_rid}] [{session_id}] SSE stream sent 'done' event and is closing.")
                    break
            except queue.Empty:
                if sess.get("status") in ("done", "error"):
                    log.warning(f"[{sess_rid}] [{session_id}] Worker finished but queue empty. Sending final 'done'.")
                    yield _sse_event("done", {}, rid=sess_rid)
                    break
                if time.time() >= keepalive_deadline:
                    yield ": keep-alive\n\n"
                    keepalive_deadline = time.time() + 20
                continue
            except Exception as e:
                log.error(f"[{sess_rid}] [{session_id}] SSE error: {e}")
                yield _sse_event("error", {"message": str(e)}, rid=sess_rid)
                break

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Request-Id": getattr(g, "rid", ""),
    }
    return Response(stream_with_context(event_stream()), headers=headers)

@app.route("/api/session_status", methods=["GET"])
def session_status_endpoint():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id or session_id not in app.papers_cache:
        return _jsonify_with_diag({"status": "missing"}, status=404, route="session_status")
    sess = app.papers_cache[session_id]
    return _jsonify_with_diag({
        "status": sess.get("status", "unknown"),
        "mode": "together" if sess.get("search_together") else "separate",
        "protein_names": sess.get("protein_names", []),
        "counts": {
            "total": len(sess.get("papers", [])) if sess.get("papers") is not None else None,
            "per_protein": {k: len(v or []) for k, v in (sess.get("papers_by_protein") or {}).items()} if sess.get("papers_by_protein") is not None else None,
        },
    }, route="session_status")

@app.route("/api/suggest", methods=["POST"])
def suggest_endpoint():
    try:
        _log_with_rid("info", "suggest_endpoint_called")
        # Guard: genealias required
        if load_gene_aliases is None or _normalize_aliases is None or _normalize_token is None or _is_gene_like is None or _match_score is None:
            _log_with_rid("warning", "suggest_genealias_unavailable")
            return _jsonify_with_diag({"suggestions": [], "warning": "Gene alias service unavailable"}, status=200, route="suggest")

        data = request.json or {}
        raw = data.get("proteins")
        if isinstance(raw, list):
            tokens = [str(x).strip() for x in raw if str(x).strip()]
        else:
            tokens = [t.strip() for t in str(raw or "").split(",") if t.strip()]
        _log_with_rid("info", "suggest_tokens_parsed", tokens=tokens, count=len(tokens))
        if not tokens:
            return _jsonify_with_diag({"suggestions": []}, route="suggest")

        # Try multiple possible locations for the TSV file
        # __file__ is api/src/index.py, so parent is api/src/
        current_dir = Path(__file__).parent  # api/src/
        parent_dir = current_dir.parent  # api/
        
        # Try current directory first (api/src/) where the file actually is
        possible_paths = [
            current_dir / "proteinatlas_search.tsv",  # api/src/proteinatlas_search.tsv (most likely)
            parent_dir / "proteinatlas_search.tsv",    # api/proteinatlas_search.tsv (fallback)
            current_dir / "proteinatlas_search_old.tsv",  # Old file if exists
        ]
        
        genes_df = None
        tsv_path = None
        for path in possible_paths:
            _log_with_rid("info", "suggest_trying_tsv_path", path=str(path), exists=path.exists())
            if path.exists():
                genes_df = load_gene_aliases(path)
                if genes_df is not None and not getattr(genes_df, "empty", True) and "Gene" in getattr(genes_df, "columns", []):
                    tsv_path = path
                    _log_with_rid("info", "suggest_tsv_loaded_successfully", path=str(path), rows=len(genes_df))
                    break
                else:
                    _log_with_rid("warning", "suggest_tsv_load_failed", path=str(path), 
                                 reason="empty_or_missing_columns")
        
        if genes_df is None or getattr(genes_df, "empty", True) or "Gene" not in getattr(genes_df, "columns", []):
            tried_paths = [str(p) for p in possible_paths]
            _log_with_rid("error", "suggest_gene_table_unavailable", 
                         tried_paths=tried_paths,
                         current_dir=str(current_dir),
                         parent_dir=str(parent_dir),
                         file_exists=[str(p.exists()) for p in possible_paths])
            return _jsonify_with_diag({"suggestions": [], "warning": "Gene alias table unavailable"}, status=200, route="suggest")

        _log_with_rid("info", "suggest_gene_table_loaded", rows=len(genes_df))
        results = []
        for tok in tokens:
            exact = False
            try:
                t = _normalize_token(tok)
                # Check if exact match in Gene column
                exact = not genes_df[genes_df["Gene"].astype(str).map(_normalize_token) == t].empty
                _log_with_rid("debug", "suggest_exact_check_gene", token=tok, normalized=t, exact_after_gene_check=exact)
                if not exact:
                    # Check aliases
                    for aliases in genes_df.get("Aliases", pd.Series([])).fillna("").astype(str):
                        for a in _normalize_aliases(aliases):
                            if _normalize_token(a) == t:
                                exact = True
                                _log_with_rid("debug", "suggest_exact_found_in_aliases", token=tok, alias=a)
                                break
                        if exact:
                            break
            except Exception as e:
                _log_with_rid("warning", "suggest_exact_check_error", token=tok, error=str(e))
                exact = False
            
            _log_with_rid("info", "suggest_exact_final", token=tok, exact=exact)

            variant_to_canonical: Dict[str, str] = {}
            rows_by_gene: Dict[str, Any] = {}
            try:
                for _, row in genes_df.iterrows():
                    canonical = str(row.get("Gene", "")).strip()
                    if not canonical:
                        continue
                    rows_by_gene[canonical] = row
                    variant_to_canonical[canonical] = canonical
                    for alias in _normalize_aliases(row.get("Aliases", "")):
                        if _is_gene_like(alias):
                            variant_to_canonical[alias] = canonical
            except Exception:
                pass

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

            try:
                from thefuzz import process, fuzz
                raw_matches = process.extract(norm_token, norm_variants, limit=50, scorer=fuzz.ratio)
            except Exception:
                # Fallback: simple scoring
                raw_matches = []
                for v in norm_variants:
                    score = 100 if norm_token == v else (80 if norm_token in v or v in norm_token else 0)
                    if score >= 60:
                        raw_matches.append((v, score))
                raw_matches = sorted(raw_matches, key=lambda x: x[1], reverse=True)[:50]

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

            MIN_SCORE = 60  # Lowered from 70 to be more lenient
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

            _log_with_rid("info", "suggest_token_result", 
                         token=tok, exact=exact, suggestions_count=len(details),
                         has_suggestions=len(details) > 0)

            results.append(
                {
                    "input": tok,
                    "exact": bool(exact),
                    "suggestions": [d["gene"] for d in details],
                    "details": details,
                }
            )

        _log_with_rid("info", "suggest_complete", results_count=len(results))
        return _jsonify_with_diag({"suggestions": results}, route="suggest")
    except Exception as e:
        _log_with_rid("error", "suggest_failed", error=str(e))
        log.exception("suggest failed")
        return _jsonify_with_diag({"error": str(e)}, status=500, route="suggest")

@app.route("/api/search", methods=["POST"])
def search_endpoint():
    try:
        data = request.json or {}
        _log_with_rid("info", "search_received", body_keys=list(data.keys()))

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key

        # Guard: ensure query_pubmed is available
        pubmed_err = _require_query_pubmed_available()
        if pubmed_err:
            _log_with_rid("error", "search_pubmed_unavailable", error=pubmed_err)
            return _jsonify_with_diag({"error": pubmed_err}, status=503, route="search")

        proteins_input = (data.get("proteins") or "").strip()
        if not proteins_input:
            return _jsonify_with_diag({"error": "No proteins specified"}, status=400, route="search")

        protein_names = [p.strip().upper() for p in proteins_input.split(",") if p.strip()]
        search_together = bool(data.get("search_proteins_together", False))
        search_terms = data.get("search_terms", []) or []
        question = data.get("question", "") or ""
        session_id = (data.get("session_id") or str(uuid.uuid4())).strip()
        fetch_papers_only = bool(data.get("fetch_papers_only", False))

        # Check if OpenAI key is available
        has_openai_key = bool(api_key and not _looks_like_google_api_key(api_key))
        
        if search_together:
            _log_with_rid("info", "search_query", together=True, proteins=protein_names, terms=search_terms, has_openai_key=has_openai_key)
            papers = query_pubmed(protein_names, True, search_terms, has_openai_key=has_openai_key)
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
                    "rid": getattr(g, "rid", None),
                    "protein_names": protein_names,
                    "question": question,
                    "search_together": True,
                    "timestamp": datetime.now().isoformat(),
                }
                return _jsonify_with_diag({"success": True, "mode": "together", "session_id": session_id, "proteins": protein_names, "papers": papers_for_response}, route="search")

            if not papers:
                return _jsonify_with_diag({"success": True, "mode": "together", "proteins": protein_names, "papers": [], "summary": "No papers found matching your search criteria."}, route="search")

            # Guard: summarization availability
            sum_err = _require_summarization_available()
            if sum_err:
                return _jsonify_with_diag({"success": True, "mode": "together", "proteins": protein_names, "papers": papers_for_response, "summary": None, "warning": sum_err}, route="search")

            uniprot_block = build_uniprot_function_block(protein_names)
            import sys
            openai_key_check = os.environ.get("OPENAI_API_KEY", "")
            print(f"[DEBUG] search_endpoint: About to call summarize_papers_with_llm (together mode)", flush=True)
            print(f"[DEBUG] search_endpoint: OPENAI_API_KEY present: {bool(openai_key_check)}, length: {len(openai_key_check)}", flush=True)
            sys.stdout.flush()
            summary = summarize_papers_with_llm(papers, protein_names, question, uniprot_block)
            print(f"[DEBUG] search_endpoint: summarize_papers_with_llm returned, length: {len(summary) if summary else 0}", flush=True)
            sys.stdout.flush()
            results_dir = ensure_results_directory()
            saved_file = save_results_to_txt(summary, "_".join(protein_names), results_dir)
            return _jsonify_with_diag({"success": True, "mode": "together", "proteins": protein_names, "papers": papers_for_response, "summary": summary, "saved_file": saved_file or None}, route="search")

        # separate
        _log_with_rid("info", "search_query", together=False, proteins=protein_names, terms=search_terms, has_openai_key=has_openai_key)
        all_results = []
        all_papers_data = []
        for protein in protein_names:
            papers = query_pubmed([protein], True, search_terms, has_openai_key=has_openai_key)
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
                    sum_err = _require_summarization_available()
                    if sum_err:
                        protein_summary = None
                        saved_file = None
                        warning = sum_err
                    else:
                        uniprot_block = build_uniprot_function_block([protein])
                        import sys
                        openai_key_check = os.environ.get("OPENAI_API_KEY", "")
                        print(f"[DEBUG] search_endpoint: About to call summarize_papers_with_llm (separate mode, protein: {protein})", flush=True)
                        print(f"[DEBUG] search_endpoint: OPENAI_API_KEY present: {bool(openai_key_check)}, length: {len(openai_key_check)}", flush=True)
                        sys.stdout.flush()
                        protein_summary = summarize_papers_with_llm(papers, [protein], question, uniprot_block)
                        print(f"[DEBUG] search_endpoint: summarize_papers_with_llm returned for {protein}, length: {len(protein_summary) if protein_summary else 0}", flush=True)
                        sys.stdout.flush()
                        results_dir = ensure_results_directory()
                        saved_file = save_results_to_txt(protein_summary, protein, results_dir)
                        warning = None
                else:
                    protein_summary = f"No papers found for {protein}."
                    saved_file = None
                    warning = None
                entry = {"protein": protein, "papers": papers_for_response, "summary": protein_summary, "saved_file": saved_file}
                if warning:
                    entry["warning"] = warning
                all_results.append(entry)

        if fetch_papers_only:
            app.papers_cache[session_id] = {
                "papers_by_protein": {r["protein"]: all_papers_data[i]["papers"] for i, r in enumerate(all_results)},
                "rid": getattr(g, "rid", None),
                "protein_names": protein_names,
                "question": question,
                "search_together": False,
                "timestamp": datetime.now().isoformat(),
            }
            return _jsonify_with_diag({"success": True, "mode": "separate", "session_id": session_id, "results": all_results}, route="search")

        return _jsonify_with_diag({"success": True, "mode": "separate", "results": all_results}, route="search")
    except Exception as e:
        log.exception("search failed")
        return _jsonify_with_diag({"error": str(e)}, status=500, route="search")

@app.route("/api/summarize", methods=["POST"])
def summarize_endpoint():
    import sys
    print("[DEBUG] ========== SUMMARIZE ENDPOINT CALLED ==========", flush=True)
    sys.stdout.flush()
    try:
        data = request.json or {}
        print(f"[DEBUG] summarize_endpoint: Received data keys: {list(data.keys())}", flush=True)
        sys.stdout.flush()
        _log_with_rid("info", "summarize_received", body_keys=list(data.keys()))
        session_id = (data.get("session_id") or "").strip()
        if not session_id:
            return _jsonify_with_diag({"error": "Session ID is required"}, status=400, route="summarize")
        
        # Enhanced session lookup with better error reporting
        if session_id not in app.papers_cache:
            available_sessions = list(app.papers_cache.keys())[:10]  # Show first 10 for debugging
            all_sessions_with_timestamps = [
                {
                    "session_id": sid,
                    "status": sess.get("status", "unknown"),
                    "timestamp": sess.get("timestamp", ""),
                    "proteins": sess.get("protein_names", []),
                }
                for sid, sess in list(app.papers_cache.items())[:10]
            ]
            _log_with_rid("warning", "summarize_session_not_found", 
                         requested_session_id=session_id, 
                         cache_size=len(app.papers_cache),
                         available_sessions=available_sessions,
                         available_sessions_detail=all_sessions_with_timestamps)
            return _jsonify_with_diag({
                "error": "Session expired or not found",
                "requested_session_id": session_id,
                "cache_size": len(app.papers_cache),
                "available_sessions": available_sessions,
                "hint": "Session may have been created on a different server instance. Try starting a new search.",
                "note": "If using multiple server instances, sessions are stored in-memory and not shared between instances"
            }, status=404, route="summarize")

        api_key = (data.get("api_key") or "").strip()
        google_api_key = (data.get("google_api_key") or "").strip()
        
        # If no API key provided in request, try to get it from session
        if not api_key and session_id in app.papers_cache:
            cached_data = app.papers_cache[session_id]
            stored_api_key = cached_data.get("api_key")
            print(f"[DEBUG] summarize_endpoint: Checking session for stored key - found: {bool(stored_api_key)}, length: {len(stored_api_key) if stored_api_key else 0}", flush=True)
            sys.stdout.flush()
            if stored_api_key:
                api_key = stored_api_key
                print(f"[DEBUG] summarize_endpoint: Using stored API key from session, length: {len(api_key)}", flush=True)
                sys.stdout.flush()
                _log_with_rid("info", "summarize_using_stored_api_key", key_length=len(api_key) if api_key else 0)
            else:
                print("[DEBUG] summarize_endpoint: No stored API key in session", flush=True)
                sys.stdout.flush()
        else:
            print(f"[DEBUG] summarize_endpoint: api_key from request: {bool(api_key)}, session_id in cache: {session_id in app.papers_cache if session_id else False}", flush=True)
            sys.stdout.flush()
        
        # Clear OpenAI key from environment first to avoid persistence issues
        if "OPENAI_API_KEY" in os.environ:
            print(f"[DEBUG] summarize_endpoint: Clearing existing OPENAI_API_KEY from environment")
            del os.environ["OPENAI_API_KEY"]
        
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
            print(f"[DEBUG] summarize_endpoint: Set GOOGLE_API_KEY, length: {len(google_api_key)}")
            _log_with_rid("info", "summarize_set_google_key", key_length=len(google_api_key))
        if api_key:
            if _looks_like_google_api_key(api_key):
                os.environ["GOOGLE_API_KEY"] = api_key
                print(f"[DEBUG] summarize_endpoint: Set GOOGLE_API_KEY from api_key, length: {len(api_key)}")
                _log_with_rid("info", "summarize_set_google_key_from_api_key", key_length=len(api_key))
            else:
                os.environ["OPENAI_API_KEY"] = api_key
                print(f"[DEBUG] summarize_endpoint: Set OPENAI_API_KEY, length: {len(api_key)}, preview: {api_key[:10]}...")
                _log_with_rid("info", "summarize_set_openai_key", key_length=len(api_key))
        else:
            print("[DEBUG] summarize_endpoint: No api_key provided (neither in request nor in session)", flush=True)
            sys.stdout.flush()
            _log_with_rid("info", "summarize_no_openai_key_will_use_gemma")
        
        # Verify key is set before calling summarization
        final_openai_key = os.environ.get("OPENAI_API_KEY", "")
        print(f"[DEBUG] summarize_endpoint: Final OPENAI_API_KEY check - present: {bool(final_openai_key)}, length: {len(final_openai_key)}", flush=True)
        sys.stdout.flush()

        # Guard: summarization availability
        sum_err = _require_summarization_available()
        if sum_err:
            _log_with_rid("error", "summarize_unavailable", error=sum_err)
            return _jsonify_with_diag({"error": sum_err}, status=503, route="summarize")

        cached_data = app.papers_cache[session_id]
        # Log session structure for debugging
        _log_with_rid("info", "summarize_session_found", 
                     session_id=session_id,
                     has_papers="papers" in cached_data and cached_data.get("papers") is not None,
                     papers_count=len(cached_data.get("papers", [])) if cached_data.get("papers") else 0,
                     has_papers_by_protein="papers_by_protein" in cached_data and cached_data.get("papers_by_protein") is not None,
                     search_together=cached_data.get("search_together", False),
                     has_stored_api_key=bool(cached_data.get("api_key")),
                     has_openai_key_flag=cached_data.get("has_openai_key", False))
        question = data.get("question") or cached_data.get("question", "")
        search_together = cached_data.get("search_together", False)

        if search_together:
            papers = cached_data.get("papers", [])
            if not papers:
                return _jsonify_with_diag({"success": True, "summary": "No papers found to summarize.", "saved_file": None}, route="summarize")
            protein_names = cached_data.get("protein_names", [])
            uniprot_block = build_uniprot_function_block(protein_names)
            # Log API key status before calling summarization
            openai_key_check = os.environ.get("OPENAI_API_KEY", "")
            print(f"[DEBUG] summarize_endpoint: About to call summarize_papers_with_llm", flush=True)
            print(f"[DEBUG] summarize_endpoint: OPENAI_API_KEY present: {bool(openai_key_check)}, length: {len(openai_key_check)}", flush=True)
            sys.stdout.flush()
            _log_with_rid("info", "summarize_calling_llm", 
                         has_openai_key=bool(openai_key_check),
                         openai_key_length=len(openai_key_check) if openai_key_check else 0)
            summary = summarize_papers_with_llm(papers, protein_names, question, uniprot_block)
            print(f"[DEBUG] summarize_endpoint: summarize_papers_with_llm returned, length: {len(summary) if summary else 0}", flush=True)
            sys.stdout.flush()
            results_dir = ensure_results_directory()
            saved_file = save_results_to_txt(summary, "_".join(protein_names), results_dir)
            return _jsonify_with_diag({"success": True, "summary": summary, "saved_file": saved_file}, route="summarize")
        else:
            all_papers_data = cached_data.get("papers_by_protein", {})
            print(f"[DEBUG] summarize_endpoint: all_papers_data type: {type(all_papers_data)}, keys: {list(all_papers_data.keys()) if isinstance(all_papers_data, dict) else 'not a dict'}", flush=True)
            sys.stdout.flush()
            
            # Handle case where papers_by_protein might be a list instead of dict
            if isinstance(all_papers_data, list):
                print(f"[DEBUG] summarize_endpoint: papers_by_protein is a list, converting to dict", flush=True)
                sys.stdout.flush()
                # Convert list format to dict format
                protein_names_list = cached_data.get("protein_names", [])
                all_papers_data_dict = {}
                for i, paper_list in enumerate(all_papers_data):
                    if i < len(protein_names_list):
                        all_papers_data_dict[protein_names_list[i]] = paper_list if isinstance(paper_list, list) else []
                all_papers_data = all_papers_data_dict
            
            summaries = []
            if not isinstance(all_papers_data, dict):
                error_msg = f"papers_by_protein is not a dict after conversion, got {type(all_papers_data)}"
                print(f"[DEBUG] summarize_endpoint: ERROR - {error_msg}", flush=True)
                sys.stdout.flush()
                log.error(f"summarize_endpoint: {error_msg}")
                return _jsonify_with_diag({"error": error_msg}, status=500, route="summarize")
            
            for protein, papers in all_papers_data.items():
                print(f"[DEBUG] summarize_endpoint: Processing protein {protein}, papers count: {len(papers) if isinstance(papers, list) else 'not a list'}", flush=True)
                sys.stdout.flush()
                
                if not papers:
                    summaries.append({"protein": protein, "summary": f"No papers found for {protein}.", "saved_file": None})
                    continue
                
                if not isinstance(papers, list):
                    error_msg = f"papers for {protein} is not a list, got {type(papers)}"
                    print(f"[DEBUG] summarize_endpoint: ERROR - {error_msg}", flush=True)
                    sys.stdout.flush()
                    log.error(f"summarize_endpoint: {error_msg}")
                    summaries.append({"protein": protein, "summary": f"Error: {error_msg}", "saved_file": None})
                    continue
                
                try:
                    uniprot_block = build_uniprot_function_block([protein])
                    # Log API key status before calling summarization
                    openai_key_check = os.environ.get("OPENAI_API_KEY", "")
                    _log_with_rid("info", "summarize_calling_llm_separate", 
                                 protein=protein,
                                 has_openai_key=bool(openai_key_check),
                                 openai_key_length=len(openai_key_check) if openai_key_check else 0)
                    protein_summary = summarize_papers_with_llm(papers, [protein], question, uniprot_block)
                    results_dir = ensure_results_directory()
                    saved_file = save_results_to_txt(protein_summary, protein, results_dir)
                    summaries.append({"protein": protein, "summary": protein_summary, "saved_file": saved_file})
                except Exception as e:
                    error_msg = f"Error summarizing {protein}: {str(e)}"
                    print(f"[DEBUG] summarize_endpoint: EXCEPTION for {protein}: {e}", flush=True)
                    import traceback
                    print(f"[DEBUG] summarize_endpoint: Traceback: {traceback.format_exc()}", flush=True)
                    sys.stdout.flush()
                    log.exception(f"summarize_endpoint: Error summarizing {protein}")
                    summaries.append({"protein": protein, "summary": f"Error: {error_msg}", "saved_file": None})
            return _jsonify_with_diag({"success": True, "summaries": summaries}, route="summarize")
    except Exception as e:
        log.exception("summarize failed")
        return _jsonify_with_diag({"error": str(e)}, status=500, route="summarize")

@app.route("/", methods=["GET"])
def root():
    import sys
    print("[DEBUG] Root endpoint called - testing console output", flush=True)
    sys.stdout.flush()
    return _jsonify_with_diag({"status": "ok", "message": "ProtSearch API", "version": "1.0"}, route="root")

@app.route("/health", methods=["GET"])
def health_check():
    return _jsonify_with_diag({
        "status": "ok",
        "message": "ProtSearch API is running",
        "cache_size": len(app.papers_cache),
    }, route="health")

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
def cleanup_expired_sessions():
    current_time = datetime.now()
    expired_sessions: List[str] = []
    # Increased timeout to 3 hours (10800 seconds) to allow time for summarization
    SESSION_TIMEOUT_SECONDS = 10800  # 3 hours
    
    for session_id, data in list(app.papers_cache.items()):
        try:
            timestamp_str = data.get("timestamp", "")
            if not timestamp_str:
                # Only remove sessions without timestamps if they're very old (safety check)
                expired_sessions.append(session_id)
                continue
            
            timestamp = datetime.fromisoformat(timestamp_str)
            elapsed = current_time - timestamp
            status = data.get("status", "unknown")
            
            # Don't clean up sessions that are still running or recently completed
            # Only clean up if they're old AND in a final state (done/error) or queued for too long
            if elapsed.total_seconds() > SESSION_TIMEOUT_SECONDS:
                # Session is old - check if it's safe to remove
                if status in ("done", "error"):
                    # Completed sessions can be removed after timeout
                    expired_sessions.append(session_id)
                elif status == "queued" and elapsed.total_seconds() > 1800:  # 30 minutes
                    # Queued sessions that haven't started in 30 minutes are likely stuck
                    expired_sessions.append(session_id)
                elif status == "running":
                    # Running sessions get extra time - only remove if very old (4 hours)
                    if elapsed.total_seconds() > 14400:  # 4 hours
                        expired_sessions.append(session_id)
                else:
                    # Unknown status, remove if old
                    expired_sessions.append(session_id)
        except Exception as e:
            log.warning(f"[cleanup] Error checking session {session_id}: {e}")
            # Only remove on error if it's very old (safety)
            try:
                timestamp_str = data.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    elapsed = current_time - timestamp
                    if elapsed.total_seconds() > SESSION_TIMEOUT_SECONDS * 2:  # 6 hours
                        expired_sessions.append(session_id)
            except:
                pass
    
    for session_id in expired_sessions:
        if session_id in app.papers_cache:
            sess_data = app.papers_cache[session_id]
            status = sess_data.get("status", "unknown")
            timestamp_str = sess_data.get("timestamp", "")
            _log_with_rid("info", "cleanup_removing_session", 
                         session_id=session_id,
                         status=status,
                         timestamp=timestamp_str)
            del app.papers_cache[session_id]
            log.info(f"[cleanup] expired session removed session_id={session_id} status={status}")

@app.route("/api/cleanup", methods=["POST"])
def cleanup_endpoint():
    cleanup_expired_sessions()
    return _jsonify_with_diag({"success": True, "message": "Cache cleaned up", "remaining_sessions": len(app.papers_cache)}, route="cleanup")

@app.route("/api/clear_all_sessions", methods=["POST"])
def clear_all_sessions_endpoint():
    """Clear all sessions - useful for testing or forcing fresh start"""
    count = len(app.papers_cache)
    for session_id in list(app.papers_cache.keys()):
        sess = app.papers_cache.get(session_id)
        if sess and "queue" in sess:
            try:
                while not sess["queue"].empty():
                    sess["queue"].get_nowait()
            except:
                pass
        del app.papers_cache[session_id]
    _log_with_rid("info", "clear_all_sessions", cleared_count=count)
    return _jsonify_with_diag({"success": True, "message": f"Cleared {count} sessions", "remaining_sessions": len(app.papers_cache)}, route="clear_all_sessions")

def start_cleanup_scheduler():
    def cleanup_task():
        while True:
            # Run cleanup every 30 minutes instead of every hour
            time.sleep(1800)  # 30 minutes
            try:
                cleanup_expired_sessions()
            except Exception as e:
                log.error(f"[cleanup_scheduler] Error in cleanup task: {e}")
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    log.info("Cleanup scheduler started (runs every 30 minutes, sessions expire after 3 hours)")

start_cleanup_scheduler()

# Log successful startup
log.info("ProtSearch API initialized successfully")
log.info(f"Cache initialized with {len(app.papers_cache)} sessions")
log.info(f"Service status on startup: {json.dumps(_service_status())}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    log.info(f"Starting Flask development server on port {port}")
    app.run(debug=True, host="0.0.0.0", port=port, threaded=True)