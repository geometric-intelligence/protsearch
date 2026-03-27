"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon, MinusIcon, BeakerIcon, DocumentTextIcon, ArrowRightIcon } from "@heroicons/react/24/outline";
import Cookies from 'js-cookie';

export default function HomePage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [proteinsInput, setProteinsInput] = useState("");
  const [searchProteinsTogether, setSearchProteinsTogether] = useState(false);
  const [searchTerms, setSearchTerms] = useState<Array<{term: string, operator: "AND" | "OR" | null}>>([
    { term: "", operator: null }
  ]);
  const [question, setQuestion] = useState("");
  const [rememberKey, setRememberKey] = useState(true);

  // Suggestions state
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionsData, setSuggestionsData] = useState<any[]>([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Record<number, string>>({});

  // API interaction state variables
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // refs to inputs for focusing newly added fields
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  // API base URL - use the same as search_start endpoint
  const API_BASE_URL = 'https://protsearch-backend-312141936151.us-central1.run.app';

  // Load API key from cookie on component mount
  useEffect(() => {
    const savedApiKey = Cookies.get('protsearch_api_key');
    if (savedApiKey) {
      setApiKey(savedApiKey);
    }
  }, []);

  // Handle API key changes
  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setApiKey(newValue);
    // Save to cookie if remember option is enabled
    if (rememberKey) {
      if (newValue) {
        Cookies.set('protsearch_api_key', newValue, { expires: 30, secure: true, sameSite: 'strict' });
      } else {
        Cookies.remove('protsearch_api_key');
      }
    }
  };

  // Toggle remember option
  const toggleRememberKey = () => {
    const newValue = !rememberKey;
    setRememberKey(newValue);
    if (!newValue) {
      Cookies.remove('protsearch_api_key');
    } else if (apiKey) {
      Cookies.set('protsearch_api_key', apiKey, { expires: 30, secure: true, sameSite: 'strict' });
    }
  };

  // Add a new search term field: ensure previous operator becomes AND, then focus new input
  const addSearchTerm = () => {
    setSearchTerms(prev => {
      const next = [...prev];
      if (next.length > 0) {
        const last = next[next.length - 1];
        if (last) {
          next[next.length - 1] = { term: last.term, operator: last.operator ?? "AND" };
        }
      }
      next.push({ term: "", operator: null });
      return next;
    });
    // Focus the newly added input on next tick
    setTimeout(() => {
      const idx = inputRefs.current.length - 1;
      if (idx >= 0) {
        const el = inputRefs.current[idx];
        el?.focus();
      }
    }, 0);
  };

  // Remove a search term at a specific index
  const removeSearchTerm = (index: number) => {
    setSearchTerms(prev => {
      if (prev.length <= 1) return prev;
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
    // Clean up ref to avoid stale indices
    setTimeout(() => {
      inputRefs.current = inputRefs.current.filter((_, i) => i !== index);
    }, 0);
  };

  // Update a search term at a specific index
  const updateSearchTerm = (index: number, value: string) => {
    setSearchTerms(ts => {
      const copy = [...ts];
      const existing = ts[index];
      copy[index] = { term: value, operator: existing ? existing.operator : null };
      return copy;
    });
  };

  // Toggle the operator for a search term
  const toggleOperator = (index: number) => {
    setSearchTerms(ts => {
      const copy = [...ts];
      const existing = ts[index];
      const current = existing?.operator ?? null;
      const next: "AND" | "OR" | null =
        current === null ? "AND" :
        current === "AND"  ? "OR"  :
                            "AND";
      copy[index] = { term: existing ? existing.term : "", operator: next };
      return copy;
    });
  };

  // Helpers to parse/join protein tokens
  const parseProteinTokens = (text: string): string[] =>
    text
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

  const joinProteinTokens = (tokens: string[]) => tokens.join(", ");

  // Fetch suggestions from backend; return true if safe to proceed immediately
  const precheckSuggestions = async (): Promise<boolean> => {
    const tokens = parseProteinTokens(proteinsInput);
    if (tokens.length === 0) {
      console.log("No protein tokens to check");
      return true;
    }

    console.log("Checking suggestions for tokens:", tokens);

    try {
      const resp = await fetch(`${API_BASE_URL}/api/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ proteins: tokens }),
      });

      console.log("Suggest response status:", resp.status, resp.statusText);

      if (!resp.ok) {
        const errorText = await resp.text();
        console.warn("Suggest endpoint returned non-OK status:", resp.status, errorText);
        return true; // don't block if suggest fails
      }

      const data = await resp.json();
      console.log("Suggest response data:", JSON.stringify(data, null, 2));

      // Check for warnings - if gene alias service is unavailable, we should block
      const warning: string = data?.warning || "";
      const lowerWarn = warning.toLowerCase();
      const isServiceUnavailable = lowerWarn.includes("unavailable") || lowerWarn.includes("gene alias");
      
      if (isServiceUnavailable) {
        console.error("⚠️ Gene alias service unavailable:", warning);
        const mockSuggestions = tokens.map((tok: string) => ({
          input: tok,
          exact: false,
          suggestions: [],
          details: []
        }));
        setSuggestionsData(mockSuggestions);
        setSelectedSuggestions({});
        setShowSuggestions(true);
        setError(`Gene alias service is currently unavailable: ${warning}. Please verify your protein names before proceeding.`);
        console.log("🛑 BLOCKING: Gene alias service unavailable, showing UI");
        return false; // Block to let user confirm
      }

      const list: any[] = Array.isArray(data?.suggestions) ? data.suggestions : [];
      console.log("Suggestions list length:", list.length);
      console.log("Suggestions list:", list);

      if (list.length === 0 && tokens.length > 0) {
        console.warn("No suggestions list returned from API for tokens, showing 'not found' UI");
        const mockSuggestions = tokens.map((tok: string) => ({
          input: tok,
          exact: false,
          suggestions: [],
          details: []
        }));
        setSuggestionsData(mockSuggestions);
        setSelectedSuggestions({});
        setShowSuggestions(true);
        console.log("🛑 BLOCKING: No suggestions returned, showing 'not found' UI");
        return false;
      }
      
      if (list.length === 0 && tokens.length === 0) {
        console.log("No tokens to check, proceeding");
        return true;
      }

      const hasNonExactMatches = list.some((item: any) => item?.exact !== true);
      console.log("Has non-exact matches:", hasNonExactMatches);

      if (hasNonExactMatches) {
        console.log("🚫 NON-EXACT MATCHES DETECTED - BLOCKING SEARCH");
        setSuggestionsData(list);
        
        // Preselect first suggestion where available
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

      console.log("✅ ALL PROTEINS ARE EXACT MATCHES - PROCEEDING");
      return true;
    } catch (err) {
      console.error("Error fetching suggestions:", err);
      return true; // Don't block on error
    }
  };

  // Apply selected suggestions to the input, close the UI, then proceed to search
  const applySuggestionsAndSearch = async () => {
    const tokens = parseProteinTokens(proteinsInput);
    const replaced = tokens.map((tok, idx) => {
      const item = suggestionsData[idx];
      if (!item || item.exact) return tok;
      const chosen = selectedSuggestions[idx];
      if (chosen && String(chosen).trim().length > 0) return chosen;
      return tok;
    });

    const newInput = joinProteinTokens(replaced);
    setProteinsInput(newInput);
    setShowSuggestions(false);
    setLoading(true);
    await doSearch();
  };

  // Ignore suggestions and proceed
  const ignoreSuggestionsAndSearch = async () => {
    setShowSuggestions(false);
    setLoading(true);
    await doSearch();
  };

  // Handle selecting a suggestion chip
  const chooseSuggestion = (index: number, suggestion: string) => {
    setSelectedSuggestions((prev) => ({ ...prev, [index]: suggestion }));
  };

  // Wrapper for the Start button: check suggestions first
  const handleStart = async () => {
    setError(null);
    if (!proteinsInput.trim()) {
      setError("Please enter at least one protein");
      return;
    }

    // Don't proceed if suggestions UI is already showing
    if (showSuggestions) {
      console.warn("Suggestions UI already showing, ignoring start click");
      return;
    }

    console.log("=== START BUTTON CLICKED ===");
    setLoading(true);
    const canProceed = await precheckSuggestions();
    console.log("precheckSuggestions returned:", canProceed);

    if (canProceed) {
      console.log("Proceeding with search immediately");
      await doSearch();
    } else {
      // Ensure suggestions UI is visible without relying on stale state
      console.log("BLOCKING - Showing suggestions UI and disabling loading");
      setLoading(false);
      setShowSuggestions(true);
    }
  };

  // Start streaming search; navigate to results immediately
  const doSearch = async () => {
    if (!proteinsInput.trim()) {
      setError("Please enter at least one protein");
      setLoading(false);
      return;
    }

    try {
      setError(null);

      // Clear all old session data before starting new search
      localStorage.removeItem('protsearch_results');
      localStorage.removeItem('protsearch_session_id');
      sessionStorage.removeItem('protsearch_sse_done');
      sessionStorage.removeItem('protsearch_sse_done_session_id');

      const response = await fetch(`${API_BASE_URL}/api/search_start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
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
      const serverSessionId: string | undefined = startData.session_id || startData.diag?.session_id;

      if (!serverSessionId) {
        throw new Error("Server did not return a session_id");
      }

      if (startData.new_session) {
        localStorage.removeItem('protsearch_results');
        localStorage.removeItem('protsearch_session_id');
        sessionStorage.removeItem('protsearch_sse_done');
        sessionStorage.removeItem('protsearch_sse_done_session_id');
      }

      const initialResults = {
        ...startData,
        summaryLoading: true,
        summaryError: null,
        activeTab: 'papers',
      };

      localStorage.setItem('protsearch_results', JSON.stringify(initialResults));
      localStorage.setItem('protsearch_session_id', serverSessionId);
      router.push(`/results?session_id=${serverSessionId}`);
    } catch (error: any) {
      if (error?.message === "Failed to fetch") {
        setError("Cannot connect to the server. Please make sure the Flask server is running.");
      } else {
        setError(error?.message || "An unknown error occurred");
      }
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-blue-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <BeakerIcon className="h-8 w-8" />
              <h1 className="text-2xl font-bold tracking-tight" style={{
                textShadow: `-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000`
              }}>ProtSearch</h1>
            </div>
            <span className="text-sm opacity-75">Protein Literature Research Assistant</span>
          </div>
        </div>
      </header>

      {/* Global styles */}
      <style jsx global>{`
        .btn-glow {
          position: relative;
          z-index: 1;
          overflow: hidden;
          transition: all 0.3s;
        }
        .btn-glow::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, rgba(99, 179, 237, 0), rgba(104, 211, 245, 0.5));
          border-radius: inherit;
          opacity: 0;
          z-index: -1;
          transform: scale(1.2);
          transition: transform 0.4s ease-out, opacity 0.4s;
        }
        .btn-glow:hover {
          box-shadow: 0 0 15px rgba(99, 179, 237, 0.5);
        }
        .btn-glow:hover::before {
          transform: scale(1);
          opacity: 1;
        }
        .btn-glow-primary::before {
          background: linear-gradient(135deg, rgba(79, 70, 229, 0), rgba(104, 211, 245, 0.7));
        }
        .btn-glow-primary:hover {
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.6);
        }
        .toggle-switch {
          position: relative;
          width: 48px;
          height: 24px;
        }
        .toggle-switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }
        .toggle-slider {
          position: absolute;
          cursor: pointer;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: #ccc;
          transition: .4s;
          border-radius: 24px;
        }
        .toggle-slider:before {
          position: absolute;
          content: "";
          height: 18px;
          width: 18px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: .4s;
          border-radius: 50%;
        }
        input:checked + .toggle-slider {
          background-color: #93c5fd;
        }
        input:checked + .toggle-slider:before {
          transform: translateX(24px);
        }
      `}</style>

      <div className="container mx-auto px-4 py-8">
        {error && (
          <div className="mb-4 bg-red-50 border-l-4 border-red-500 p-4 rounded">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-3 space-y-6">
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <h2 className="text-lg font-medium text-gray-800 mb-4 flex items-center">
                <DocumentTextIcon className="h-5 w-5 mr-2 text-indigo-500" />
                Configuration
              </h2>
              <div>
                <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 mb-1">
                  Enter API Key (optional):
                </label>
                <input
                  type="password"
                  id="apiKey"
                  value={apiKey}
                  onChange={handleApiKeyChange}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <div className="mt-2 flex items-center">
                  <input
                    type="checkbox"
                    id="rememberKey"
                    checked={rememberKey}
                    onChange={toggleRememberKey}
                    className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                  />
                  <label htmlFor="rememberKey" className="ml-2 block text-sm text-gray-700">
                    Remember API key (stored securely in your browser)
                  </label>
                </div>
              </div>
            </div>

            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-indigo-100">
              <h3 className="font-medium text-indigo-800 mb-2">Tips</h3>
              <ul className="text-sm text-indigo-700 space-y-2">
                <li>• Add extra terms to narrow your search</li>
                <li>• Ask specific questions in the summary section</li>
                <li>• Using an API key will not affect the papers found, only the number of papers found and the summary quality.</li>
                <li>• Using an API key will use the full papers if publically available, not using an API key will only use abstracts.</li>
              </ul>
            </div>
          </div>

          <div className="lg:col-span-9">
            <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
              {/* Suggestions Modal/Overlay */}
              {showSuggestions && (
                <div className="mb-6 border-2 border-amber-400 bg-gradient-to-br from-amber-50 to-yellow-50 rounded-xl p-6 shadow-lg">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <h3 className="text-xl font-bold text-amber-900 mb-2 flex items-center">
                        <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        Protein Not Found - Review Before Searching
                      </h3>
                      <p className="text-sm text-amber-800 mb-1">
                        One or more proteins were not found as exact matches in our database. Please review the suggestions below, select corrections if available, or confirm to continue with your original input. The search will not proceed until you confirm.
                      </p>
                    </div>
                  </div>

                  <div className="space-y-4 mb-6">
                    {suggestionsData.map((item: any, idx: number) => {
                      if (item?.exact) {
                        return (
                          <div key={idx} className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="text-sm text-gray-700">
                              <span className="font-medium">Input:</span> <span className="font-mono text-green-800">{item.input}</span>
                              <span className="ml-2 text-green-700 font-medium">✓ Exact match found</span>
                            </div>
                          </div>
                        );
                      }

                      // If not exact but no suggestions found, show warning
                      if ((!Array.isArray(item?.suggestions) || item.suggestions.length === 0) &&
                          (!Array.isArray(item?.details) || item.details.length === 0)) {
                        return (
                          <div key={idx} className="bg-orange-50 border-2 border-orange-300 rounded-lg p-4">
                            <div className="text-sm text-gray-700 mb-2">
                              <span className="font-medium">Input:</span> <span className="font-mono text-orange-900 bg-orange-100 px-2 py-1 rounded">{item?.input}</span>
                              <span className="ml-2 text-orange-800 font-medium">⚠ No exact match found</span>
                            </div>
                            <p className="text-xs text-orange-700">
                              This protein was not found in our database. You can continue with your original input, but results may be limited.
                            </p>
                          </div>
                        );
                      }

                      const selectedGene = selectedSuggestions[idx];
                      return (
                        <div key={idx} className="bg-white border-2 border-amber-200 rounded-lg p-4 shadow-sm">
                          <div className="text-sm text-gray-700 mb-3">
                            <span className="font-medium">Input:</span> <span className="font-mono text-gray-800 bg-gray-100 px-2 py-1 rounded">{item?.input}</span>
                            <span className="ml-2 text-amber-700 font-medium">→ Select a correction:</span>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {item?.details?.map((d: any) => {
                              const chosen = selectedGene === d.gene;
                              return (
                                <button
                                  key={d.gene}
                                  type="button"
                                  onClick={() => chooseSuggestion(idx, d.gene)}
                                  className={`px-4 py-2 rounded-lg text-sm font-medium border-2 transition-all ${
                                    chosen
                                      ? "bg-indigo-600 text-white border-indigo-600 shadow-md scale-105"
                                      : "bg-white text-indigo-700 border-indigo-300 hover:bg-indigo-50 hover:border-indigo-400"
                                  }`}
                                  title={d.aliases ? `Aliases: ${d.aliases}` : d.gene_name ? `Name: ${d.gene_name}` : ""}
                                >
                                  {d.gene}
                                  {typeof d.score === "number" && (
                                    <span className="ml-2 opacity-70 text-xs">({d.score}% match)</span>
                                  )}
                                </button>
                              );
                            })}
                          </div>
                          {item?.details?.[0]?.gene_name && (
                            <div className="mt-2 text-xs text-gray-600">
                              {selectedGene && item?.details?.find((d: any) => d.gene === selectedGene)?.gene_name && (
                                <span>Selected: <strong>{item.details.find((d: any) => d.gene === selectedGene)?.gene_name}</strong></span>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex gap-3 pt-4 border-t border-amber-300">
                    <button
                      type="button"
                      onClick={applySuggestionsAndSearch}
                      className="btn-glow btn-glow-primary inline-flex items-center px-6 py-3 rounded-lg text-white bg-gradient-to-r from-indigo-600 to-blue-600 font-medium shadow-md hover:shadow-lg"
                    >
                      <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Apply suggestions and search
                    </button>
                    <button
                      type="button"
                      onClick={ignoreSuggestionsAndSearch}
                      className="btn-glow inline-flex items-center px-6 py-3 rounded-lg border-2 border-gray-300 bg-white text-gray-700 font-medium hover:bg-gray-50"
                    >
                      Continue with original input
                    </button>
                  </div>
                </div>
              )}

              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 mb-4 pb-2 border-b">
                  Protein Search Parameters
                </h2>
                <div className="mb-6">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Proteins of Interest
                  </label>
                  <input
                    type="text"
                    value={proteinsInput}
                    onChange={(e) => setProteinsInput(e.target.value)}
                    className="block w-full px-4 py-3 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="e.g. ACE, APP, BACE1 (comma separated)"
                  />
                  <div className="flex items-center mt-3 bg-gray-50 p-3 rounded-lg">
                    <label className="toggle-switch mr-3">
                      <input
                        type="checkbox"
                        checked={searchProteinsTogether}
                        onChange={() => setSearchProteinsTogether(!searchProteinsTogether)}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                    <label className="text-sm text-gray-700 font-medium">
                      {searchProteinsTogether
                        ? "Search for papers with ALL proteins (AND)"
                        : "Search for each protein individually (OR)"}
                    </label>
                  </div>
                </div>

                <div className="mb-2">
                  <label className="block text sm font-medium text-gray-700 mb-2">
                    Additional Paper Search Terms
                  </label>
                  <div className="space-y-3">
                    {searchTerms.map((item, index) => (
                      <div key={index} className="flex items-center gap-2">
                        {index > 0 && (
                          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100">
                            <span className="text-xs font-medium text-gray-500">{item.operator || "AND"}</span>
                          </div>
                        )}
                        <div className="flex-grow flex items-center">
                          <input
                            type="text"
                            value={item.term}
                            onChange={(e) => updateSearchTerm(index, e.target.value)}
                            ref={(el) => { inputRefs.current[index] = el ?? null; }}
                            className="block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                            placeholder={index === 0 ? "e.g. metabolism" : ""}
                          />
                          <div className="flex ml-2">
                            {index < searchTerms.length - 1 && (
                              <button
                                type="button"
                                onClick={() => toggleOperator(index)}
                                className="btn-glow px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white mr-2"
                              >
                                {item.operator || "AND"}
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => removeSearchTerm(index)}
                              className="btn-glow p-2 border border-gray-300 rounded-lg text-gray-500"
                              disabled={searchTerms.length <= 1 && index === 0}
                            >
                              <MinusIcon className="h-5 w-5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={addSearchTerm}
                    className="btn-glow mt-3 inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-lg text-gray-700 bg-white"
                  >
                    <PlusIcon className="h-5 w-5 mr-2 text-gray-500" /> Add Term
                  </button>
                </div>
              </section>

              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 mb-4 pb-2 border-b">
                  AI Summary Configuration
                </h2>
                <p className="text-sm text-gray-600 mb-3">
                  Add any specific information or questions for the summary. (Note: This will not affect the papers pulled, use additional search terms to specify the papers you want.)
                </p>
                <div className="relative">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value.slice(0, 200))}
                    maxLength={200}
                    rows={4}
                    className="block w-full px-4 py-3 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="e.g. Focus on protein interactions with APP, or therapeutic applications"
                  />
                  <div className="absolute bottom-3 right-3 text-xs font-medium px-2 py-1 bg-gray-100 rounded text-gray-500">
                    {question.length}/200
                  </div>
                </div>
              </section>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleStart}
                  disabled={loading || showSuggestions}
                  className={`btn-glow btn-glow-primary inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg shadow-lg text-white bg-gradient-to-r from-indigo-600 to-blue-600 ${
                    loading || showSuggestions ? 'opacity-75 cursor-not-allowed' : ''
                  }`}
                >
                  {loading ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Processing...
                    </>
                  ) : (
                    <>
                      Start Research <ArrowRightIcon className="ml-2 h-5 w-5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <footer className="mt-12 py-6 bg-gray-50 border-t border-gray-200">
        <div className="container mx-auto px-4 text-center text-sm text-gray-600">
          ProtSearch helps researchers discover and summarize scientific literature about proteins.
          </div>
      </footer>
    </div>
  );
}