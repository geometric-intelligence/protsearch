from typing import List, Dict, Optional, Any
import requests
import time
import logging
from xml.etree import ElementTree as ET
from services.confighelper import load_config
from services.genealias import load_gene_aliases, find_gene_and_aliases
from pathlib import Path

log = logging.getLogger("protsearch")

EUROPE_PMC_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

def parse_europepmc_result(result_elem) -> Optional[Dict]:
    """Parse Europe PMC XML result element into structured paper info."""
    if result_elem is None:
        return None
    
    paper_info: Dict[str, str] = {
        "PMID": "",
        "Title": "",
        "Authors": "",
        "Journal": "",
        "Year": "",
        "Abstract": "",
        "DOI": "",
        "PMCID": "",  # PubMed Central ID (needed for full text access)
        "FullText": ""  # Full text content (only fetched for OpenAI models)
    }
    
    # Europe PMC XML doesn't use namespaces for result elements, so we can search directly
    # Extract fields from XML
    pmid_elem = result_elem.find("pmid")
    if pmid_elem is not None and pmid_elem.text:
        paper_info["PMID"] = pmid_elem.text.strip()
    else:
        # Try alternative ID if no PMID (for non-MED sources like preprints)
        id_elem = result_elem.find("id")
        if id_elem is not None and id_elem.text:
            paper_info["PMID"] = id_elem.text.strip()
    
    title_elem = result_elem.find("title")
    if title_elem is not None and title_elem.text:
        paper_info["Title"] = title_elem.text.strip()
    
    author_elem = result_elem.find("authorString")
    if author_elem is not None and author_elem.text:
        paper_info["Authors"] = author_elem.text.strip()
    
    journal_elem = result_elem.find("journalTitle")
    if journal_elem is not None and journal_elem.text:
        paper_info["Journal"] = journal_elem.text.strip()
    
    year_elem = result_elem.find("pubYear")
    if year_elem is not None and year_elem.text:
        paper_info["Year"] = year_elem.text.strip()
    
    # Abstract might be in abstractText or abstract field depending on resultType
    abstract_elem = result_elem.find("abstractText")
    if abstract_elem is None:
        abstract_elem = result_elem.find("abstract")
    if abstract_elem is not None:
        # Abstract can be a single text node or have multiple paragraphs
        abstract_text = abstract_elem.text or ""
        # Also check for paragraph elements within abstract
        for para in abstract_elem.findall("p"):
            if para.text:
                abstract_text += " " + para.text
        if abstract_text.strip():
            paper_info["Abstract"] = abstract_text.strip()
    
    doi_elem = result_elem.find("doi")
    if doi_elem is not None and doi_elem.text:
        paper_info["DOI"] = doi_elem.text.strip()
    
    # Get PMCID (PubMed Central ID) - needed for full text access
    pmcid_elem = result_elem.find("pmcid")
    if pmcid_elem is not None and pmcid_elem.text:
        paper_info["PMCID"] = pmcid_elem.text.strip()
    else:
        # Try alternative field name
        pmcid_elem = result_elem.find("id")  # Sometimes PMCID is in id field
        if pmcid_elem is not None and pmcid_elem.text and "PMC" in pmcid_elem.text:
            paper_info["PMCID"] = pmcid_elem.text.strip()
        else:
            paper_info["PMCID"] = ""
    
    # Be more lenient - only require Title (PMID can be empty for some sources)
    if not paper_info["Title"]:
        return None
    
    # If no PMID, try to use PMCID or DOI as identifier
    if not paper_info["PMID"]:
        if paper_info["PMCID"]:
            paper_info["PMID"] = paper_info["PMCID"]  # Use PMCID as identifier
        elif paper_info["DOI"]:
            paper_info["PMID"] = paper_info["DOI"]  # Use DOI as identifier
    
    return paper_info

def fetch_full_text_from_europepmc(pmid: str, pmcid: str = "") -> str:
    """Fetch full text content from Europe PMC for a given PMID or PMCID.
    
    Args:
        pmid: PubMed ID of the paper
        pmcid: PubMed Central ID (preferred for full text access)
        
    Returns:
        Full text content as string, or empty string if not available
    """
    # Prefer PMCID over PMID for full text access
    if not pmcid and not pmid:
        log.warning("fetch_full_text_from_europepmc: No ID provided")
        return ""
    
    # Determine which ID to use and its type
    if pmcid:
        id_to_use = pmcid.strip()  # Keep PMC prefix for PMCID
        id_type = "PMCID"
    else:
        id_to_use = pmid.strip()
        id_type = "PMID"
    
    print(f"[DEBUG] fetch_full_text_from_europepmc: Attempting to fetch full text for {id_type} {id_to_use}", flush=True)
    
    try:
        # Try full text XML endpoint first (more structured)
        # Europe PMC endpoint format: /{id}/fullTextXML (NOT /articles/{id}/fullTextXML)
        # For PMCID: use with "PMC" prefix (e.g., "PMC12345678")
        # For PMID: use the PMID as-is
        url = f"{EUROPE_PMC_BASE_URL}/{id_to_use}/fullTextXML"
        print(f"[DEBUG] fetch_full_text_from_europepmc: Trying XML endpoint: {url}", flush=True)
        response = requests.get(url, timeout=30)
        print(f"[DEBUG] fetch_full_text_from_europepmc: XML endpoint response status: {response.status_code}", flush=True)
        
        if response.status_code == 200:
            # Parse XML and extract text content
            root = ET.fromstring(response.content)
            # Remove namespace prefixes
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]
            
            # Extract text from body sections
            body_text_parts = []
            
            # Try to find body element
            body_elem = root.find(".//body")
            if body_elem is None:
                body_elem = root.find("body")
            
            if body_elem is not None:
                # Extract text from all sections
                for section in body_elem.iter():
                    if section.text:
                        body_text_parts.append(section.text.strip())
                    # Also get tail text
                    if section.tail:
                        body_text_parts.append(section.tail.strip())
            
            # If no body found, try to get all text
            if not body_text_parts:
                body_text_parts = [elem.text.strip() for elem in root.iter() if elem.text and elem.text.strip()]
            
            full_text = " ".join(body_text_parts).strip()
            
            if full_text:
                print(f"[DEBUG] fetch_full_text_from_europepmc: Successfully fetched full text for PMID {pmid}: {len(full_text):,} characters", flush=True)
                log.info(f"Fetched full text for PMID {pmid}: {len(full_text)} characters")
                return full_text
            else:
                print(f"[DEBUG] fetch_full_text_from_europepmc: XML parsed but no text extracted for PMID {pmid}", flush=True)
        
        # Fallback: Try plain text endpoint
        url = f"{EUROPE_PMC_BASE_URL}/{id_to_use}/fullText"
        print(f"[DEBUG] fetch_full_text_from_europepmc: Trying plain text endpoint: {url}", flush=True)
        response = requests.get(url, timeout=30)
        print(f"[DEBUG] fetch_full_text_from_europepmc: Plain text endpoint response status: {response.status_code}", flush=True)
        
        if response.status_code == 200:
            full_text = response.text.strip()
            if full_text:
                print(f"[DEBUG] fetch_full_text_from_europepmc: Successfully fetched full text (plain) for {id_type} {id_to_use}: {len(full_text):,} characters", flush=True)
                log.info(f"Fetched full text (plain) for {id_type} {id_to_use}: {len(full_text)} characters")
                return full_text
        
        print(f"[DEBUG] fetch_full_text_from_europepmc: Full text not available for {id_type} {id_to_use} (status: {response.status_code})", flush=True)
        log.warning(f"Full text not available for {id_type} {id_to_use}")
        return ""
        
    except Exception as e:
        print(f"[DEBUG] fetch_full_text_from_europepmc: Exception fetching full text for {id_type} {id_to_use}: {e}", flush=True)
        log.warning(f"Error fetching full text for {id_type} {id_to_use}: {e}")
        return ""

def _build_europepmc_query(protein_names: List[str], search_together: bool, additional_terms: Optional[List[Dict]]) -> str:
    """Build Europe PMC search query from protein names and additional terms.
    
    Europe PMC supports full-text search by default, so we don't need to specify fields.
    For full-text search, we can search without field restrictions or use FULLTEXT: field.
    """
    config = load_config()
    start_year = config.get("start_year", 1900)
    
    # First check if the gene alias file exists, create an empty one if not
    project_root = Path(__file__).resolve().parents[1]
    tsv_path = project_root / "proteinatlas_search.tsv"
    if not tsv_path.exists():
        log.warning(f"Gene alias TSV not found at {tsv_path}, creating empty file")
        with open(tsv_path, 'w') as f:
            f.write("Gene\tAliases\tGene name\tUniprot\n")  # Header row
    
    genes_df = load_gene_aliases(tsv_path)
    protein_query_parts: List[str] = []
    
    for protein_name in protein_names:
        search_query = protein_name
        if genes_df is not None:
            symbol, aliases, description = find_gene_and_aliases(protein_name, genes_df)
            if symbol:
                # For Europe PMC, build OR query with gene symbol and aliases
                base_terms: List[str] = [symbol]
                if aliases and isinstance(aliases, str):
                    alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
                    base_terms.extend(alias_list[:3])
                # Europe PMC syntax: use quotes for exact phrases, OR for alternatives
                search_query = " OR ".join([f'"{term}"' for term in base_terms])
        protein_query_parts.append(f"({search_query})")
    
    op = " AND " if search_together else " OR "
    protein_query = op.join(protein_query_parts)
    
    additional_query = ""
    if additional_terms:
        for i, term_data in enumerate(additional_terms):
            term = (term_data.get("term") or "").strip()
            if not term:
                continue
            if i == 0:
                additional_query = f"({term})"
            else:
                operator = term_data.get("operator", "AND") or "AND"
                additional_query += f" {operator} ({term})"
    
    query = f"({protein_query})"
    if additional_query:
        query += f" AND {additional_query}"
    # Europe PMC date filtering syntax: PUB_YEAR:[start TO end]
    query += f" AND PUB_YEAR:[{start_year} TO 3000]"
    return query

def iterate_pubmed(protein_names: List[str], search_together: bool, additional_terms: Optional[List[Dict]], has_openai_key: bool = False):
    """Iterate through Europe PMC results, yielding papers one by one for streaming.
    
    Args:
        protein_names: List of protein names to search for
        search_together: Whether to search for all proteins together
        additional_terms: Additional search terms
        has_openai_key: Whether OpenAI key is available (use 50 papers if True, 25 if False)
    """
    query = _build_europepmc_query(protein_names, search_together, additional_terms)
    log.info(f"Europe PMC query: {query}")
    
    # Use 50 papers if OpenAI key is available, otherwise use config default (25)
    base_num_papers = load_config().get("num_papers", 25)
    num_papers = 50 if has_openai_key else base_num_papers
    log.info(f"Using {num_papers} papers (OpenAI key: {has_openai_key})")
    page_size = 25  # Europe PMC default page size
    cursor_mark = "*"  # Start cursor for pagination
    total_fetched = 0
    
    # First request to get total count
    try:
        params = {
            "query": query,
            "format": "xml",
            "resultType": "core",
            "pageSize": page_size,
            "cursorMark": cursor_mark
        }
        response = requests.get(f"{EUROPE_PMC_BASE_URL}/search", params=params, timeout=30)
        response.raise_for_status()
        
        # Parse XML - handle namespaces if present
        root = ET.fromstring(response.content)
        # Remove namespace prefixes for easier searching
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}')[1]
        
        hit_count_elem = root.find("hitCount")
        hit_count = int(hit_count_elem.text) if hit_count_elem is not None and hit_count_elem.text else 0
        log.info(f"Europe PMC found {hit_count} results")
        
        yield {"type": "meta", "count": hit_count}
        
        if hit_count == 0:
            return 
        
        # Parse first page
        result_list = root.find("resultList")
        if result_list is not None:
            for result_elem in result_list.findall("result"):
                if total_fetched >= num_papers:
                    break
                    paper_info = parse_europepmc_result(result_elem)
                    if paper_info:
                        pmid = paper_info.get("PMID", "")
                        # Fetch full text if OpenAI key is available
                        print(f"[DEBUG] iterate_pubmed (first page): has_openai_key = {has_openai_key}", flush=True)
                        if has_openai_key:
                            if pmid:
                                pmcid = paper_info.get("PMCID", "")
                                print(f"[DEBUG] iterate_pubmed (first page): Fetching full text for PMID {pmid}, PMCID: {pmcid}", flush=True)
                                full_text = fetch_full_text_from_europepmc(pmid, pmcid)
                                if full_text:
                                    paper_info["FullText"] = full_text
                                    print(f"[DEBUG] iterate_pubmed (first page): Added full text for PMID {pmid}: {len(full_text):,} characters", flush=True)
                                    log.info(f"Added full text for PMID {pmid}: {len(full_text)} characters")
                                else:
                                    print(f"[DEBUG] iterate_pubmed (first page): Full text not available for PMID {pmid}, using abstract", flush=True)
                                    log.debug(f"Full text not available for PMID {pmid}, using abstract")
                        else:
                            print(f"[DEBUG] iterate_pubmed (first page): No OpenAI key, skipping full text fetch", flush=True)
                        log.debug(f"Paper {total_fetched + 1}: {paper_info.get('Title', '')[:50]}...")
                        yield {"type": "paper", "pmid": pmid, "paper": paper_info}
                        total_fetched += 1
                else:
                    log.warning(f"Failed to parse paper")
                    yield {"type": "error", "pmid": "", "message": "parse_failed"}
        
        # Get next cursor mark for pagination
        next_cursor_elem = root.find("nextCursorMark")
        if next_cursor_elem is not None and next_cursor_elem.text:
            cursor_mark = next_cursor_elem.text
        
        # Fetch additional pages if needed
        while total_fetched < num_papers and cursor_mark and cursor_mark != "*":
            time.sleep(0.35)  # Be nice to Europe PMC
            params["cursorMark"] = cursor_mark
            
            try:
                response = requests.get(f"{EUROPE_PMC_BASE_URL}/search", params=params, timeout=30)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                # Remove namespace prefixes for easier searching
                for elem in root.iter():
                    if '}' in elem.tag:
                        elem.tag = elem.tag.split('}')[1]
                
                result_list = root.find("resultList")
                
                if result_list is None:
                    break
                
                page_fetched = 0
                for result_elem in result_list.findall("result"):
                    if total_fetched >= num_papers:
                        break
                    paper_info = parse_europepmc_result(result_elem)
                    if paper_info:
                        pmid = paper_info.get("PMID", "")
                        # Fetch full text if OpenAI key is available
                        print(f"[DEBUG] iterate_pubmed: has_openai_key = {has_openai_key}", flush=True)
                        if has_openai_key:
                            if pmid:
                                pmcid = paper_info.get("PMCID", "")
                                print(f"[DEBUG] iterate_pubmed: Fetching full text for PMID {pmid}, PMCID: {pmcid}", flush=True)
                                full_text = fetch_full_text_from_europepmc(pmid, pmcid)
                                if full_text:
                                    paper_info["FullText"] = full_text
                                    print(f"[DEBUG] iterate_pubmed: Added full text for PMID {pmid}: {len(full_text):,} characters", flush=True)
                                    log.info(f"Added full text for PMID {pmid}: {len(full_text)} characters")
                                else:
                                    print(f"[DEBUG] iterate_pubmed: Full text not available for PMID {pmid}, using abstract", flush=True)
                                    log.debug(f"Full text not available for PMID {pmid}, using abstract")
                        else:
                            print(f"[DEBUG] iterate_pubmed: No OpenAI key, skipping full text fetch", flush=True)
                        log.debug(f"Paper {total_fetched + 1}: {paper_info.get('Title', '')[:50]}...")
                        yield {"type": "paper", "pmid": pmid, "paper": paper_info}
                        total_fetched += 1
                        page_fetched += 1
                    else:
                        # Log more details about why parsing failed
                        title_elem = result_elem.find("title")
                        pmid_elem = result_elem.find("pmid") or result_elem.find("id")
                        title_text = title_elem.text if title_elem is not None and title_elem.text else "N/A"
                        pmid_text = pmid_elem.text if pmid_elem is not None and pmid_elem.text else "N/A"
                        print(f"[DEBUG] iterate_pubmed: Failed to parse paper - Title: {title_text[:50]}, PMID: {pmid_text}", flush=True)
                        log.warning(f"Failed to parse paper - Title: {title_text[:50]}, PMID: {pmid_text}")
                        yield {"type": "error", "pmid": "", "message": "parse_failed"}
                
                # If no new papers were fetched, break
                if page_fetched == 0:
                    break
                
                # Get next cursor mark
                next_cursor_elem = root.find("nextCursorMark")
                if next_cursor_elem is not None and next_cursor_elem.text:
                    new_cursor = next_cursor_elem.text
                    if new_cursor == cursor_mark:  # No more pages
                        break
                    cursor_mark = new_cursor
                else:
                    break
            except Exception as e:
                log.error(f"Error fetching page from Europe PMC: {e}")
                break
                
    except Exception as e:
        log.error(f"Error querying Europe PMC: {e}")
        yield {"type": "error", "pmid": "", "message": str(e)}

def query_pubmed(protein_names: List[str], search_together: bool = False, additional_terms: Optional[List[Dict]] = None, has_openai_key: bool = False) -> List[Dict]:
    """Query Europe PMC for papers matching the protein names and additional terms.
    
    Args:
        protein_names: List of protein names to search for
        search_together: Whether to search for all proteins together
        additional_terms: Additional search terms
        has_openai_key: Whether OpenAI key is available (use 50 papers if True, 25 if False)
    """
    # Use 50 papers if OpenAI key is available, otherwise use config default (25)
    base_num_papers = load_config().get("num_papers", 25)
    num = 50 if has_openai_key else base_num_papers
    log.info(f"query_pubmed: Using {num} papers (OpenAI key: {has_openai_key})")
    query = _build_europepmc_query(protein_names, search_together, additional_terms)
    
    try:
        papers: List[Dict] = []
        page_size = 25
        cursor_mark = "*"
        total_fetched = 0
        
        while total_fetched < num:
            params = {
                "query": query,
                "format": "xml",
                "resultType": "core",
                "pageSize": page_size,
                "cursorMark": cursor_mark
            }
            
            response = requests.get(f"{EUROPE_PMC_BASE_URL}/search", params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            # Remove namespace prefixes for easier searching
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]
            
            result_list = root.find("resultList")
            
            if result_list is None:
                break
            
            for result_elem in result_list.findall("result"):
                if total_fetched >= num:
                    break
                paper_info = parse_europepmc_result(result_elem)
                if paper_info:
                    # Fetch full text if OpenAI key is available
                    if has_openai_key:
                        pmid = paper_info.get("PMID", "")
                        pmcid = paper_info.get("PMCID", "")
                        if pmid:
                            full_text = fetch_full_text_from_europepmc(pmid, pmcid)
                            if full_text:
                                paper_info["FullText"] = full_text
                                log.info(f"Added full text for PMID {pmid}: {len(full_text)} characters")
                            else:
                                # If full text not available, keep abstract
                                log.debug(f"Full text not available for PMID {pmid}, using abstract")
                    papers.append(paper_info)
                    total_fetched += 1
            
            # Get next cursor mark
            next_cursor_elem = root.find("nextCursorMark")
            if next_cursor_elem is not None and next_cursor_elem.text:
                new_cursor = next_cursor_elem.text
                if new_cursor == cursor_mark:  # No more pages
                    break
                cursor_mark = new_cursor
            else:
                break
            
            if total_fetched < num:
                time.sleep(0.35)  # Be nice to Europe PMC
        
        return papers
    except Exception as e:
        log.error(f"Error querying Europe PMC: {e}")
        return []
