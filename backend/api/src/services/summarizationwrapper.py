from typing import List, Dict, Optional, Tuple, Any
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


def _join_papers_text(papers: List[Dict]) -> str:
    return "\n\n".join(
        [
            f"PMID: {p.get('PMID','')}\nTitle: {p.get('Title','')}\nAuthors: {p.get('Authors','')}\n"
            f"Journal: {p.get('Journal','')}\nYear: {p.get('Year','')}\n"
            + (f"Full Text: {p.get('FullText','')}" if p.get("FullText") else f"Abstract: {p.get('Abstract','')}")
            + f"\nDOI: {p.get('DOI','')}"
            for p in papers
        ]
    )


def _summarization_prompt_tail(proteins_text: str, custom_question: str) -> str:
    tail = f"""=== SUMMARY STRUCTURE ===
Your summary MUST use GitHub-flavored Markdown and follow this structure exactly:

# {proteins_text}: Research Summary

## General Overview
Write 1-2 short paragraphs describing the general biological function and role of {proteins_text} using ONLY the UniProt background data above. End this section with a single citation: (UniProt: https://www.uniprot.org). Do NOT repeat the UniProt citation elsewhere.

## Key Findings
List the key research findings related to {proteins_text} as bullet points (one finding per bullet).

## Disease Associations
List diseases or conditions linked to {proteins_text} as bullet points. If none are reported, write one bullet stating that.

## Mechanisms
List cellular or molecular mechanisms involving {proteins_text} as bullet points.

## Therapeutic Implications
List therapeutic implications mentioned in the papers as bullet points. If none are reported, write one bullet stating that.
"""
    if custom_question:
        tail += f"""
## User Question
Address this question from the user as bullet point(s):
{custom_question}
"""
    tail += """
=== CRITICAL CITATION RULES ===
- General Overview: use UniProt information only; cite UniProt once at the end of that section
- All other sections: cite only the specific paper(s) that support each bullet
- In-text citations: (PMID: 12345678) or (PMID: 12345678, 87654321) at the end of the relevant sentence
- End with a ## References section listing every cited paper in APA format, one reference per numbered line
- Each reference MUST include the DOI URL when available
- Reference format: Author(s). (Year). Title. *Journal*, Volume(Issue), Pages. https://doi.org/DOI
- Only include information explicitly stated in the papers or UniProt background

=== OUTPUT FORMAT (Markdown) ===
Follow these formatting rules strictly:
- Use # for the title, ## for each section heading, each on its own line
- Under every section except General Overview, use "- " bullet points (one finding per bullet)
- Start each bullet with a short topic label in bold, then the explanation. Example:
  - **COVID-19 severity:** Variants in ACE1 and ACE2 are associated with disease outcomes (PMID: 40150043).
- Use normal (non-italic) body text; do NOT italicize whole paragraphs or sections
- Bold a protein or gene name only on its first mention within each bullet or paragraph
- Do NOT use ***bold-italic*** or mixed heading styles; use only ## headings and **bold** topic labels
- Do NOT use inline section headers like "**Topic:**" without a bullet; always use bullet lists under ## sections
- Separate sections with a blank line
- In References, use a numbered list (1., 2., 3., ...) with one full APA citation per line
"""
    return tail


def build_summarization_prompt(
    papers: List[Dict],
    protein_names: List[str],
    custom_question: str = "",
    uniprot_functions: str = "",
    evaluator_notes: str = "",
    max_tokens: int = 120000,
) -> Tuple[str, Dict[str, Any]]:
    """
    Build the same user prompt string sent to OpenAI/Gemini as in summarize_papers_with_llm.
    evaluator_notes: optional block === EVALUATOR NOTES === (for offline / manual evaluation).
    """
    if not papers:
        return "", {
            "paper_count": 0,
            "papers_in_prompt": 0,
            "estimated_tokens": 0,
            "prompt_chars": 0,
        }
    proteins_text = ", ".join(protein_names)
    if uniprot_functions:
        log.info(
            "build_summarization_prompt: Including UniProt function data (%s chars)",
            len(uniprot_functions),
        )
        background_block = f"""
=== BACKGROUND CONTEXT (UniProt Database) ===
The following is general protein function information from UniProt database:
{uniprot_functions}

IMPORTANT: Use this UniProt information only for the ## General Overview section at the beginning of your summary.
Cite UniProt once at the end of that section as: (UniProt: https://www.uniprot.org)

=== RESEARCH PAPERS TO ANALYZE ===
"""
    else:
        log.warning("build_summarization_prompt: No UniProt function data for %s", protein_names)
        background_block = "=== RESEARCH PAPERS TO ANALYZE ===\n"

    intro = f"""You are a research assistant specialized in neuroscience.
Analyze the research papers below about {proteins_text} and create a comprehensive summary.

"""
    if evaluator_notes.strip():
        glue_fmt = f"\n\n=== EVALUATOR NOTES ===\n{evaluator_notes.strip()}\n\n"
    else:
        glue_fmt = "\n\n"
    tail = _summarization_prompt_tail(proteins_text, custom_question)

    papers_copy = list(papers)
    while True:
        papers_text = _join_papers_text(papers_copy)
        prompt = intro + background_block + papers_text + glue_fmt + tail
        total_tokens = count_tokens(prompt)
        if total_tokens <= max_tokens or len(papers_copy) <= 1:
            break
        papers_copy = papers_copy[:-1]

    return prompt, {
        "paper_count": len(papers),
        "papers_in_prompt": len(papers_copy),
        "estimated_tokens": total_tokens,
        "prompt_chars": len(prompt),
        "papers_text_chars": len(papers_text),
        "trimmed": len(papers_copy) < len(papers),
    }


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
    prompt, prompt_meta = build_summarization_prompt(
        papers, protein_names, custom_question, uniprot_functions, evaluator_notes=""
    )
    total_tokens = prompt_meta["estimated_tokens"]
    papers_text_chars = prompt_meta["papers_text_chars"]

    # Log final prompt statistics
    print(f"[DEBUG] summarize_papers_with_llm: Final prompt statistics:", flush=True)
    print(f"[DEBUG]   - Total prompt length: {len(prompt):,} characters", flush=True)
    print(f"[DEBUG]   - Total tokens (estimated): {total_tokens:,}", flush=True)
    print(f"[DEBUG]   - Papers text portion: {papers_text_chars:,} characters", flush=True)
    print(f"[DEBUG]   - Background/instructions: {len(prompt) - papers_text_chars:,} characters", flush=True)

    # Optionally log a sample of the prompt (first 2000 chars and last 500 chars)
    print(f"[DEBUG] summarize_papers_with_llm: Prompt preview (first 2000 chars):", flush=True)
    print(f"[DEBUG] {prompt[:2000]}...", flush=True)
    print(f"[DEBUG] summarize_papers_with_llm: Prompt preview (last 500 chars):", flush=True)
    print(f"[DEBUG] ...{prompt[-500:]}", flush=True)
    sys.stdout.flush()

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
                        {"role": "system", "content": "You are a research assistant specialized in neuroscience. Write summaries in clean GitHub-flavored Markdown with ## section headings and bullet lists. Only cite papers for information from those papers. Use UniProt only for the General Overview and cite it once. Do not italicize whole paragraphs."},
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
    
    # Use Google Gemini model if no OpenAI key or OpenAI failed.
    google_key = os.environ.get("GOOGLE_API_KEY", "").strip() # type: ignore
    print(f"[DEBUG] summarize_papers_with_llm: Google key check - present: {bool(google_key)}, length: {len(google_key) if google_key else 0}")
    if google_key:
        print("[DEBUG] summarize_papers_with_llm: Using Google Gemini model for summarization")
        log.info("summarize_papers_with_llm: Using Google Gemini model for summarization")
        primary = (os.environ.get("GEMINI_SUMMARY_MODEL") or "gemini-2.5-pro").strip() or "gemini-2.5-pro"
        fallback = (os.environ.get("GEMINI_SUMMARY_FALLBACK_MODEL") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        models = [primary]
        if fallback and fallback != primary:
            models.append(fallback)
        log.info(
            "summarize_papers_with_llm: Gemini models (one HTTP call each, no 429 retries): %s",
            models,
        )
        for model in models:
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