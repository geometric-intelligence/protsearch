"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  PlusIcon,
  MinusIcon,
  ArrowRightIcon,
  ChevronDownIcon,
  LightBulbIcon,
} from "@heroicons/react/24/outline";
import Cookies from "js-cookie";
import PageBackground from "~/components/PageBackground";
import TopBar from "~/components/TopBar";
import { SITE_BLURB } from "~/components/SiteTagline";
import SuggestionsPanel from "~/components/SuggestionsPanel";

const API_BASE_URL =
  "https://protsearch-backend-312141936151.us-central1.run.app";

const SUGGESTED_PROMPTS = [
  {
    label: "Suggested",
    proteins: "BRCA1, BRCA2",
    question: "What is the role of BRCA1 and BRCA2 in DNA repair and breast cancer risk?",
  },
  {
    label: "Suggested",
    proteins: "TP53",
    question: "How do TP53 mutations affect tumor suppression and therapy response?",
  },
  {
    label: "Suggested",
    proteins: "EGFR, KRAS",
    question: "What are recent advances in targeted therapy for EGFR and KRAS in lung cancer?",
  },
];

const CONFIG_SECTIONS = [
  { id: "together", label: "Search together" },
  { id: "summary", label: "AI summary notes" },
  { id: "terms", label: "Paper search terms" },
] as const;

export default function HomePage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [proteinsInput, setProteinsInput] = useState("");
  const [searchProteinsTogether, setSearchProteinsTogether] = useState(false);
  const [searchTerms, setSearchTerms] = useState<
    Array<{ term: string; operator: "AND" | "OR" | null }>
  >([{ term: "", operator: null }]);
  const [question, setQuestion] = useState("");
  const [rememberKey, setRememberKey] = useState(true);

  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionsData, setSuggestionsData] = useState<any[]>([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState<
    Record<number, string>
  >({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  useEffect(() => {
    const savedApiKey = Cookies.get("protsearch_api_key");
    if (savedApiKey) setApiKey(savedApiKey);
  }, []);

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setApiKey(newValue);
    if (rememberKey) {
      if (newValue) {
        Cookies.set("protsearch_api_key", newValue, {
          expires: 30,
          secure: true,
          sameSite: "strict",
        });
      } else {
        Cookies.remove("protsearch_api_key");
      }
    }
  };

  const toggleRememberKey = () => {
    const newValue = !rememberKey;
    setRememberKey(newValue);
    if (!newValue) Cookies.remove("protsearch_api_key");
    else if (apiKey) {
      Cookies.set("protsearch_api_key", apiKey, {
        expires: 30,
        secure: true,
        sameSite: "strict",
      });
    }
  };

  const addSearchTerm = () => {
    setSearchTerms((prev) => {
      const next = [...prev];
      if (next.length > 0) {
        const last = next[next.length - 1];
        if (last) next[next.length - 1] = { term: last.term, operator: last.operator ?? "AND" };
      }
      next.push({ term: "", operator: null });
      return next;
    });
    setTimeout(() => {
      const idx = inputRefs.current.length - 1;
      inputRefs.current[idx]?.focus();
    }, 0);
  };

  const removeSearchTerm = (index: number) => {
    setSearchTerms((prev) => {
      if (prev.length <= 1) return prev;
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
    setTimeout(() => {
      inputRefs.current = inputRefs.current.filter((_, i) => i !== index);
    }, 0);
  };

  const updateSearchTerm = (index: number, value: string) => {
    setSearchTerms((ts) => {
      const copy = [...ts];
      const existing = ts[index];
      copy[index] = { term: value, operator: existing ? existing.operator : null };
      return copy;
    });
  };

  const toggleOperator = (index: number) => {
    setSearchTerms((ts) => {
      const copy = [...ts];
      const existing = ts[index];
      const current = existing?.operator ?? null;
      const next: "AND" | "OR" | null =
        current === null ? "AND" : current === "AND" ? "OR" : "AND";
      copy[index] = { term: existing ? existing.term : "", operator: next };
      return copy;
    });
  };

  const parseProteinTokens = (text: string): string[] =>
    text
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

  const joinProteinTokens = (tokens: string[]) => tokens.join(", ");

  const precheckSuggestions = async (): Promise<boolean> => {
    const tokens = parseProteinTokens(proteinsInput);
    if (tokens.length === 0) return true;

    try {
      const resp = await fetch(`${API_BASE_URL}/api/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ proteins: tokens }),
      });

      if (!resp.ok) return true;

      const data = await resp.json();
      const warning: string = data?.warning || "";
      const lowerWarn = warning.toLowerCase();
      const isServiceUnavailable =
        lowerWarn.includes("unavailable") || lowerWarn.includes("gene alias");

      if (isServiceUnavailable) {
        const mockSuggestions = tokens.map((tok: string) => ({
          input: tok,
          exact: false,
          suggestions: [],
          details: [],
        }));
        setSuggestionsData(mockSuggestions);
        setSelectedSuggestions({});
        setShowSuggestions(true);
        setError(
          `Gene alias service is unavailable: ${warning}. Verify protein names before proceeding.`,
        );
        return false;
      }

      const list: any[] = Array.isArray(data?.suggestions) ? data.suggestions : [];

      if (list.length === 0 && tokens.length > 0) {
        setSuggestionsData(
          tokens.map((tok: string) => ({
            input: tok,
            exact: false,
            suggestions: [],
            details: [],
          })),
        );
        setSelectedSuggestions({});
        setShowSuggestions(true);
        return false;
      }

      if (list.length === 0) return true;

      const hasNonExactMatches = list.some((item: any) => item?.exact !== true);
      if (hasNonExactMatches) {
        setSuggestionsData(list);
        const preselected: Record<number, string> = {};
        list.forEach((item: any, idx: number) => {
          if (item?.exact !== true) {
            if (Array.isArray(item?.suggestions) && item.suggestions.length > 0) {
              preselected[idx] = String(item.suggestions[0]);
            } else if (Array.isArray(item?.details) && item.details.length > 0) {
              preselected[idx] = String(item.details[0].gene);
            }
          }
        });
        setSelectedSuggestions(preselected);
        setShowSuggestions(true);
        return false;
      }

      return true;
    } catch {
      return true;
    }
  };

  const applySuggestionsAndSearch = async () => {
    const tokens = parseProteinTokens(proteinsInput);
    const replaced = tokens.map((tok, idx) => {
      const item = suggestionsData[idx];
      if (!item || item.exact) return tok;
      const chosen = selectedSuggestions[idx];
      if (chosen && String(chosen).trim().length > 0) return chosen;
      return tok;
    });
    setProteinsInput(joinProteinTokens(replaced));
    setShowSuggestions(false);
    setLoading(true);
    await doSearch();
  };

  const ignoreSuggestionsAndSearch = async () => {
    setShowSuggestions(false);
    setLoading(true);
    await doSearch();
  };

  const chooseSuggestion = (index: number, suggestion: string) => {
    setSelectedSuggestions((prev) => ({ ...prev, [index]: suggestion }));
  };

  const handleStart = async () => {
    setError(null);
    if (!proteinsInput.trim()) {
      setError("Please enter at least one protein");
      return;
    }
    if (showSuggestions) return;

    setLoading(true);
    const canProceed = await precheckSuggestions();
    if (canProceed) await doSearch();
    else {
      setLoading(false);
      setShowSuggestions(true);
    }
  };

  const doSearch = async () => {
    if (!proteinsInput.trim()) {
      setError("Please enter at least one protein");
      setLoading(false);
      return;
    }

    try {
      setError(null);
      localStorage.removeItem("protsearch_results");
      localStorage.removeItem("protsearch_session_id");
      sessionStorage.removeItem("protsearch_sse_done");
      sessionStorage.removeItem("protsearch_sse_done_session_id");

      const response = await fetch(`${API_BASE_URL}/api/search_start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          api_key: apiKey || undefined,
          proteins: proteinsInput,
          search_proteins_together: searchProteinsTogether,
          search_terms: searchTerms,
          question: question,
        }),
      });

      if (!response.ok) {
        let errorText = `Server returned ${response.status}`;
        try {
          const errorData = await response.json();
          errorText = errorData.error || errorText;
        } catch {}
        throw new Error(errorText);
      }

      const startData = await response.json();
      const serverSessionId: string | undefined =
        startData.session_id || startData.diag?.session_id;

      if (!serverSessionId) throw new Error("Server did not return a session_id");

      if (startData.new_session) {
        localStorage.removeItem("protsearch_results");
        localStorage.removeItem("protsearch_session_id");
        sessionStorage.removeItem("protsearch_sse_done");
        sessionStorage.removeItem("protsearch_sse_done_session_id");
      }

      const initialResults = {
        ...startData,
        summaryLoading: true,
        summaryError: null,
        activeTab: "papers",
      };

      localStorage.setItem("protsearch_results", JSON.stringify(initialResults));
      localStorage.setItem("protsearch_session_id", serverSessionId);
      router.push(`/results?session_id=${serverSessionId}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "An unknown error occurred";
      if (message === "Failed to fetch") {
        setError("Cannot connect to the server. Make sure the backend is running.");
      } else {
        setError(message);
      }
      setLoading(false);
    }
  };

  const applySuggested = (proteins: string, q: string) => {
    setProteinsInput(proteins);
    setQuestion(q);
    setError(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleStart();
    }
  };

  return (
    <PageBackground>
      <TopBar
        apiKey={apiKey}
        rememberKey={rememberKey}
        onApiKeyChange={handleApiKeyChange}
        onToggleRemember={toggleRememberKey}
      />

      <div className="mx-auto flex max-w-3xl flex-col justify-center px-6 py-10 pb-16 sm:min-h-[calc(100vh-3.5rem)] sm:py-14">
        <header className="mb-8 animate-fade-up text-center">
          <h1 className="sr-only">ProtSearch — AI-assisted protein literature search</h1>
          <p className="mx-auto max-w-lg text-sm leading-relaxed text-muted">{SITE_BLURB}</p>
        </header>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 animate-fade-up">
            {error}
          </div>
        )}

        {showSuggestions && (
          <SuggestionsPanel
            suggestionsData={suggestionsData}
            selectedSuggestions={selectedSuggestions}
            onChoose={chooseSuggestion}
            onApply={() => void applySuggestionsAndSearch()}
            onIgnore={() => void ignoreSuggestionsAndSearch()}
          />
        )}

        {/* Main research input card */}
        <div className="animate-fade-up-delay-1 overflow-hidden rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center border-b border-border bg-brand-muted/50 px-4 py-3">
            <span className="flex items-center gap-2 text-sm font-medium text-brand">
              Protein research
              <ChevronDownIcon className="h-4 w-4 opacity-50" />
            </span>
          </div>

          <div className="px-4 pt-4 pb-2">
            <textarea
              value={proteinsInput}
              onChange={(e) => setProteinsInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={4}
              disabled={loading || showSuggestions}
              placeholder="Enter proteins to research, e.g. BRCA1, TP53, EGFR"
              className="w-full resize-none border-0 bg-transparent text-base leading-relaxed text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0 disabled:opacity-60"
            />
          </div>

          <div className="flex items-center justify-end border-t border-border bg-gray-50/80 px-3 py-2.5">
            <button
              type="button"
              onClick={() => void handleStart()}
              disabled={loading || showSuggestions}
              className="btn-submit flex h-10 w-10 items-center justify-center rounded-full bg-brand text-white disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Start research"
            >
              {loading ? (
                <svg
                  className="h-5 w-5 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
              ) : (
                <ArrowRightIcon className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>

        {/* Search options — always visible */}
        <div className="animate-fade-up-delay-2 mt-4 overflow-hidden rounded-xl border border-border bg-white shadow-sm">
          <section className="p-5">
            <h2 className="mb-1 text-sm font-semibold text-gray-900">
              {CONFIG_SECTIONS[0].label}
            </h2>
            <p className="mb-4 text-sm text-gray-600">
              Choose how multiple proteins are matched when finding papers.
            </p>
            <label
              className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${
                !searchProteinsTogether
                  ? "border-brand bg-brand-muted/40"
                  : "border-gray-200"
              }`}
            >
              <input
                type="radio"
                name="proteinMode"
                checked={!searchProteinsTogether}
                onChange={() => setSearchProteinsTogether(false)}
                className="mt-0.5 text-brand focus:ring-brand"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Each protein separately
                </span>
                <span className="block text-xs text-gray-500">
                  Search papers for each protein on its own (OR).
                </span>
              </span>
            </label>
            <label
              className={`mt-3 flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${
                searchProteinsTogether
                  ? "border-brand bg-brand-muted/40"
                  : "border-gray-200"
              }`}
            >
              <input
                type="radio"
                name="proteinMode"
                checked={searchProteinsTogether}
                onChange={() => setSearchProteinsTogether(true)}
                className="mt-0.5 text-brand focus:ring-brand"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  All proteins together
                </span>
                <span className="block text-xs text-gray-500">
                  Only papers that mention every protein (AND).
                </span>
              </span>
            </label>
          </section>

          <section className="border-t border-border p-5">
            <h2 className="mb-1 text-sm font-semibold text-gray-900">
              {CONFIG_SECTIONS[1].label}
            </h2>
            <p className="mb-3 text-sm text-gray-600">
              Notes for the AI summary only. These do not change which papers are
              retrieved.
            </p>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value.slice(0, 200))}
              maxLength={200}
              rows={4}
              placeholder="e.g. Focus on therapeutic applications and clinical trials"
              className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <p className="mt-1 text-right text-xs text-gray-400">{question.length}/200</p>
          </section>

          <section className="border-t border-border p-5">
            <h2 className="mb-1 text-sm font-semibold text-gray-900">
              {CONFIG_SECTIONS[2].label}
            </h2>
            <p className="mb-3 text-sm text-gray-600">
              Extra keywords to narrow which papers are found. Combined with your
              proteins using AND/OR.
            </p>
            <div className="space-y-2">
              {searchTerms.map((item, index) => (
                <div key={index} className="flex items-center gap-2">
                  {index > 0 && (
                    <button
                      type="button"
                      onClick={() => toggleOperator(index)}
                      className="shrink-0 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-600"
                    >
                      {item.operator || "AND"}
                    </button>
                  )}
                  <input
                    type="text"
                    value={item.term}
                    onChange={(e) => updateSearchTerm(index, e.target.value)}
                    ref={(el) => {
                      inputRefs.current[index] = el;
                    }}
                    placeholder={index === 0 ? "e.g. cancer, inhibitor" : ""}
                    className="flex-1 rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  />
                  <button
                    type="button"
                    onClick={() => removeSearchTerm(index)}
                    disabled={searchTerms.length <= 1 && index === 0}
                    className="rounded-lg p-2 text-gray-400 hover:bg-gray-50 disabled:opacity-30"
                  >
                    <MinusIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addSearchTerm}
              className="mt-3 flex items-center gap-1 text-sm text-gray-600 hover:text-brand"
            >
              <PlusIcon className="h-4 w-4" />
              Add term
            </button>
          </section>
        </div>

        {/* Suggested prompts */}
        <div className="animate-fade-up-delay-3 mt-10">
          <p className="mb-3 text-center text-xs font-medium text-muted">
            Suggested
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            {SUGGESTED_PROMPTS.map((card, i) => (
              <button
                key={i}
                type="button"
                onClick={() => applySuggested(card.proteins, card.question)}
                className="card-hover group rounded-xl border border-border bg-white p-4 text-left"
              >
                <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted">
                  <LightBulbIcon className="h-3.5 w-3.5 text-brand/70" />
                  {card.label}
                </div>
                <p className="line-clamp-3 text-sm leading-relaxed text-gray-600 group-hover:text-gray-800">
                  {card.question}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </PageBackground>
  );
}
