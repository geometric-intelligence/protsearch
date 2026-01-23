from typing import Optional, Dict, Any
import os, time, logging, requests, tiktoken

log = logging.getLogger("protsearch")

try:
    from openai import OpenAI as _OpenAIClient  # type: ignore
    _HAS_OPENAI = True
except Exception:
    _OpenAIClient = None  # type: ignore
    _HAS_OPENAI = False

def setup_openai() -> Optional[object]:
    print(f"[DEBUG] setup_openai: _HAS_OPENAI = {_HAS_OPENAI}")
    if not _HAS_OPENAI:
        print("[DEBUG] setup_openai: OpenAI library not available")
        return None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    print(f"[DEBUG] setup_openai: API key from env - present: {bool(api_key)}, length: {len(api_key) if api_key else 0}")
    if not api_key:
        print("[DEBUG] setup_openai: No API key found in environment")
        return None
    try:
        print("[DEBUG] setup_openai: Attempting to create OpenAI client")
        client = _OpenAIClient(api_key=api_key)  # type: ignore
        print("[DEBUG] setup_openai: OpenAI client created successfully")
        return client
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"[DEBUG] setup_openai: EXCEPTION - {error_type}: {error_msg}")
        log.warning(f"Failed to init OpenAI client: {e}")
        return None

def generate_with_gemini_rest(prompt: str, model_name: str, api_key: str, timeout: int = 120, max_retries: int = 4) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload: Dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    backoff = 0.5
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(backoff); backoff *= 2; continue
            if resp.status_code == 404:
                log.error(f"Gemini REST 404 (model): {url}")
                return ""
            resp.raise_for_status()
            data = resp.json()
            candidates = (data or {}).get("candidates") or []
            if candidates:
                content = candidates[0].get("content") or {}
                parts = content.get("parts") or []
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
                return "".join(texts).strip()
            return ""
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(backoff); backoff *= 2; continue
            log.error(f"Gemini REST failed after retries: {e}")
            return ""

def count_tokens(text: str) -> int:
    try:
        enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
        return len(enc.encode(text or ""))
    except Exception:
        return int(len((text or "").split()) * 1.3)