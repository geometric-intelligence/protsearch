import re
from typing import List, Tuple
import logging
import spacy
import tiktoken

log = logging.getLogger("protsearch")

_NLP = None
_ENC = None

def _get_nlp():
    global _NLP
    if _NLP is None:
        # Try to load scientific model first, fallback to web model
        model_names = ["en_core_sci_sm", "en_core_web_sm"]
        for model_name in model_names:
            try:
                _NLP = spacy.load(model_name)
                log.info(f"Loaded spacy model: {model_name}")
                if "sentencizer" not in _NLP.pipe_names:
                    _NLP.add_pipe("sentencizer", first=True)
                break
            except OSError:
                log.warning(f"Failed to load spacy model: {model_name}, trying next...")
                continue
        
        # If all models fail, create a blank model as fallback
        if _NLP is None:
            log.warning("All spacy models failed to load, using blank model")
            try:
                _NLP = spacy.blank("en")
                _NLP.add_pipe("sentencizer", first=True)
            except Exception as e:
                log.error(f"Failed to create blank spacy model: {e}")
                raise
    return _NLP

def _enc():
    global _ENC
    if _ENC is None:
        _ENC = tiktoken.get_encoding("cl100k_base")
    return _ENC

def rough_tokens(text: str) -> int:
    try:
        return len(_enc().encode(text or ""))
    except Exception:
        return max(1, len(text or "") // 4)

def to_sentences(text: str, max_len_chars: int = 2000) -> List[str]:
    doc = _get_nlp()(text or "")
    out: List[str] = []
    for s in doc.sents:
        st = s.text.strip()
        if not st:
            continue
        if len(st) <= max_len_chars:
            out.append(st)
        else:
            chunks = re.split(r"(?<=[\.\?\!])\s+", st)
            out.extend([c for c in chunks if c.strip()])
    return out

def chunk_sentences(sentences: List[str], max_tokens: int = 400, overlap: int = 80) -> List[str]:
    chunks: List[str] = []
    cur: List[str] = []
    cur_tok = 0
    for s in sentences:
        st = s.strip()
        if not st:
            continue
        t = rough_tokens(st)
        if cur and cur_tok + t > max_tokens:
            chunks.append(" ".join(cur).strip())
            tail: List[str] = []
            tail_tok = 0
            for ss in reversed(cur):
                tt = rough_tokens(ss)
                if tail_tok + tt > overlap:
                    break
                tail.insert(0, ss)
                tail_tok += tt
            cur = tail
            cur_tok = sum(rough_tokens(x) for x in cur)
        cur.append(st)
        cur_tok += t
    if cur:
        chunks.append(" ".join(cur).strip())
    return chunks

def sectionize(text: str) -> List[Tuple[str, str]]:
    parts: List[Tuple[str, str]] = []
    current_h = "BODY"
    buf: List[str] = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*(abstract|introduction|methods?|results?|discussion|conclusion|limitations)\s*:?\s*$", line.strip(), flags=re.I):
            if buf:
                parts.append((current_h, "\n".join(buf).strip()))
                buf = []
            current_h = line.strip().upper()
        else:
            buf.append(line)
    if buf:
        parts.append((current_h, "\n".join(buf).strip()))
    if not parts:
        parts = [("BODY", text or "")]
    return parts