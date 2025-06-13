# ProtSearch

A Python package for protein search and analysis, currently focused on dementia-related research.

## Installation

### Using Conda (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/protsearch.git
cd protsearch

# Create and activate a conda environment with Python 3.12
conda create -n protsearch python=3.12
conda activate protsearch

# Install the package in development mode
pip install -e .
```

## Usage

1. Get an OpenAI API key:
   - Go to [OpenAI's website](https://platform.openai.com/api-keys)
   - Create an account or sign in
   - Generate a new API key
   - Export the key in your terminal:
     ```bash
     export OPENAI_API_KEY='your-api-key-here'
     ```

2. Configure your search parameters in `config.yaml`:
   ```yaml
   # Number of relevant papers to retrieve from PubMed
   num_papers: 50

   # Year to start searching from in PubMed (e.g., 2023 means papers from 2023 onwards)
   start_year: 2023
   ```

3. Run the program:
   ```bash
   python src/main.py
   ```

4. When prompted, enter the name of the protein you want to search for.

The program will:
- Search PubMed for papers about the specified protein
- Focus on papers related to dementia and neuroscience
- Generate a summary of the findings
- Save the results in a text file

Note: Currently, the search is optimized for dementia-related research. The program will look for papers that mention the protein in the context of dementia, brain disorders, and neuroscience.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.