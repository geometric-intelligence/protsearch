"use client";

import React, { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { BeakerIcon, ArrowLeftIcon, ClipboardIcon, ArrowTopRightOnSquareIcon, ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/24/outline";
import Link from 'next/link';
import Cookies from 'js-cookie';

export const dynamic = 'force-dynamic';

const SHOW_DEBUG = false;

interface Paper {
  pmid: string;
  title: string;
  authors: string;
  journal: string;
  year: string;
  abstract: string;
  doi: string;
  url: string;
}

interface SingleResult {
  protein: string;
  papers: Paper[];
  summary: string | null;
  saved_file: string | null;
}

interface ResultsData {
  session_id: string;
  mode: "together" | "separate";
  proteins: string[];
  papers: Paper[] | null;
  results: SingleResult[] | null;
  summary?: string | null;
  saved_file?: string | null;
  summaryLoading: boolean;
  summaryError: string | null;
}

const normalizePaper = (raw: any): Paper => {
  const pmid = String(raw?.PMID ?? raw?.pmid ?? "").trim();
  return {
    pmid,
    title: String(raw?.Title ?? raw?.title ?? "No Title"),
    authors: String(raw?.Authors ?? raw?.authors ?? "No Authors"),
    journal: String(raw?.Journal ?? raw?.journal ?? "No Journal"),
    year: String(raw?.Year ?? raw?.year ?? "Unknown Year"),
    abstract: String(raw?.Abstract ?? raw?.abstract ?? "No Abstract Available"),
    doi: String(raw?.DOI ?? raw?.doi ?? ""),
    url: pmid ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : String(raw?.url ?? ""),
  };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://protsearch-backend-312141936151.us-central1.run.app";

const PaperList = ({ papers, expandedAbstracts, toggleAbstract, copyToClipboard, copiedText }: {
  papers: Paper[];
  expandedAbstracts: Record<string, boolean>;
  toggleAbstract: (pmid: string) => void;
  copyToClipboard: (text: string, label: string) => void;
  copiedText: string | null;
}) => {
  if (papers.length === 0) return <div className="text-center py-12 text-gray-500">Searching for papers...</div>;
  return (
    <div className="space-y-4">
      {papers.map(paper => (
        <div key={paper.pmid} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 className="font-semibold text-lg text-gray-900">{cleanText(paper.title)}</h3>
          <p className="text-sm text-gray-600 my-1">{paper.authors}</p>
          <div className="flex flex-wrap items-center text-xs text-gray-500 gap-x-3 gap-y-1 mb-2">
            <span>{paper.journal} ({paper.year})</span>
            {paper.doi && <span>DOI: <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{paper.doi}</a></span>}
          </div>
          {paper.abstract && paper.abstract.trim() ? (
            <p className={`text-sm text-gray-700 transition-all duration-300 ${expandedAbstracts[paper.pmid] ? 'max-h-full' : 'line-clamp-3'}`}>
              {cleanText(paper.abstract)}
            </p>
          ) : (
            <p className="text-sm text-gray-500 italic">No abstract available</p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={() => toggleAbstract(paper.pmid)} className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center">
              {expandedAbstracts[paper.pmid] ? <ChevronUpIcon className="h-3 w-3 mr-1" /> : <ChevronDownIcon className="h-3 w-3 mr-1" />}
              {expandedAbstracts[paper.pmid] ? 'Show Less' : 'Show More'}
            </button>
            <a href={paper.url} target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center">
              <ArrowTopRightOnSquareIcon className="h-3 w-3 mr-1" />PubMed
            </a>
            <button onClick={() => copyToClipboard(paper.abstract, `abstract-${paper.pmid}`)} className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center">
              <ClipboardIcon className="h-3 w-3 mr-1" />{copiedText === `abstract-${paper.pmid}` ? 'Copied!' : 'Copy Abstract'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

// Text cleaning for paper display: decode entities like &lt;i&gt; and remove all tags
function decodeEntities(s: string): string {
  return (s ?? '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function cleanText(s: string): string {
  const decoded = decodeEntities(s ?? '');
  const withoutTags = decoded.replace(/<[^>]*>/g, '');
  return withoutTags;
}

// Summary formatting (unchanged from your current file)
function escapeHtml(s: string): string {
  return (s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Protect code spans then replace paired markers exactly
function formatInlineExactMarkers(input: string): string {
  const CODE_PH = '\u0000CODE\u0000';
  const codes: string[] = [];
  let out = input ?? '';

  // Protect code: store HTML-escaped code content
  out = out.replace(/`([^`]+)`/g, (_m, code) => {
    const idx = codes.push(`<code>${escapeHtml(code)}</code>`) - 1;
    return `${CODE_PH}${idx}${CODE_PH}`;
  });

  // Bold pass: scan and alternate opening/closing tags on '**'
  out = replacePairedMarkers(out, '**', 'strong');

  // Italic pass: scan and alternate on single '*', skipping '**'
  out = replacePairedMarkers(out, '*', 'em');

  // Restore code placeholders
  out = out.replace(new RegExp(`${CODE_PH}(\\d+)${CODE_PH}`, 'g'), (_m, i) => codes[Number(i)] || '');

  return out;
}

// Marker scanner that preserves text and toggles tags for each pair
function replacePairedMarkers(text: string, marker: '*' | '**', tag: 'strong' | 'em'): string {
  let result = '';
  let i = 0;
  let open = false;

  while (i < text.length) {
    if (marker === '**') {
      if (text[i] === '*' && text[i + 1] === '*') {
        result += open ? `</${tag}>` : `<${tag}>`;
        open = !open;
        i += 2;
        continue;
      }
    } else {
      if (text[i] === '*') {
        if (text[i + 1] === '*') {
          result += text[i];
          i += 1;
          continue;
        }
        result += open ? `</${tag}>` : `<${tag}>`;
        open = !open;
        i += 1;
        continue;
      }
    }
    result += text[i];
    i += 1;
  }

  if (open) {
    const openTag = `<${tag}>`;
    const pos = result.lastIndexOf(openTag);
    if (pos !== -1) {
      result = result.slice(0, pos) + marker + result.slice(pos + openTag.length);
    }
  }
  return result;
}

// Render summary preserving line breaks
function FormattedSummary({ text }: { text: string }) {
  const raw = text ?? '';
  const paragraphs = raw.split(/\r?\n\r?\n/);

  const renderParaHtml = (para: string) => {
    const withMarkers = formatInlineExactMarkers(escapeHtml(para));
    const withBr = withMarkers.replace(/\r?\n/g, '<br>');
    return withBr;
  };

  return (
    <div className="prose max-w-none">
      {paragraphs.map((p, idx) => (
        <p key={idx} dangerouslySetInnerHTML={{ __html: renderParaHtml(p) }} />
      ))}
    </div>
  );
}

const SummaryView = ({ summary, loading, error, copyToClipboard }: {
  summary: string | null | undefined;
  loading: boolean;
  error: string | null;
  copyToClipboard: (text: string, label: string) => void;
}) => (
  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
    <div className="flex justify-between items-center mb-4">
      <h2 className="text-xl font-semibold text-gray-800">AI Research Summary</h2>
      {summary && <button onClick={() => copyToClipboard(summary, 'summary')} className="text-sm font-medium text-indigo-600 hover:text-indigo-800 flex items-center"><ClipboardIcon className="h-4 w-4 mr-1" />Copy</button>}
    </div>
    {loading && <div className="text-center py-12 text-gray-600">Generating AI summary...</div>}
    {error && <div className="bg-red-50 text-red-700 p-3 rounded-md">{error}</div>}
    {summary && <FormattedSummary text={summary} />}
  </div>
);

const DebugPanel = ({ debugMessages, onReset }: { debugMessages: string[], onReset: () => void }) => (
  <div className="fixed bottom-4 right-4 bg-gray-800 text-white rounded-lg p-4 shadow-lg max-w-sm w-full z-50 hidden">
    <div className="flex justify-between items-center mb-2">
      <h3 className="font-bold text-sm">Debug Info</h3>
      <button onClick={onReset} className="px-2 py-1 text-xs bg-red-500 rounded">Reset & Start Over</button>
    </div>
    <div className="text-xs font-mono h-48 overflow-y-auto bg-gray-900 p-2 rounded">
      {debugMessages.map((msg, i) => <div key={i}>{msg}</div>)}
    </div>
  </div>
);

function ResultsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [results, setResults] = useState<ResultsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [debugMessages, setDebugMessages] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'papers' | 'summary'>('papers');
  const [activeProteinIndex, setActiveProteinIndex] = useState(0);
  const [expandedAbstracts, setExpandedAbstracts] = useState<Record<string, boolean>>({});
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const didSummarizeRef = useRef(false);

  const addDebug = useCallback((msg: string) => {
    console.log(`[ProtSearch Debug] ${msg}`);
    setDebugMessages(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 49)]);
  }, []);

  const handleSummarization = useCallback(async (sessionId: string) => {
    addDebug("Starting summary generation...");
    setResults(prev => prev ? { ...prev, summaryLoading: true, summaryError: null } : null);
    try {
      const apiKey = Cookies.get('protsearch_api_key') || '';
      const resp = await fetch(`${API_BASE}/api/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, api_key: apiKey }),
      });
      if (!resp.ok) {
        const errorText = await resp.text();
        throw new Error(`Summary failed (${resp.status}): ${errorText}`);
      }
      const summaryData = await resp.json();
      addDebug("Summary received successfully.");
      setResults(prev => {
        if (!prev) return null;
        let updated: ResultsData = { ...prev, summaryLoading: false };
        if (prev.mode === 'together') {
          updated.summary = summaryData.summary ?? null;
          updated.saved_file = summaryData.saved_file ?? null;
        } else if (prev.mode === 'separate' && summaryData.summaries) {
          updated.results = (prev.results || []).map(r => {
            const match = summaryData.summaries.find((s: any) => s.protein.toLowerCase() === r.protein.toLowerCase());
            return match ? { ...r, summary: match.summary, saved_file: match.saved_file } : r;
          });
        }
        localStorage.setItem('protsearch_results', JSON.stringify(updated));
        return updated;
      });
    } catch (e: any) {
      addDebug(`Summary error: ${e.message}`);
      setResults(prev => {
        if (!prev) return null;
        const updated = { ...prev, summaryLoading: false, summaryError: e.message };
        localStorage.setItem('protsearch_results', JSON.stringify(updated));
        return updated;
      });
    }
  }, [addDebug]);

  const handleSummarizationRef = useRef(handleSummarization);
  useEffect(() => { handleSummarizationRef.current = handleSummarization; });

  useEffect(() => {
    const sessionIdFromUrl = searchParams.get('session_id');
    const storedSessionId = localStorage.getItem('protsearch_session_id');
    if (sessionIdFromUrl) {
      if (sessionIdFromUrl !== storedSessionId) {
        addDebug(`New session ID from URL: ${sessionIdFromUrl}. Clearing stale data.`);
        localStorage.removeItem('protsearch_results');
        localStorage.removeItem('protsearch_session_id');
        sessionStorage.removeItem('protsearch_sse_done');
        sessionStorage.removeItem('protsearch_sse_done_session_id');
        didSummarizeRef.current = false;
        setResults(null);
      }
      localStorage.setItem('protsearch_session_id', sessionIdFromUrl);
    }
    const sessionId = sessionIdFromUrl || storedSessionId;
    if (!sessionId) {
      addDebug("No session ID. Redirecting home.");
      router.push('/');
      return;
    }
    const storedResultsJson = localStorage.getItem('protsearch_results');
    if (storedResultsJson) {
      try {
        const parsed: ResultsData = JSON.parse(storedResultsJson);
        if (parsed.session_id === sessionId) {
          setResults(parsed);
          addDebug(`Loaded results from storage for ${sessionId}.`);
        } else {
          localStorage.removeItem('protsearch_results');
        }
      } catch {
        localStorage.removeItem('protsearch_results');
      }
    }
    const sseDone = sessionStorage.getItem('protsearch_sse_done') === 'true';
    const sseDoneSessionId = sessionStorage.getItem('protsearch_sse_done_session_id');
    if (sseDone && sseDoneSessionId === sessionId) {
      addDebug("SSE already done for this session.");
      const stored = localStorage.getItem('protsearch_results');
      if (stored) {
        const parsed: ResultsData = JSON.parse(stored);
        if (parsed.session_id === sessionId) {
          const needsSummary = parsed.summaryLoading || (!parsed.summary && !parsed.summaryError && !parsed.results?.every(r => r.summary || r.summary === ""));
          if (needsSummary && !didSummarizeRef.current) {
            didSummarizeRef.current = true;
            handleSummarizationRef.current(sessionId);
          }
        }
      }
      return;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    addDebug(`Connecting SSE for session ${sessionId}`);
    const es = new EventSource(`${API_BASE}/api/search_events?session_id=${encodeURIComponent(sessionId)}`);
    esRef.current = es;

    es.onopen = () => addDebug("SSE opened.");
    es.onerror = () => addDebug(`SSE error. State: ${es.readyState}`);

    const handleEvent = (eventName: string, handler: (data: any) => void) => {
      es.addEventListener(eventName, (ev: MessageEvent) => {
        try {
          if (!ev.data || ev.data === 'undefined' || ev.data.trim() === '') return;
          handler(JSON.parse(ev.data));
        } catch (e) {
          addDebug(`Parse error on ${eventName}: ${e}`);
        }
      });
    };

    handleEvent('started', data => {
      addDebug(`Started event. Mode: ${data.mode}`);
      setResults(prev => {
        if (prev && prev.session_id === sessionId) return prev;
        const init: ResultsData = {
          session_id: sessionId,
          mode: data.mode,
          proteins: data.proteins || [],
          papers: data.mode === 'together' ? [] : null,
          results: data.mode === 'separate' ? data.proteins.map((p: string) => ({
            protein: p, papers: [], summary: null, saved_file: null
          })) : null,
          summaryLoading: true,
          summaryError: null
        };
        localStorage.setItem('protsearch_results', JSON.stringify(init));
        return init;
      });
    });

    handleEvent('paper', data => {
      const uiPaper = normalizePaper(data.paper);
      setResults(prev => {
        if (!prev || prev.session_id !== sessionId) return prev;
        const copy = { ...prev };
        if (copy.mode === 'together') {
          copy.papers = [...(copy.papers || []), uiPaper];
        } else if (copy.mode === 'separate' && Array.isArray(copy.results)) {
          copy.results = copy.results.map(r =>
            r.protein.toLowerCase() === String(data.protein || '').toLowerCase()
              ? { ...r, papers: [...r.papers, uiPaper] }
              : r
          );
        }
        localStorage.setItem('protsearch_results', JSON.stringify(copy));
        return copy;
      });
    });

    handleEvent('error', data => {
      addDebug(`Server error event: ${data.message}`);
      setError(data.message || 'Error');
    });

    es.addEventListener('done', () => {
      addDebug("Done event. Closing SSE.");
      es.close();
      esRef.current = null;
      sessionStorage.setItem('protsearch_sse_done', 'true');
      sessionStorage.setItem('protsearch_sse_done_session_id', sessionId);
      if (!didSummarizeRef.current) {
        didSummarizeRef.current = true;
        handleSummarizationRef.current(sessionId);
      }
    });

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [searchParams, addDebug, router]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedText(label);
      setTimeout(() => setCopiedText(null), 2000);
    });
  };

  const toggleAbstract = (pmid: string) => {
    setExpandedAbstracts(prev => ({ ...prev, [pmid]: !prev[pmid] }));
  };

  const handleReset = () => {
    addDebug("Resetting state.");
    localStorage.removeItem('protsearch_session_id');
    localStorage.removeItem('protsearch_results');
    sessionStorage.removeItem('protsearch_sse_done');
    sessionStorage.removeItem('protsearch_sse_done_session_id');
    router.push('/');
  };

  if (error) {
    return <div className="text-red-500 p-4">Error: {error} <button onClick={handleReset} className="ml-4 text-blue-500">Restart</button></div>;
  }
  if (!results) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin h-10 w-10 border-4 border-indigo-600 border-t-transparent rounded-full"></div>
        {SHOW_DEBUG && <DebugPanel debugMessages={[]} onReset={handleReset} />}
      </div>
    );
  }

  const papers = results.mode === 'together' ? results.papers || [] : results.results?.[activeProteinIndex]?.papers || [];
  const summary = results.mode === 'together' ? results.summary : results.results?.[activeProteinIndex]?.summary;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <BeakerIcon className="h-8 w-8 text-indigo-600" />
              <h1 className="text-2xl font-bold text-gray-800">ProtSearch</h1>
            </div>
            <Link href="/" className="text-sm font-medium text-gray-600 hover:text-indigo-600 flex items-center">
              <ArrowLeftIcon className="h-4 w-4 mr-1" /> New Search
            </Link>
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-6">
        <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          {results.mode === 'separate' && results.results && (
            <div className="flex-grow overflow-x-auto whitespace-nowrap pb-2">
              {results.results.map((result, index) => (
                <button
                  key={index}
                  onClick={() => setActiveProteinIndex(index)}
                  className={`px-4 py-2 mx-1 text-sm font-medium rounded-lg transition-colors ${index === activeProteinIndex ? 'bg-indigo-600 text-white shadow' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-100'}`}
                >
                  {result.protein} ({result.papers.length})
                </button>
              ))}
            </div>
          )}
          <div className="inline-flex rounded-lg shadow-sm self-center">
            <button
              onClick={() => setActiveTab('papers')}
              className={`px-4 py-2 text-sm font-medium border border-gray-300 rounded-l-lg ${activeTab === 'papers' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700'}`}
            >
              Papers ({papers.length})
            </button>
            <button
              onClick={() => setActiveTab('summary')}
              className={`px-4 py-2 text-sm font-medium border border-gray-300 rounded-r-lg flex items-center ${activeTab === 'summary' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700'}`}
            >
              AI Summary {results.summaryLoading && <span className="ml-2 w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>}
            </button>
          </div>
        </div>
        {activeTab === 'papers'
          ? <PaperList papers={papers} expandedAbstracts={expandedAbstracts} toggleAbstract={toggleAbstract} copyToClipboard={copyToClipboard} copiedText={copiedText} />
          : <SummaryView summary={summary || null} loading={results.summaryLoading} error={results.summaryError} copyToClipboard={copyToClipboard} />}
        {SHOW_DEBUG && <DebugPanel debugMessages={debugMessages} onReset={handleReset} />}
      </main>
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin h-10 w-10 border-4 border-indigo-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-gray-600">Loading results...</p>
        </div>
      </div>
    }>
      <ResultsContent />
    </Suspense>
  );
}