from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from services.llmhelper import setup_openai, generate_with_gemini_rest, count_tokens
import logging
import os
import sys

log = logging.getLogger("protsearch")

def ensure_results_directory() -> Path:
    results_dir = Path.cwd() / "results"
    results_dir.mkdir(exist_ok=True)
    return results_dir

def save_results_to_txt(text: str, protein_name: str, results_dir: Path) -> Optional[str]:
    if not text:
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{protein_name}_{timestamp}.txt"
    file_path = results_dir / filename
    try:
        file_path.write_text(text, encoding="utf-8")
        return str(file_path)
    except Exception as e:
        log.warning(f"Error saving results: {e}")
        return None

def summarize_papers_with_llm(papers: List[Dict], protein_names: List[str], custom_question: str = "", uniprot_functions: str = "") -> str:
    import sys
    # Force immediate output
    sys.stdout.write("[DEBUG] ========== summarize_papers_with_llm CALLED ==========\n")
    sys.stdout.write(f"[DEBUG] summarize_papers_with_llm: papers count: {len(papers)}, proteins: {protein_names}\n")
    sys.stdout.flush()
    print("[DEBUG] ========== summarize_papers_with_llm CALLED ==========", flush=True)
    print(f"[DEBUG] summarize_papers_with_llm: papers count: {len(papers)}, proteins: {protein_names}", flush=True)
    sys.stdout.flush()
    if not papers:
        print("[DEBUG] summarize_papers_with_llm: No papers, returning empty", flush=True)
        sys.stdout.flush()
        return ""
    proteins_text = ", ".join(protein_names)
    # Check if we have OpenAI key (for full text) by checking if any paper has FullText
    has_full_text = any(p.get('FullText') for p in papers)
    
    # Count papers with full text vs abstracts
    papers_with_full_text = sum(1 for p in papers if p.get('FullText'))
    papers_with_abstract_only = len(papers) - papers_with_full_text
    
    print(f"[DEBUG] summarize_papers_with_llm: Papers breakdown - Total: {len(papers)}, Full Text: {papers_with_full_text}, Abstract Only: {papers_with_abstract_only}", flush=True)
    sys.stdout.flush()
    
    # Include full text if available (for OpenAI), otherwise use abstracts
    papers_text = "\n\n".join(
        [
            f"PMID: {p.get('PMID','')}\nTitle: {p.get('Title','')}\nAuthors: {p.get('Authors','')}\n"
            f"Journal: {p.get('Journal','')}\nYear: {p.get('Year','')}\n"
            + (f"Full Text: {p.get('FullText','')}" if p.get('FullText') else f"Abstract: {p.get('Abstract','')}")
            + f"\nDOI: {p.get('DOI','')}"
            for p in papers
        ]
    )
    
    # Log statistics about the input
    total_chars = len(papers_text)
    avg_chars_per_paper = total_chars / len(papers) if papers else 0
    
    # Calculate full text vs abstract character counts
    full_text_chars = sum(len(p.get('FullText', '')) for p in papers)
    abstract_chars = sum(len(p.get('Abstract', '')) for p in papers)
    
    print(f"[DEBUG] summarize_papers_with_llm: Input statistics:", flush=True)
    print(f"[DEBUG]   - Total papers text length: {total_chars:,} characters", flush=True)
    print(f"[DEBUG]   - Average per paper: {avg_chars_per_paper:,.0f} characters", flush=True)
    print(f"[DEBUG]   - Full text total: {full_text_chars:,} characters", flush=True)
    print(f"[DEBUG]   - Abstracts total: {abstract_chars:,} characters", flush=True)
    sys.stdout.flush()
    
    # Log a sample of the first paper to verify content
    if papers:
        first_paper = papers[0]
        first_paper_has_full_text = bool(first_paper.get('FullText'))
        first_paper_content = first_paper.get('FullText') or first_paper.get('Abstract', '')
        first_paper_content_preview = first_paper_content[:500] if first_paper_content else "N/A"
        print(f"[DEBUG] summarize_papers_with_llm: First paper sample (PMID: {first_paper.get('PMID', 'N/A')}):", flush=True)
        print(f"[DEBUG]   - Has Full Text: {first_paper_has_full_text}", flush=True)
        print(f"[DEBUG]   - Content type: {'Full Text' if first_paper_has_full_text else 'Abstract'}", flush=True)
        print(f"[DEBUG]   - Content length: {len(first_paper_content):,} characters", flush=True)
        print(f"[DEBUG]   - Content preview (first 500 chars): {first_paper_content_preview}...", flush=True)
        sys.stdout.flush()
    background_block = ""
    if uniprot_functions:
        log.info(f"summarize_papers_with_llm: Including UniProt function data in prompt ({len(uniprot_functions)} chars)")
        background_block = f"""
=== BACKGROUND CONTEXT (UniProt Database) ===
The following is general protein function information from UniProt database:
{uniprot_functions}

IMPORTANT: Use this UniProt information to write a general overview/introduction section at the BEGINNING of your summary. 
This overview should describe the general function and role of {proteins_text} based on UniProt data.
If you cite this information, cite it as: (UniProt: https://www.uniprot.org)

=== RESEARCH PAPERS TO ANALYZE ===
"""
    else:
        log.warning(f"summarize_papers_with_llm: No UniProt function data provided for {protein_names}")
        background_block = "=== RESEARCH PAPERS TO ANALYZE ===\n"
    
    prompt = f"""You are a research assistant specialized in neuroscience.
Analyze the research papers below about {proteins_text} and create a comprehensive summary.

{background_block}{papers_text}

=== SUMMARY STRUCTURE ===
Your summary MUST follow this structure:

1. **General Overview** (use UniProt information): Start with a brief overview of {proteins_text} based on the UniProt function data provided above. This should be 1-2 paragraphs describing the general biological function and role of the protein(s). Cite as (UniProt: https://www.uniprot.org) if referencing this information.

2. **Key Findings** (from papers): What are the key research findings related to {proteins_text}? Cite specific papers using (PMID: xxxxxxxx).

3. **Disease Associations** (from papers): Has {proteins_text} been linked to any diseases or conditions? If yes, which ones? Cite specific papers.

4. **Mechanisms** (from papers): What cellular/molecular mechanisms involve {proteins_text}? Cite specific papers.

5. **Therapeutic Implications** (from papers): Are there any therapeutic implications mentioned? Cite specific papers.
"""
    if custom_question:
        prompt += f"\n6. **User Question**: Additionally, address this question from the user:\n{custom_question}\nCite specific papers.\n"
    prompt += """
=== CRITICAL CITATION RULES ===
- For the General Overview section: Use UniProt information and cite as (UniProt: https://www.uniprot.org)
- For all other sections: ONLY cite papers for information that comes from those papers
- For each finding, mechanism, disease link, or therapeutic implication from papers, cite the specific paper(s) using the PMID
- Format citations in-text as: (PMID: 12345678) or (PMID: 12345678, 87654321)
- At the end, provide a References section with all cited papers in APA format
- Each reference MUST include the DOI if available
- Format references as: Author(s). (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/DOI
- Only include information that is explicitly stated in the papers
- Use proper scientific terminology
- Use bold formatting for important terms by surrounding them with ** (e.g. **NPTX1**)

=== OUTPUT FORMAT ===
Format the response as a well-structured text with clear sections, paragraphs, and a References section at the end.
Start with the General Overview section using UniProt information, then proceed with findings from the papers.
"""
    total_tokens = count_tokens(prompt)
    max_tokens = 120000
    
    # Log final prompt statistics
    print(f"[DEBUG] summarize_papers_with_llm: Final prompt statistics:", flush=True)
    print(f"[DEBUG]   - Total prompt length: {len(prompt):,} characters", flush=True)
    print(f"[DEBUG]   - Total tokens (estimated): {total_tokens:,}", flush=True)
    print(f"[DEBUG]   - Papers text portion: {len(papers_text):,} characters", flush=True)
    print(f"[DEBUG]   - Background/instructions: {len(prompt) - len(papers_text):,} characters", flush=True)
    
    # Optionally log a sample of the prompt (first 2000 chars and last 500 chars)
    print(f"[DEBUG] summarize_papers_with_llm: Prompt preview (first 2000 chars):", flush=True)
    print(f"[DEBUG] {prompt[:2000]}...", flush=True)
    print(f"[DEBUG] summarize_papers_with_llm: Prompt preview (last 500 chars):", flush=True)
    print(f"[DEBUG] ...{prompt[-500:]}", flush=True)
    sys.stdout.flush()
    papers_copy = list(papers)
    while total_tokens > max_tokens and len(papers_copy) > 1:
        papers_copy = papers_copy[:-1]
        papers_text = "\n\n".join(
            [
                f"PMID: {p.get('PMID','')}\nTitle: {p.get('Title','')}\nAuthors: {p.get('Authors','')}\n"
                f"Journal: {p.get('Journal','')}\nYear: {p.get('Year','')}\n"
                + (f"Full Text: {p.get('FullText','')}" if p.get('FullText') else f"Abstract: {p.get('Abstract','')}")
                + f"\nDOI: {p.get('DOI','')}"
                for p in papers_copy
            ]
        )
        # Update the papers section in the prompt while preserving structure
        # The prompt uses "=== SUMMARY STRUCTURE ===" not "=== SUMMARY REQUIREMENTS ==="
        if "=== RESEARCH PAPERS TO ANALYZE ===" in prompt:
            parts = prompt.split("=== RESEARCH PAPERS TO ANALYZE ===", 1)
            if len(parts) == 2:
                prefix, rest = parts
                # Try to find where the papers section ends (before SUMMARY STRUCTURE)
                rest_parts = rest.split("\n\n=== SUMMARY STRUCTURE ===", 1)
                if len(rest_parts) == 2:
                    rest_after_list = rest_parts[1]
                    prompt = f"{prefix}=== RESEARCH PAPERS TO ANALYZE ===\n{papers_text}\n\n=== SUMMARY STRUCTURE ==={rest_after_list}"
                else:
                    # Fallback if structure is different - just replace the papers section
                    prompt = f"{prefix}=== RESEARCH PAPERS TO ANALYZE ===\n{papers_text}\n\n{rest}"
            else:
                # Fallback if split failed - rebuild prompt
                prompt_prefix = prompt.split("=== RESEARCH PAPERS TO ANALYZE ===")[0] if "=== RESEARCH PAPERS TO ANALYZE ===" in prompt else prompt.split("\n\n")[0] if "\n\n" in prompt else ""
                prompt = f"{prompt_prefix}\n\n=== RESEARCH PAPERS TO ANALYZE ===\n{papers_text}\n\n=== SUMMARY STRUCTURE ===\nYour summary MUST follow this structure:\n\n1. **General Overview** (use UniProt information)\n2. **Key Findings** (from papers)\n3. **Disease Associations** (from papers)\n4. **Mechanisms** (from papers)\n5. **Therapeutic Implications** (from papers)\n"
        else:
            # Fallback for old format
            parts = prompt.split("Papers to analyze:", 1)
            if len(parts) == 2:
                prefix, rest = parts
                rest_parts = rest.split("\n\nCreate a summary", 1)
                if len(rest_parts) == 2:
                    rest_after_list = rest_parts[1]
                    prompt = f"{prefix}Papers to analyze:\n{papers_text}\n\nCreate a summary{rest_after_list}"
                else:
                    prompt = f"{prefix}Papers to analyze:\n{papers_text}\n\n{rest}"
            else:
                # Fallback if split failed - rebuild prompt
                prompt = f"You are a research assistant specialized in neuroscience.\nAnalyze the research papers below about {proteins_text} and create a comprehensive summary.\n\n=== RESEARCH PAPERS TO ANALYZE ===\n{papers_text}\n\n=== SUMMARY STRUCTURE ===\nYour summary MUST follow this structure:\n\n1. **General Overview**\n2. **Key Findings**\n3. **Disease Associations**\n4. **Mechanisms**\n5. **Therapeutic Implications**\n"
        total_tokens = count_tokens(prompt)
    
    # Check for OpenAI API key in environment - only use OpenAI if key is actually present
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    key_present = bool(openai_key)
    key_length = len(openai_key) if openai_key else 0
    key_preview = f"{openai_key[:10]}..." if openai_key and len(openai_key) > 10 else (openai_key if openai_key else "NONE")
    
    print(f"[DEBUG] summarize_papers_with_llm: OpenAI key check - present: {key_present}, length: {key_length}, preview: {key_preview}", flush=True)
    sys.stdout.flush()
    log.info(f"summarize_papers_with_llm: OpenAI key present: {key_present}, length: {key_length}")
    
    # Try OpenAI first only if key is present
    if openai_key:
        print("[DEBUG] summarize_papers_with_llm: OpenAI key found, attempting to initialize client", flush=True)
        sys.stdout.flush()
        log.info("summarize_papers_with_llm: Attempting to use OpenAI for summarization")
        client = setup_openai()
        if client is None:
            print("[DEBUG] summarize_papers_with_llm: ERROR - setup_openai() returned None")
            log.warning("summarize_papers_with_llm: setup_openai() returned None, OpenAI client not available")
        else:
            print("[DEBUG] summarize_papers_with_llm: OpenAI client initialized successfully")
            log.info("summarize_papers_with_llm: OpenAI client initialized successfully")
            try:
                # Try different model names in case one doesn't work
                model_name = "gpt-5-mini"  # Updated to gpt-5-mini as requested
                print(f"[DEBUG] summarize_papers_with_llm: Calling OpenAI API with model '{model_name}'")
                print(f"[DEBUG] summarize_papers_with_llm: Prompt length: {len(prompt)} characters")
                log.info(f"summarize_papers_with_llm: Calling OpenAI API with model {model_name}")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a research assistant specialized in neuroscience. Summarize papers with clear citations. Only cite papers for information that comes from those papers. Do NOT cite papers for general protein function information from UniProt - that is background context only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=1,
                    max_completion_tokens=40000,  # Increased for reasoning models - they need tokens for both reasoning and output
                    
                )
                has_choices = bool(response and response.choices)
                print(f"[DEBUG] summarize_papers_with_llm: OpenAI API response received - has_choices: {has_choices}", flush=True)
                sys.stdout.flush()
                log.info(f"summarize_papers_with_llm: OpenAI API response received, has choices: {has_choices}")
                
                    # Debug: Print full response structure
                if response:
                    print(f"[DEBUG] summarize_papers_with_llm: Response type: {type(response)}", flush=True)
                    print(f"[DEBUG] summarize_papers_with_llm: Response has choices: {hasattr(response, 'choices')}", flush=True)
                    if hasattr(response, 'choices') and response.choices:
                        print(f"[DEBUG] summarize_papers_with_llm: Number of choices: {len(response.choices)}", flush=True)
                        first_choice = response.choices[0]
                        print(f"[DEBUG] summarize_papers_with_llm: First choice type: {type(first_choice)}", flush=True)
                        print(f"[DEBUG] summarize_papers_with_llm: First choice attributes: {dir(first_choice)}", flush=True)
                        print(f"[DEBUG] summarize_papers_with_llm: First choice finish_reason: {getattr(first_choice, 'finish_reason', 'N/A')}", flush=True)
                        print(f"[DEBUG] summarize_papers_with_llm: First choice has message: {hasattr(first_choice, 'message')}", flush=True)
                        if hasattr(first_choice, 'message'):
                            message = first_choice.message
                            print(f"[DEBUG] summarize_papers_with_llm: Message type: {type(message)}", flush=True)
                            print(f"[DEBUG] summarize_papers_with_llm: Message attributes: {dir(message)}", flush=True)
                            print(f"[DEBUG] summarize_papers_with_llm: Message has content: {hasattr(message, 'content')}", flush=True)
                            if hasattr(message, 'content'):
                                content_val = message.content
                                print(f"[DEBUG] summarize_papers_with_llm: Content type: {type(content_val)}", flush=True)
                                print(f"[DEBUG] summarize_papers_with_llm: Content is None: {content_val is None}", flush=True)
                                print(f"[DEBUG] summarize_papers_with_llm: Content value (first 500 chars): {repr(content_val)[:500] if content_val else 'None'}", flush=True)
                    sys.stdout.flush()
                
                if response and response.choices:
                    first_choice = response.choices[0]
                    if hasattr(first_choice, 'message') and first_choice.message:
                        message = first_choice.message
                        # For reasoning models, content might be empty but annotations might have the text
                        content = message.content if hasattr(message, 'content') and message.content else ""
                        
                        # Check if this is a reasoning model with annotations
                        if not content and hasattr(message, 'annotations') and message.annotations:
                            # For reasoning models, the actual content might be in annotations
                            print(f"[DEBUG] summarize_papers_with_llm: Found annotations: {len(message.annotations) if message.annotations else 0}", flush=True)
                            # Try to extract content from annotations if available
                            for ann in (message.annotations or []):
                                if hasattr(ann, 'text') and ann.text:
                                    content = ann.text
                                    break
                                elif hasattr(ann, 'content') and ann.content:
                                    content = ann.content
                                    break
                    else:
                        # Try alternative access patterns
                        content = getattr(first_choice, 'content', None) or getattr(first_choice, 'text', None) or ""
                    
                    content_len = len(content) if content else 0
                    print(f"[DEBUG] summarize_papers_with_llm: OpenAI response content length: {content_len}", flush=True)
                    sys.stdout.flush()
                    log.info(f"summarize_papers_with_llm: OpenAI response content length: {content_len}")
                    
                    if content:
                        print("[DEBUG] summarize_papers_with_llm: SUCCESS - Returning OpenAI summary", flush=True)
                        sys.stdout.flush()
                        log.info("summarize_papers_with_llm: Successfully used OpenAI for summarization")
                        return content
                    else:
                        print("[DEBUG] summarize_papers_with_llm: WARNING - OpenAI returned empty content", flush=True)
                        print(f"[DEBUG] summarize_papers_with_llm: Full response object: {response}", flush=True)
                        sys.stdout.flush()
                        log.warning("summarize_papers_with_llm: OpenAI returned empty content")
                else:
                    print("[DEBUG] summarize_papers_with_llm: WARNING - OpenAI response has no choices", flush=True)
                    sys.stdout.flush()
                    log.warning("summarize_papers_with_llm: OpenAI response has no choices")
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                import traceback
                tb = traceback.format_exc()
                print(f"[DEBUG] summarize_papers_with_llm: EXCEPTION - {error_type}: {error_msg}")
                print(f"[DEBUG] summarize_papers_with_llm: Full traceback:\n{tb}")
                log.error(f"summarize_papers_with_llm: OpenAI summarization failed with exception: {e}", exc_info=True)
                log.info("summarize_papers_with_llm: Falling back to Google GenAI")
                # Don't return here - let it fall through to Gemma
    else:
        print("[DEBUG] summarize_papers_with_llm: No OpenAI key found, skipping OpenAI")
    
    # Use Google/Gemma models if no OpenAI key or OpenAI failed
    # Default Google API key (fallback if not set in environment)
    DEFAULT_GOOGLE_API_KEY = "AIzaSyAtbBvgeOx5_ndbbCbIkhWJT4yYZpmJ9_M"
    google_key = os.environ.get("GOOGLE_API_KEY", DEFAULT_GOOGLE_API_KEY).strip() # type: ignore
    print(f"[DEBUG] summarize_papers_with_llm: Google key check - present: {bool(google_key)}, length: {len(google_key) if google_key else 0}")
    if google_key:
        print("[DEBUG] summarize_papers_with_llm: Using Google Gemma models for summarization")
        log.info("summarize_papers_with_llm: Using Google Gemma models for summarization")
        for model in ["gemma-3-4b-it", "gemma-3-12b-it"]:
            print(f"[DEBUG] summarize_papers_with_llm: Trying model: {model}")
            text_rest = generate_with_gemini_rest(prompt, model, google_key)
            if text_rest:
                print(f"[DEBUG] summarize_papers_with_llm: SUCCESS - Used {model}, content length: {len(text_rest)}")
                log.info(f"summarize_papers_with_llm: Successfully used {model} for summarization")
                return text_rest
            else:
                print(f"[DEBUG] summarize_papers_with_llm: Model {model} returned empty, trying next")
    
    error_msg = "Summary unavailable: no LLM provider configured. Provide an OpenAI API key in the app or set the GOOGLE_API_KEY environment variable to use Google Gemini models."
    print(f"[DEBUG] summarize_papers_with_llm: FAILED - {error_msg}")
    return error_msg