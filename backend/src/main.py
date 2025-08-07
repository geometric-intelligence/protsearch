import os
from typing import List, Dict, Tuple
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import csv
import io
import requests
from Bio import Entrez
import time
import tiktoken
import yaml
import pandas as pd
from pathlib import Path
from thefuzz import fuzz
from thefuzz import process
from flask import Flask, request, jsonify
from flask_cors import CORS
import json

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def load_gene_aliases(file_path):
    """Load gene data from TSV file"""
    try:
        genes_df = pd.read_csv(file_path, sep='\t')
        return genes_df
    except Exception as e:
        print(f"Error loading gene aliases file: {str(e)}")
        return None

def find_similar_genes(query, genes_df, threshold=80):
    """Find similar gene names using fuzzy matching"""
    gene_names = genes_df['Gene'].tolist()
    matches = process.extract(query, gene_names, limit=5)
    return [match for match, score in matches if score >= threshold]

def find_gene_and_aliases(gene_name, genes_df):
    """Find gene and its aliases from the gene dataframe"""
    # Try exact match first
    exact_match = genes_df[genes_df['Gene'].str.lower() == gene_name.lower()]
    
    if not exact_match.empty:
        row = exact_match.iloc[0]
        return row['Gene'], row.get('Aliases', ''), row.get('Gene name', '')
        
    # Try fuzzy matching if no exact match
    similar_genes = find_similar_genes(gene_name, genes_df)
    if similar_genes:
        top_match = similar_genes[0]
        row = genes_df[genes_df['Gene'] == top_match].iloc[0]
        return row['Gene'], row.get('Aliases', ''), row.get('Gene name', '')
        
    # Return original if no match found
    return gene_name, '', ''

def create_search_query(symbol, aliases, description):
    """Create an optimized PubMed search query using gene information"""
    query_parts = [symbol]
    
    # Add aliases if available
    if aliases and isinstance(aliases, str):
        alias_list = [a.strip() for a in aliases.split(',') if a.strip()]
        if alias_list:
            # Add up to 3 aliases to avoid overly complex queries
            for alias in alias_list[:3]:
                query_parts.append(alias)
    
    # Combine with OR
    return " OR ".join([f'"{part}"' for part in query_parts])

def load_config():
    """Load configuration from config.yaml"""
    try:
        config_path = Path(__file__).parent.parent / 'config.yaml'
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading config: {str(e)}")
        return {
            'num_papers': 50,
            'start_year': 2023
        }  # Default values

def setup_openai():
    """Set up OpenAI client"""
    # Try to load from .env file first
    load_dotenv()
    
    # Get API key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
    return OpenAI(api_key=api_key)

def parse_pubmed_record(record_text):
    """Parse PubMed record in MEDLINE format"""
    if not record_text:
        return None
        
    lines = record_text.split('\n')
    paper_info = {
        "PMID": "",
        "Title": "",
        "Authors": "",
        "Journal": "",
        "Year": "",
        "Abstract": "",
        "DOI": ""
    }
    
    current_field = None
    
    for line in lines:
        if not line.strip():
            continue
            
        # Check if line starts a new field
        if line[:4].strip() and line[4:6] == "- ":
            current_field = line[:4].strip()
            content = line[6:].strip()
            
            if current_field == "PMID":
                paper_info["PMID"] = content
            elif current_field == "TI":
                paper_info["Title"] = content
            elif current_field == "AU":
                paper_info["Authors"] = content
            elif current_field == "DP":
                # Extract year from date
                year_match = content.split(" ")[0]
                if year_match:
                    paper_info["Year"] = year_match
            elif current_field == "JT":
                paper_info["Journal"] = content
            elif current_field == "AB":
                paper_info["Abstract"] = content
            elif current_field == "LID" and "[doi]" in content:
                # Extract DOI
                paper_info["DOI"] = content.replace(" [doi]", "")
            elif current_field == "AID" and "[doi]" in content:
                # Alternative location for DOI
                paper_info["DOI"] = content.replace(" [doi]", "")
                
        # If line continues the previous field
        elif line.startswith("      ") and current_field:
            content = line.strip()
            
            if current_field == "TI":
                paper_info["Title"] += " " + content
            elif current_field == "AU":
                if paper_info["Authors"]:
                    paper_info["Authors"] += ", " + content
                else:
                    paper_info["Authors"] = content
            elif current_field == "AB":
                paper_info["Abstract"] += " " + content
    
    # Return None if essential fields are missing
    if not paper_info["PMID"] or not paper_info["Title"]:
        return None
        
    return paper_info

def count_tokens(text):
    """Count tokens in text using tiktoken"""
    try:
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        return len(encoding.encode(text))
    except Exception as e:
        # Fallback to simple approximation if tiktoken fails
        return len(text.split()) * 1.3  # Rough estimate

def ensure_results_directory():
    """Ensure the results directory exists"""
    results_dir = Path.cwd() / 'results'
    results_dir.mkdir(exist_ok=True)
    return results_dir

def save_results_to_txt(text, protein_name, results_dir):
    """Save results to a text file"""
    if not text:
        return None
        
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{protein_name}_{timestamp}.txt"
    file_path = results_dir / filename
    
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(text)
        return str(file_path)
    except Exception as e:
        print(f"Error saving results: {str(e)}")
        return None

# Updated query_pubmed to accept multiple proteins and custom search terms
def query_pubmed(protein_names: List[str], search_together: bool = False, additional_terms: List[Dict] = None) -> List[Dict]:
    """
    Query PubMed for papers about specific proteins with additional search terms.
    
    Parameters
    ----------
    protein_names : List[str]
        Names of proteins to search for
    search_together : bool
        If True, search for papers containing ALL proteins, otherwise any protein
    additional_terms : List[Dict]
        Additional search terms with operators
        
    Returns
    -------
    List[Dict]
        List of dictionaries containing paper information
    """
    # Load configuration
    config = load_config()
    num_papers = config.get('num_papers', 50)
    start_year = config.get('start_year', 2023)
    
    # Load gene aliases from TSV file
    project_root = Path(__file__).parent.parent
    tsv_path = project_root / 'proteinatlas_search.tsv'
    genes_df = load_gene_aliases(tsv_path)
    
    # Build protein search query parts
    protein_query_parts = []
    
    for protein_name in protein_names:
        search_query = protein_name
        if genes_df is not None:
            symbol, aliases, description = find_gene_and_aliases(protein_name, genes_df)
            if symbol:
                search_query = create_search_query(symbol, aliases, description)
        
        protein_query_parts.append(f"({search_query})")
    
    # Combine protein parts with AND or OR
    operator = " AND " if search_together else " OR "
    protein_query = operator.join(protein_query_parts)
    
    # Build additional terms query
    additional_query = ""
    if additional_terms:
        for i, term_data in enumerate(additional_terms):
            term = term_data.get('term', '').strip()
            if not term:
                continue
                
            if i == 0:
                additional_query = f"({term})"
            else:
                operator = term_data.get('operator', 'AND')
                additional_query += f" {operator} ({term})"
    
    # Combine queries
    query = f"({protein_query})"
    if additional_query:
        query += f" AND {additional_query}"
    
    # Add year filter
    query += f" AND ({start_year}:3000[Date - Publication])"
    
    # Set your email for Entrez
    Entrez.email = "your.email@example.com"  # Replace with your email
    
    try:
        # Search PubMed
        handle = Entrez.esearch(db="pubmed", term=query, retmax=num_papers, sort="relevance")
        record = Entrez.read(handle)
        handle.close()
        
        if not record["IdList"]:
            return []
            
        # Fetch details for each paper
        papers = []
        for pmid in record["IdList"]:
            # Add delay to respect NCBI's rate limits
            time.sleep(0.5)
            
            # Fetch paper details
            handle = Entrez.efetch(db="pubmed", id=pmid, rettype="medline", retmode="text")
            paper_record = handle.read()
            handle.close()
            
            # Parse the paper record
            paper_info = parse_pubmed_record(paper_record)
            if paper_info:
                papers.append(paper_info)
                
        return papers
        
    except Exception as e:
        print(f"Error querying PubMed: {str(e)}")
        return []

# Update summarize_papers_with_llm to include custom question
def summarize_papers_with_llm(papers: List[Dict], protein_names: List[str], custom_question: str = "") -> str:
    """
    Use OpenAI to summarize papers with custom questions.
    
    Parameters
    ----------
    papers : List[Dict]
        List of paper information
    protein_names : List[str]
        Names of proteins being researched
    custom_question : str
        Custom questions from the user
        
    Returns
    -------
    str
        Summary response from LLM
    """
    if not papers:
        return ""
        
    # Format proteins for prompt
    proteins_text = ", ".join(protein_names)
    
    # Prepare papers for the LLM
    papers_text = "\n\n".join([
        f"PMID: {p['PMID']}\nTitle: {p['Title']}\nAuthors: {p['Authors']}\n"
        f"Journal: {p['Journal']}\nYear: {p['Year']}\nAbstract: {p['Abstract']}\nDOI: {p['DOI']}"
        for p in papers
    ])
    
    # Build the base prompt
    prompt = f"""You are a research assistant specialized in neuroscience. 
    Analyze these papers about {proteins_text} and create a comprehensive summary.

    Papers to analyze:
    {papers_text}

    Create a summary that addresses the following:
    1. What are the key findings related to {proteins_text}?
    2. Has {proteins_text} been linked to any diseases or conditions? If yes, which ones?
    3. What cellular/molecular mechanisms involve {proteins_text}?
    4. Are there any therapeutic implications mentioned?
    """
    
    # Add custom question if provided
    if custom_question:
        prompt += f"\n\nAdditionally, please address this specific question from the user:\n{custom_question}\n"
    
    prompt += """
    Important requirements:
    - Write in clear, academic language
    - For each finding, cite the specific paper(s) it comes from
    - At the end, provide a References section with all cited papers in APA format
    - Each reference MUST include the DOI if available
    - Format references as: Author(s). (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/DOI
    - Only include information that is explicitly stated in the papers
    - Use proper scientific terminology

    Format the response as a well-structured text with clear paragraphs and a References section at the end.
    """

    # Count tokens in the prompt
    total_tokens = count_tokens(prompt)
    max_tokens = 120000  # Setting a safe limit below the model's 128K limit
    
    if total_tokens > max_tokens:
        # Reduce papers until we're under the limit
        while total_tokens > max_tokens and len(papers) > 1:
            papers = papers[:-1]  # Remove the last paper
            papers_text = "\n\n".join([
                f"PMID: {p['PMID']}\nTitle: {p['Title']}\nAuthors: {p['Authors']}\n"
                f"Journal: {p['Journal']}\nYear: {p['Year']}\nAbstract: {p['Abstract']}\nDOI: {p['DOI']}"
                for p in papers
            ])
            
            # Rebuild prompt with fewer papers
            prompt = f"""You are a research assistant specialized in neuroscience. 
            Analyze these papers about {proteins_text} and create a comprehensive summary.

            Papers to analyze:
            {papers_text}

            Create a summary that addresses the following:
            1. What are the key findings related to {proteins_text}?
            2. Has {proteins_text} been linked to any diseases or conditions? If yes, which ones?
            3. What cellular/molecular mechanisms involve {proteins_text}?
            4. Are there any therapeutic implications mentioned?
            """
            
            if custom_question:
                prompt += f"\n\nAdditionally, please address this specific question from the user:\n{custom_question}\n"
                
            prompt += """
            Important requirements:
            - Write in clear, academic language
            - For each finding, cite the specific paper(s) it comes from
            - At the end, provide a References section with all cited papers in APA format
            - Each reference MUST include the DOI if available
            - Format references as: Author(s). (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/DOI
            - Only include information that is explicitly stated in the papers
            - Use proper scientific terminology

            Format the response as a well-structured text with clear paragraphs and a References section at the end.
            """
            
            total_tokens = count_tokens(prompt)

    try:
        client = setup_openai()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a research assistant specialized in neuroscience. Your task is to analyze and summarize scientific papers, providing clear citations and a comprehensive overview of the findings. Only include information that is explicitly stated in the papers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.1
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error querying OpenAI: {str(e)}")
        return ""

# Update the search_endpoint function

@app.route('/api/search', methods=['POST'])
def search_endpoint():
    try:
        # Get data from request
        data = request.json
        
        # Validate required fields
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Extract API key and save it temporarily
        api_key = data.get('api_key')
        if not api_key:
            return jsonify({"error": "API key is required"}), 400
        
        os.environ["OPENAI_API_KEY"] = api_key
            
        # Extract protein names
        proteins_input = data.get('proteins', '')
        if not proteins_input:
            return jsonify({"error": "No proteins specified"}), 400
            
        protein_names = [p.strip() for p in proteins_input.split(',') if p.strip()]
        
        # Extract search mode
        search_together = data.get('search_proteins_together', False)
        
        # Extract search terms
        search_terms = data.get('search_terms', [])
        
        # Extract custom question
        question = data.get('question', '')
        
        # If we're searching together, do a single search
        if search_together:
            # Query PubMed for papers
            papers = query_pubmed(protein_names, search_together, search_terms)
            
            if not papers:
                return jsonify({
                    "success": True,
                    "mode": "together",
                    "proteins": protein_names,
                    "papers": [],
                    "summary": "No papers found matching your search criteria."
                })
                
            # Summarize papers using LLM
            summary = summarize_papers_with_llm(papers, protein_names, question)
            
            # Ensure results directory exists and save results
            results_dir = ensure_results_directory()
            protein_string = "_".join(protein_names)
            saved_file = save_results_to_txt(summary, protein_string, results_dir)
            
            # Format papers for response
            papers_for_response = []
            for paper in papers:
                papers_for_response.append({
                    "pmid": paper.get("PMID", ""),
                    "title": paper.get("Title", ""),
                    "authors": paper.get("Authors", ""),
                    "journal": paper.get("Journal", ""),
                    "year": paper.get("Year", ""),
                    "abstract": paper.get("Abstract", ""),
                    "doi": paper.get("DOI", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('PMID', '')}/",
                })
                
            # Return results
            return jsonify({
                "success": True,
                "mode": "together",
                "proteins": protein_names,
                "papers": papers_for_response,
                "summary": summary,
                "saved_file": saved_file if saved_file else None
            })
        
        # If we're searching separately (OR mode), do a search for each protein
        else:
            all_results = []
            
            for protein in protein_names:
                # Query PubMed for papers about this protein
                papers = query_pubmed([protein], True, search_terms)
                
                protein_summary = ""
                saved_file = None
                
                if papers:
                    # Summarize papers using LLM
                    protein_summary = summarize_papers_with_llm(papers, [protein], question)
                    
                    # Save results
                    results_dir = ensure_results_directory()
                    saved_file = save_results_to_txt(protein_summary, protein, results_dir)
                
                # Format papers for response
                papers_for_response = []
                for paper in papers:
                    papers_for_response.append({
                        "pmid": paper.get("PMID", ""),
                        "title": paper.get("Title", ""),
                        "authors": paper.get("Authors", ""),
                        "journal": paper.get("Journal", ""),
                        "year": paper.get("Year", ""),
                        "abstract": paper.get("Abstract", ""),
                        "doi": paper.get("DOI", ""),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('PMID', '')}/",
                    })
                
                all_results.append({
                    "protein": protein,
                    "papers": papers_for_response,
                    "summary": protein_summary if papers else f"No papers found for {protein}.",
                    "saved_file": saved_file
                })
            
            # Return all results
            return jsonify({
                "success": True,
                "mode": "separate",
                "results": all_results
            })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "ProtSearch API is running"})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8080)