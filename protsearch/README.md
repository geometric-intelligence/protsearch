# ProtSearch

**ProtSearch** is a web application that helps researchers discover and summarize scientific literature about proteins. It searches PubMed for relevant papers, validates protein names, and generates AI-powered summaries of the research findings.

## Features

- **Protein Search**: Search for scientific papers related to one or more proteins
- **Protein Validation**: Automatic validation and suggestions for protein names using gene alias services
- **Flexible Search Modes**: 
  - Search for papers containing all specified proteins together (AND mode)
  - Search for papers for each protein individually (OR mode)
- **Additional Search Terms**: Add custom search terms with AND/OR operators to refine results
- **AI-Powered Summaries**: Generate comprehensive summaries of research findings using AI
- **Real-time Results**: Stream search results as they're discovered
- **Paper Management**: View abstracts, access PubMed links, and copy content for further analysis

## Tech Stack

- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS
- **Backend API**: Flask (separate repository)
- **Icons**: Heroicons
- **State Management**: React Hooks, LocalStorage

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- A running ProtSearch API server (see backend repository)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd protsearch
```

2. Install dependencies:
```bash
npm install
```

3. Set up environment variables:
Create a `.env.local` file in the `protsearch` directory:
```env
NEXT_PUBLIC_API_BASE=https://your-api-server-url.com
```

4. Run the development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000) in your browser.

### Building for Production

```bash
npm run build
npm start
```

## Usage

1. **Enter Proteins**: Input one or more protein names (comma-separated), e.g., `ACE, APP, BACE1`

2. **Choose Search Mode**: 
   - Toggle to search for papers with ALL proteins together
   - Or search for each protein individually

3. **Add Search Terms** (Optional): Add additional terms to narrow your search with AND/OR operators

4. **Configure AI Summary** (Optional): Add specific questions or focus areas for the AI summary

5. **Start Search**: Click "Start Research" to begin searching

6. **Review Results**: 
   - View papers in the "Papers" tab
   - Read AI-generated summaries in the "AI Summary" tab
   - Copy abstracts or summaries for your research

## API Key (Optional)

You can optionally provide an API key for enhanced functionality:
- With API key: Uses full paper content when available, potentially better summaries
- Without API key: Uses abstracts only

The API key is stored securely in your browser (if you choose to remember it).

## Project Structure

```
protsearch/
├── src/
│   ├── app/
│   │   ├── page.tsx          # Main search interface
│   │   ├── results/
│   │   │   └── page.tsx      # Results display page
│   │   └── layout.tsx        # Root layout
│   ├── env.js                # Environment variable validation
│   └── styles/
│       └── globals.css       # Global styles
├── public/                   # Static assets
├── package.json
└── README.md
```

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint errors
- `npm run typecheck` - Run TypeScript type checking
- `npm run format:check` - Check code formatting
- `npm run format:write` - Format code

## Environment Variables

- `NEXT_PUBLIC_API_BASE` - Base URL for the ProtSearch API server (optional, has default fallback)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
