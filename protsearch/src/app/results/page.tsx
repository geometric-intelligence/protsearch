"use client";

import React, { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { ArrowLeftIcon, ClipboardIcon, ArrowTopRightOnSquareIcon, ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/24/outline";
import Link from 'next/link';
import Cookies from 'js-cookie';
import PageBackground from "~/components/PageBackground";
import TopBar from "~/components/TopBar";

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
  if (papers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-white py-16 text-center">
        <div className="mb-4 h-9 w-9 animate-spin rounded-full border-2 border-brand/20 border-t-brand" />
        <p className="text-sm font-medium text-gray-700">Finding papers...</p>
        <p className="mt-1 text-xs text-muted">This may take a moment</p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {papers.map((paper) => (
        <article
          key={paper.pmid}
          className="card-hover rounded-xl border border-border bg-white p-5"
        >
          <h3 className="text-base font-semibold leading-snug text-gray-900">
            {cleanText(paper.title)}
          </h3>
          <p className="my-2 text-sm text-gray-600">{paper.authors}</p>
          <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span className="rounded-full bg-brand-muted/80 px-2.5 py-0.5 font-medium text-brand">
              {paper.journal} ({paper.year})
            </span>
            {paper.doi && (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand hover:underline"
              >
                DOI: {paper.doi}
              </a>
            )}
          </div>
          {paper.abstract && paper.abstract.trim() ? (
            <p
              className={`text-sm leading-relaxed text-gray-700 transition-all duration-300 ${
                expandedAbstracts[paper.pmid] ? "max-h-full" : "line-clamp-3"
              }`}
            >
              {cleanText(paper.abstract)}
            </p>
          ) : (
            <p className="text-sm italic text-muted">No abstract available</p>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={() => toggleAbstract(paper.pmid)}
              className="flex items-center rounded-full bg-brand-muted/60 px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-muted"
            >
              {expandedAbstracts[paper.pmid] ? (
                <ChevronUpIcon className="mr-1 h-3.5 w-3.5" />
              ) : (
                <ChevronDownIcon className="mr-1 h-3.5 w-3.5" />
              )}
              {expandedAbstracts[paper.pmid] ? "Show less" : "Show more"}
            </button>
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center rounded-full bg-brand-muted/60 px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-muted"
            >
              <ArrowTopRightOnSquareIcon className="mr-1 h-3.5 w-3.5" />
              PubMed
            </a>
            <button
              onClick={() => copyToClipboard(paper.abstract, `abstract-${paper.pmid}`)}
              className="flex items-center rounded-full bg-brand-muted/60 px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-muted"
            >
              <ClipboardIcon className="mr-1 h-3.5 w-3.5" />
              {copiedText === `abstract-${paper.pmid}` ? "Copied!" : "Copy abstract"}
            </button>
          </div>
        </article>
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

// Summary markdown rendering (headers, lists, bold/italic)
function escapeHtml(s: string): string {
  return (s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatInlineExactMarkers(input: string): string {
  const CODE_PH = '\u0000CODE\u0000';
  const codes: string[] = [];
  let out = input ?? '';

  out = out.replace(/`([^`]+)`/g, (_m, code) => {
    const idx = codes.push(`<code class="rounded bg-gray-100 px-1 py-0.5 text-sm">${escapeHtml(code)}</code>`) - 1;
    return `${CODE_PH}${idx}${CODE_PH}`;
  });

  out = replacePairedMarkers(out, '**', 'strong');
  out = replacePairedMarkers(out, '*', 'em');

  out = out.replace(new RegExp(`${CODE_PH}(\\d+)${CODE_PH}`, 'g'), (_m, i) => codes[Number(i)] || '');

  return out;
}

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

function renderInlineHtml(text: string): string {
  return formatInlineExactMarkers(escapeHtml(text));
}

function isBlockStart(line: string): boolean {
  const trimmed = line.trim();
  return (
    /^#{1,3}\s/.test(trimmed) ||
    /^[-*]\s/.test(trimmed) ||
    /^\d+\.\s/.test(trimmed)
  );
}

function FormattedSummary({ text }: { text: string }) {
  const lines = (text ?? '').split(/\r?\n/);
  const elements: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i] ?? '';
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (trimmed.startsWith('### ')) {
      elements.push(
        <h3
          key={key++}
          className="mt-4 mb-2 text-base font-semibold text-gray-900"
          dangerouslySetInnerHTML={{ __html: renderInlineHtml(trimmed.slice(4)) }}
        />
      );
      i += 1;
      continue;
    }

    if (trimmed.startsWith('## ')) {
      elements.push(
        <h2
          key={key++}
          className="mt-6 mb-3 border-b border-border pb-1 text-lg font-semibold text-gray-900 first:mt-0"
          dangerouslySetInnerHTML={{ __html: renderInlineHtml(trimmed.slice(3)) }}
        />
      );
      i += 1;
      continue;
    }

    if (trimmed.startsWith('# ')) {
      elements.push(
        <h1
          key={key++}
          className="mb-4 text-xl font-bold text-gray-900"
          dangerouslySetInnerHTML={{ __html: renderInlineHtml(trimmed.slice(2)) }}
        />
      );
      i += 1;
      continue;
    }

    if (/^[-*]\s/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const current = (lines[i] ?? '').trim();
        if (!/^[-*]\s/.test(current)) break;
        items.push(current.replace(/^[-*]\s+/, ''));
        i += 1;
      }
      elements.push(
        <ul key={key++} className="my-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-gray-700">
          {items.map((item, idx) => (
            <li key={idx} dangerouslySetInnerHTML={{ __html: renderInlineHtml(item) }} />
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const current = (lines[i] ?? '').trim();
        if (!/^\d+\.\s/.test(current)) break;
        items.push(current.replace(/^\d+\.\s+/, ''));
        i += 1;
      }
      elements.push(
        <ol key={key++} className="summary-ref-list my-3 list-decimal space-y-3 pl-5 text-sm leading-relaxed text-gray-700">
          {items.map((item, idx) => (
            <li key={idx} className="pl-1" dangerouslySetInnerHTML={{ __html: renderInlineHtml(item) }} />
          ))}
        </ol>
      );
      continue;
    }

    const paraLines: string[] = [];
    while (i < lines.length) {
      const current = lines[i] ?? '';
      if (!current.trim() || isBlockStart(current)) break;
      paraLines.push(current.trim());
      i += 1;
    }
    elements.push(
      <p
        key={key++}
        className="my-3 text-sm leading-relaxed text-gray-700"
        dangerouslySetInnerHTML={{ __html: renderInlineHtml(paraLines.join(' ')) }}
      />
    );
  }

  return <div className="summary-content max-w-none">{elements}</div>;
}

const SummaryView = ({ summary, loading, error, copyToClipboard }: {
  summary: string | null | undefined;
  loading: boolean;
  error: string | null;
  copyToClipboard: (text: string, label: string) => void;
}) => (
  <div className="rounded-xl border border-border bg-white p-6 shadow-sm">
    <div className="mb-5 flex items-center justify-between">
      <h2 className="text-lg font-semibold text-gray-900">AI Research Summary</h2>
      {summary && (
        <button
          onClick={() => copyToClipboard(summary, "summary")}
          className="flex items-center rounded-full bg-brand-muted/70 px-3 py-1.5 text-sm font-medium text-brand transition-colors hover:bg-brand-muted"
        >
          <ClipboardIcon className="mr-1 h-4 w-4" />
          Copy
        </button>
      )}
    </div>
    {loading && (
      <div className="flex flex-col items-center py-16 text-center">
        <div className="mb-4 h-10 w-10 animate-spin rounded-full border-4 border-brand border-t-transparent" />
        <p className="text-sm font-medium text-gray-700">Crafting your summary...</p>
      </div>
    )}
    {error && (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </div>
    )}
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
      <PageBackground>
        <TopBar />
        <div className="flex min-h-[calc(100vh-3.5rem)] flex-col items-center justify-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-brand border-t-transparent" />
          <p className="text-sm text-muted">Loading your research...</p>
          {SHOW_DEBUG && <DebugPanel debugMessages={[]} onReset={handleReset} />}
        </div>
      </PageBackground>
    );
  }

  const papers = results.mode === 'together' ? results.papers || [] : results.results?.[activeProteinIndex]?.papers || [];
  const summary = results.mode === 'together' ? results.summary : results.results?.[activeProteinIndex]?.summary;

  return (
    <PageBackground>
      <TopBar />
      <div className="mx-auto max-w-4xl px-6 py-8">
        {results.proteins && results.proteins.length > 0 && (
          <p className="mb-6 text-sm text-muted animate-fade-up">
            Researching{" "}
            <span className="font-medium text-gray-800">
              {results.proteins.join(", ")}
            </span>
          </p>
        )}

        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between animate-fade-up-delay-1">
          <Link
            href="/"
            className="card-hover inline-flex w-fit items-center rounded-lg border border-border bg-white px-3 py-2 text-sm font-medium text-gray-700"
          >
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            New search
          </Link>

          <div className="inline-flex rounded-full border border-border bg-white p-1 shadow-sm">
            <button
              onClick={() => setActiveTab("papers")}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === "papers"
                  ? "bg-brand text-white"
                  : "text-muted hover:text-gray-800"
              }`}
            >
              Papers ({papers.length})
            </button>
            <button
              onClick={() => setActiveTab("summary")}
              className={`flex items-center rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === "summary"
                  ? "bg-brand text-white"
                  : "text-muted hover:text-gray-800"
              }`}
            >
              AI Summary
              {results.summaryLoading && (
                <span className="ml-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              )}
            </button>
          </div>
        </div>

        {results.mode === "separate" && results.results && (
          <div className="mb-6 flex gap-2 overflow-x-auto pb-1">
            {results.results.map((result, index) => (
              <button
                key={index}
                onClick={() => setActiveProteinIndex(index)}
                className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  index === activeProteinIndex
                    ? "bg-brand text-white"
                    : "border border-border bg-white text-gray-700 hover:bg-brand-muted"
                }`}
              >
                {result.protein} ({result.papers.length})
              </button>
            ))}
          </div>
        )}

        {activeTab === 'papers' ? (
          <PaperList
            papers={papers}
            expandedAbstracts={expandedAbstracts}
            toggleAbstract={toggleAbstract}
            copyToClipboard={copyToClipboard}
            copiedText={copiedText}
          />
        ) : (
          <SummaryView
            summary={summary || null}
            loading={results.summaryLoading}
            error={results.summaryError}
            copyToClipboard={copyToClipboard}
          />
        )}
        {SHOW_DEBUG && <DebugPanel debugMessages={debugMessages} onReset={handleReset} />}
      </div>
    </PageBackground>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={
      <PageBackground>
        <TopBar />
        <div className="flex min-h-[calc(100vh-3.5rem)] flex-col items-center justify-center gap-3">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-brand border-t-transparent" />
          <p className="text-sm text-muted">Loading results...</p>
        </div>
      </PageBackground>
    }>
      <ResultsContent />
    </Suspense>
  );
}