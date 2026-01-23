from typing import List, Optional, Dict
import re, html, requests, logging
from pathlib import Path
from services.genealias import load_gene_aliases, find_gene_and_aliases

log = logging.getLogger("protsearch")
_UNIPROT_CACHE: Dict[str, str] = {}

def _strip_tags(text: str) -> str:
    if not text:
        return ""
    t = html.unescape(text)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"PubMed:\s*\d+", "", t)
    return t

def _uniprot_accession_for_symbol(symbol: str, genes_df) -> Optional[str]:
    if genes_df is None:
        return None
    try:
        sym, _aliases, _desc = find_gene_and_aliases(symbol, genes_df)
        df = genes_df[genes_df["Gene"].astype(str).str.upper() == str(sym).upper()].head(1)
        if df.empty:
            return None
        acc = str(df.iloc[0].get("Uniprot", "")).strip()
        if not acc:
            return None
        # Split and get first part, but handle empty list case
        acc_parts = re.split(r"[;,\s]+", acc)
        if not acc_parts or not acc_parts[0]:
            return None
        acc = acc_parts[0].strip()
        return acc or None
    except Exception:
        return None

def fetch_uniprot_function(accession: str, timeout: int = 10) -> str:
    acc = (accession or "").strip()
    if not acc:
        return ""
    if acc in _UNIPROT_CACHE:
        log.debug(f"fetch_uniprot_function: Using cached data for {acc}")
        return _UNIPROT_CACHE[acc]
    log.info(f"fetch_uniprot_function: Fetching from UniProt website for accession {acc}")
    headers = {"User-Agent": "ProtSearch/1.0 (contact: you@example.com)", "Accept": "application/json"}
    # JSON
    try:
        url_json = f"https://rest.uniprot.org/uniprotkb/{acc}.json"
        rj = requests.get(url_json, headers=headers, timeout=timeout)
        if rj.status_code == 200 and "application/json" in rj.headers.get("Content-Type", ""):
            data = rj.json()
            function_texts = []
            for c in data.get("comments", []) or []:
                if c.get("commentType") == "FUNCTION":
                    for t in c.get("texts", []) or []:
                        v = t.get("value") or ""
                        if isinstance(v, str) and v.strip():
                            function_texts.append(v.strip())
            if function_texts:
                txt = _strip_tags(" ".join(function_texts))
                _UNIPROT_CACHE[acc] = txt
                return txt
    except Exception:
        pass
    # HTML fallback
    try:
        url_html = f"https://www.uniprot.org/uniprotkb/{acc}/entry"
        rh = requests.get(url_html, headers={**headers, "Accept": "text/html,application/xhtml+xml"}, timeout=timeout)
        if rh.status_code == 200 and "text/html" in rh.headers.get("Content-Type", ""):
            html_text = rh.text or ""
            mfunc = re.search(r'<section[^>]+id=["\']function["\'][\s\S]*?<div class="text-block">([\s\S]*?)</div>', html_text, flags=re.I)
            if mfunc:
                txt = _strip_tags(mfunc.group(1))
            else:
                mmeta = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html_text, flags=re.I)
                txt = _strip_tags(mmeta.group(1)) if mmeta else ""
            _UNIPROT_CACHE[acc] = txt
            return txt
    except Exception:
        pass
    _UNIPROT_CACHE[acc] = ""
    return ""

def build_uniprot_function_block(protein_names: List[str]) -> str:
    if not protein_names:
        log.info("build_uniprot_function_block: No protein names provided")
        return ""
    project_root = Path(__file__).resolve().parents[1]
    tsv_path = project_root / "proteinatlas_search.tsv"
    genes_df = load_gene_aliases(tsv_path)
    seen: set[str] = set()
    parts: List[str] = []
    log.info(f"build_uniprot_function_block: Fetching UniProt functions for {protein_names}")
    for raw in protein_names:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        acc = _uniprot_accession_for_symbol(sym, genes_df)
        if not acc:
            log.warning(f"build_uniprot_function_block: No UniProt accession found for {sym}")
            continue
        log.info(f"build_uniprot_function_block: Fetching UniProt function for {sym} (accession: {acc})")
        fn = fetch_uniprot_function(acc)
        if not fn:
            log.warning(f"build_uniprot_function_block: No UniProt function data retrieved for {sym} ({acc})")
            continue
        fn_short = fn if len(fn) <= 1500 else (fn[:1400].rsplit(" ", 1)[0] + "...")
        parts.append(f"{sym} ({acc}): {fn_short}")
        log.info(f"build_uniprot_function_block: Successfully retrieved UniProt function for {sym} ({len(fn)} chars)")
    result = "\n".join(parts).strip()
    if result:
        log.info(f"build_uniprot_function_block: Returning UniProt function block ({len(result)} chars) for {len(parts)} protein(s)")
    else:
        log.warning(f"build_uniprot_function_block: No UniProt function data retrieved for any of {protein_names}")
    return result