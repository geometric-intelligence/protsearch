# ProtSearch

**ProtSearch** is a full-stack web application that helps researchers discover and summarize scientific literature about proteins. It searches EuropePMC for relevant papers, validates protein names, and generates AI-powered summaries of the research findings.

## Features

- **Protein Search**: Search for scientific papers related to one or more proteins
- **Protein Validation**: Automatic validation and suggestions for protein names using gene alias services
- **Flexible Search Modes**: 
  - Search for papers containing all specified proteins together (AND mode)
  - Search for papers for each protein individually (OR mode)
- **Additional Search Terms**: Add custom search terms with AND/OR operators to refine results
- **AI-Powered Summaries**: Generate comprehensive summaries of research findings using AI (OpenAI or Google Gemini)
- **Paper Management**: View abstracts, access PubMed links, and copy content for further analysis

## Tech Stack

### Frontend
- **Framework**: Next.js 16, React 19, TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Heroicons
- **State Management**: React Hooks, LocalStorage

### Backend
- **Framework**: Flask (Python)
- **API**: RESTful API with Server-Sent Events for streaming
- **Services**: 
  - EuropePMC integration for paper search
  - Gene alias validation
  - OpenAI/Gemini integration for AI summaries
  - UniProt integration
- **Deployment**: Docker-ready with Gunicorn

## Project Structure

```
protsearchself/
├── protsearch/              # Frontend (Next.js)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Main search interface
│   │   │   ├── results/
│   │   │   │   └── page.tsx      # Results display page
│   │   │   └── layout.tsx        # Root layout
│   │   ├── env.js                # Environment variable validation
│   │   └── styles/
│   │       └── globals.css       # Global styles
│   ├── public/                   # Static assets
│   └── package.json
├── backend/                 # Backend API (Flask)
│   ├── app.py                    # Flask app entry point
│   ├── api/
│   │   └── src/
│   │       ├── index.py          # Main API routes
│   │       ├── services/         # Backend services
│   │       │   ├── pubmedhelper.py
│   │       │   ├── genealias.py
│   │       │   ├── llmhelper.py
│   │       │   ├── summarizationwrapper.py
│   │       │   └── uniprothelper.py
│   │       └── config.yaml
│   ├── requirements.txt
│   └── Dockerfile
├── requirements.txt         # Root-level Python dependencies
└── pyproject.toml          # Python project configuration
```

## Getting Started

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.8+ (for backend)
- **API Keys** (optional but recommended):
  - OpenAI API key OR Google Gemini API key for AI summaries
  - Without API keys, the system will use abstracts only

### Installation

#### 1. Clone the Repository

```bash
git clone <repository-url>
cd protsearch
```

#### 2. Backend Setup

```bash
cd backend

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
# Create a .env file in the backend directory:
# OPENAI_API_KEY=your_key_here (optional)
# GOOGLE_API_KEY=your_key_here (optional)
```

#### 3. Frontend Setup

```bash
cd ../protsearch

# Install dependencies
npm install

# Set up environment variables (optional)
# Create a .env.local file:
# NEXT_PUBLIC_API_BASE=http://localhost:8080
```

### Running the Application

#### Development Mode

**Terminal 1 - Backend:**
```bash
cd backend
python app.py
# Backend will run on http://localhost:8080
```

**Terminal 2 - Frontend:**
```bash
cd protsearch
npm run dev
# Frontend will run on http://localhost:3000
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

#### Production Mode

**Backend:**
```bash
cd backend
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 app:app
```

**Frontend:**
```bash
cd protsearch
npm run build
npm start
```

#### Docker Deployment

The backend includes a Dockerfile for containerized deployment:

```bash
cd backend
docker build -t protsearch-api .
docker run -p 8080:8080 -e PORT=8080 protsearch-api
```

## Usage

1. **Enter Proteins**: Input one or more protein names (comma-separated), e.g., `ACE, APP, BACE1`

2. **Choose Search Mode**: 
   - Toggle to search for papers with ALL proteins together
   - Or search for each protein individually

3. **Add Search Terms** (Optional): Add additional terms to narrow your search with AND/OR operators

4. **Configure AI Summary** (Optional): Add specific questions or focus areas for the AI summary

5. **Provide API Key** (Optional): Enter your OpenAI or Google Gemini API key for enhanced summaries

6. **Start Search**: Click "Start Research" to begin searching

7. **Review Results**: 
   - View papers in the "Papers" tab as they stream in
   - Read AI-generated summaries in the "AI Summary" tab
   - Copy abstracts or summaries for your research

## API Endpoints

The backend provides the following endpoints:

- `POST /api/search_start` - Start a new search session
- `GET /api/search_events?session_id=<id>` - Stream search results via SSE
- `POST /api/suggest` - Get protein name suggestions/validation
- `POST /api/summarize` - Generate AI summary for a session

## Environment Variables

### Backend (.env in backend directory)
- `OPENAI_API_KEY` - OpenAI API key for summaries (optional)
- `GOOGLE_API_KEY` - Google Gemini API key for summaries (optional)
- `PORT` - Server port (default: 8080)
- `LOGLEVEL` - Logging level (default: INFO)

### Frontend (.env.local in protsearch directory)
- `NEXT_PUBLIC_API_BASE` - Backend API URL (default: production API URL)

## Development

### Frontend Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint errors
- `npm run typecheck` - Run TypeScript type checking
- `npm run format:check` - Check code formatting
- `npm run format:write` - Format code

### Backend Development

The backend uses Flask with threading for concurrent request handling. Key services:

- **pubmedhelper.py**: PubMed API integration
- **genealias.py**: Gene name validation and alias resolution
- **llmhelper.py**: OpenAI/Gemini integration
- **summarizationwrapper.py**: Summary generation orchestration
- **uniprothelper.py**: UniProt database integration

## API Key Usage

API keys are optional but enhance functionality:

- **With API Key**: 
  - Uses full paper content when available
  - Better quality AI summaries
  - Access to more comprehensive results

- **Without API Key**: 
  - Uses abstracts only
  - Limited summary capabilities
  - Still fully functional for paper discovery

API keys can be provided:
1. In the frontend UI (stored in browser cookies)
2. As environment variables in the backend
3. Per-request in API calls

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Notes

- The backend uses Server-Sent Events (SSE) for real-time result streaming
- Session management is handled in-memory (consider Redis for production scaling)
- The frontend stores results in localStorage for persistence across page refreshes
