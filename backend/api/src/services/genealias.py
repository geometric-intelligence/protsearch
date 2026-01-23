from typing import List, Dict, Any, Optional
import re
import pandas as pd
from thefuzz import process, fuzz

def load_gene_aliases(file_path) -> Optional[pd.DataFrame]:
    try:
        from pathlib import Path
        path_obj = Path(file_path) if not isinstance(file_path, Path) else file_path
        
        # Check if file exists
        if not path_obj.exists():
            import logging
            log = logging.getLogger("protsearch")
            log.warning(f"Gene alias file not found at: {path_obj}")
            return None
        
        genes_df = pd.read_csv(path_obj, sep="\t")
        
        # Check if dataframe is empty
        if genes_df.empty:
            import logging
            log = logging.getLogger("protsearch")
            log.warning(f"Gene alias file is empty: {path_obj}")
            return None
        
        cols = {c.strip(): c for c in genes_df.columns}
        if "Aliases" not in cols and "Gene synonym" in cols:
            genes_df["Aliases"] = genes_df["Gene synonym"].fillna("")
        if "Gene name" not in cols and "Gene description" in cols:
            genes_df["Gene name"] = genes_df["Gene description"].fillna("")
        for col in ("Gene", "Aliases", "Gene name"):
            if col not in genes_df.columns:
                genes_df[col] = ""
        if "Uniprot" not in genes_df.columns:
            genes_df["Uniprot"] = ""
        genes_df["Gene"] = genes_df["Gene"].astype(str)
        genes_df["Aliases"] = genes_df["Aliases"].astype(str)
        genes_df["Gene name"] = genes_df["Gene name"].astype(str)
        genes_df["Uniprot"] = genes_df["Uniprot"].astype(str)
        
        import logging
        log = logging.getLogger("protsearch")
        log.info(f"Successfully loaded gene alias file: {path_obj}, rows: {len(genes_df)}")
        return genes_df
    except Exception as e:
        import logging
        log = logging.getLogger("protsearch")
        log.exception(f"Failed to load gene alias file {file_path}: {e}")
        return None

def _normalize_aliases(aliases: Any) -> List[str]:
    if not isinstance(aliases, str):
        return []
    return [a.strip() for a in aliases.split(",") if isinstance(a, str) and a.strip()]

def _normalize_token(s: str) -> str:
    s = (s or "").strip().upper()
    s = re.sub(r"[^A-Z0-9\-\._]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    return s

def _is_gene_like(s: str) -> bool:
    s = (s or "").strip()
    if " " in s:
        return False
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9\-\._]{1,14}$", s))

def _alpha_prefix(s: str) -> str:
    m = re.match(r"^[A-Za-z]+", s)
    return m.group(0) if m else ""

def _match_score(a: str, b: str) -> int:
    na, nb = _normalize_token(a), _normalize_token(b)
    base = fuzz.ratio(na, nb)
    ld = abs(len(na) - len(nb))
    penalty = 0
    if ld >= 3:
        penalty += min(15, 5 * (ld - 2))
    pa, pb = _alpha_prefix(na), _alpha_prefix(nb)
    if (na[:1] != nb[:1]) and not (pa and pb and pa[0] == pb[0]):
        penalty += 10
    return max(0, base - penalty)

def find_gene_and_aliases(gene_name: str, genes_df: pd.DataFrame):
    if genes_df is None or genes_df.empty:
        return gene_name, "", ""
    exact_match = genes_df[genes_df["Gene"].astype(str).str.lower() == str(gene_name).lower()]
    if not exact_match.empty:
        row = exact_match.iloc[0]
        return row["Gene"], row.get("Aliases", ""), row.get("Gene name", "")
    norm_input = _normalize_token(gene_name)
    best_row = None
    for _, row in genes_df.iterrows():
        for alias in _normalize_aliases(row.get("Aliases", "")):
            if _normalize_token(alias) == norm_input:
                best_row = row
                break
        if best_row is not None:
            break
    if best_row is not None:
        return best_row["Gene"], best_row.get("Aliases", ""), best_row.get("Gene name", "")
    variant_to_canonical: Dict[str, str] = {}
    rows_by_gene: Dict[str, Any] = {}
    for _, row in genes_df.iterrows():
        symbol = str(row.get("Gene", "")).strip()
        if not symbol:
            continue
        rows_by_gene[symbol] = row
        variant_to_canonical[symbol] = symbol
        for alias in _normalize_aliases(row.get("Aliases", "")):
            if _is_gene_like(alias):
                variant_to_canonical[alias] = symbol
    if not variant_to_canonical:
        return gene_name, "", ""
    variant_names = list(variant_to_canonical.keys())
    norm_map: Dict[str, str] = {name: _normalize_token(name) for name in variant_names}
    reverse_norm: Dict[str, List[str]] = {}
    for original, normed in norm_map.items():
        reverse_norm.setdefault(normed, []).append(original)
    norm_variants = list(reverse_norm.keys())
    norm_token = _normalize_token(gene_name)
    if not norm_token:
        return gene_name, "", ""
    raw_matches = process.extract(norm_token, norm_variants, limit=20, scorer=fuzz.ratio)
    best_by_canonical: Dict[str, int] = {}
    for norm_name, _ in raw_matches:
        for original in reverse_norm.get(norm_name, []):
            canonical = variant_to_canonical.get(original)
            if not canonical:
                continue
            score = _match_score(gene_name, original)
            if score > best_by_canonical.get(canonical, -1):
                best_by_canonical[canonical] = score
    MIN_SCORE = 70
    best_items = [(g, s) for g, s in best_by_canonical.items() if s >= MIN_SCORE]
    if not best_items:
        return gene_name, "", ""
    best_items.sort(key=lambda x: x[1], reverse=True)
    if not best_items:
        return gene_name, "", ""
    best_symbol = best_items[0][0]
    row = rows_by_gene.get(best_symbol)
    if row is None:
        return best_symbol, "", ""
    return row["Gene"], row.get("Aliases", ""), row.get("Gene name", "")

def _variantize_token(term: str, max_variants: int = 6) -> List[str]:
    t = (term or "").strip()
    if not t:
        return []
    variants = {t}
    if "_" in t:
        variants.update({t.replace("_", "-"), t.replace("_", " "), t.replace("_", "")})
    if "-" in t:
        variants.update({t.replace("-", "_"), t.replace("-", " "), t.replace("-", "")})
    if "." in t:
        variants.update({t.replace(".", "-"), t.replace(".", "_"), t.replace(".", " "), t.replace(".", "")})
    cleaned = []
    seen = set()
    for v in variants:
        v2 = re.sub(r"\s{2,}", " ", v).strip()
        if 1 <= len(v2) <= 32:
            key = v2.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(v2)
    cleaned.sort(key=len)
    return cleaned[:max_variants]

def create_search_query(symbol: str, aliases: str, description: str) -> str:
    base_terms: List[str] = [symbol]
    if aliases and isinstance(aliases, str):
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
        base_terms.extend(alias_list[:3])
    all_terms: List[str] = []
    seen = set()
    for term in base_terms:
        for v in _variantize_token(term):
            key = v.lower()
            if key not in seen:
                seen.add(key)
                all_terms.append(v)
    return " OR ".join([f'"{t}"[All Fields]' for t in all_terms])