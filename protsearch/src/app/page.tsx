"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon, MinusIcon, BeakerIcon, DocumentTextIcon, ArrowRightIcon } from "@heroicons/react/24/outline";

export default function HomePage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [proteinsInput, setProteinsInput] = useState("");
  const [searchProteinsTogether, setSearchProteinsTogether] = useState(false);
  const [searchTerms, setSearchTerms] = useState<Array<{term: string, operator: "AND" | "OR" | null}>>([
    { term: "", operator: null }
  ]);
  const [question, setQuestion] = useState("");
  
  // API interaction state variables
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Add a new search term field
  const addSearchTerm = () => {
    setSearchTerms([...searchTerms, { term: "", operator: null }]);
  };

  // Remove a search term at a specific index
  const removeSearchTerm = (index: number) => {
    // Don't remove if it's the last one
    if (searchTerms.length <= 1) return;
    
    const newTerms = [...searchTerms];
    newTerms.splice(index, 1);
    setSearchTerms(newTerms);
  };

  // Update a search term at a specific index
  const updateSearchTerm = (index: number, value: string) => {
    setSearchTerms(ts => {
      const copy = [...ts];
      // assert ts[index] is defined
      const existing = ts[index]!;  
      copy[index] = {
        term: value,
        operator: existing.operator
      };
      return copy;
    });
  };

  // Toggle the operator for a search term
  const toggleOperator = (index: number) => {
    setSearchTerms(ts => {
      const copy = [...ts];
      const existing = ts[index]!;       // assert non-null
      const current = existing.operator;
      const next: "AND" | "OR" | null =
        current === null ? "AND" :
        current === "AND"  ? "OR"  :
                            "AND";

      copy[index] = {
        term: existing.term,
        operator: next
      };
      return copy;
    });
  };

  // Connect to the Flask backend
  const startResearch = async () => {
    // Validate inputs
    if (!apiKey.trim()) {
      setError("API key is required");
      return;
    }
    
    if (!proteinsInput.trim()) {
      setError("Please enter at least one protein");
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      
      console.log("Sending request to server...");
      
      // Try using direct IP address
      const response = await fetch('http://127.0.0.1:8080/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          api_key: apiKey,
          proteins: proteinsInput,
          search_proteins_together: searchProteinsTogether,
          search_terms: searchTerms,
          question: question
        }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Server returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("Received results:", data);
      
      // Store results in localStorage for the results page to access
      localStorage.setItem('protsearch_results', JSON.stringify(data));
      
      // Navigate to results page
      router.push('/results');
      
    } catch (error: any) {
      console.error("Error performing search:", error);
      
      // More detailed error message
      if (error.message === "Failed to fetch") {
        setError("Cannot connect to the server. Please make sure the Flask server is running on port 5000.");
      } else {
        setError(error.message || "An unknown error occurred");
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

      {/* Add these global styles for the glow effect */}
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
        
        /* Main button has a stronger effect */
        .btn-glow-primary::before {
          background: linear-gradient(135deg, rgba(79, 70, 229, 0), rgba(104, 211, 245, 0.7));
        }
        
        .btn-glow-primary:hover {
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.6);
        }
        
        /* Toggle switch styling */
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
        {/* Display errors if any */}
        {error && (
          <div className="mb-4 bg-red-50 border-l-4 border-red-500 p-4 rounded">
            <p className="text-red-700">{error}</p>
          </div>
        )}
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* API Key Section - Left sidebar on desktop */}
          <div className="lg:col-span-3 space-y-6">
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <h2 className="text-lg font-medium text-gray-800 mb-4 flex items-center">
                <DocumentTextIcon className="h-5 w-5 mr-2 text-indigo-500" />
                Configuration
              </h2>
              <div>
                <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 mb-1">
                  Enter ChatGPT API Key:
                </label>
                <input
                  type="password"
                  id="apiKey"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-indigo-100">
              <h3 className="font-medium text-indigo-800 mb-2">Tips</h3>
              <ul className="text-sm text-indigo-700 space-y-2">
                <li>• Use specific protein names for better results</li>
                <li>• Add extra terms to narrow your search</li>
                <li>• Ask specific questions in the summary section</li>
              </ul>
            </div>
          </div>
          
          {/* Main content - Right side on desktop */}
          <div className="lg:col-span-9">
            <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
              {/* Search Section */}
              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 mb-4 pb-2 border-b">
                  Protein Search Parameters
                </h2>
                
                {/* Protein Input */}
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
                  
                  {/* Toggle for search mode - Fixed version */}
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
                
                {/* PubMed Search Terms */}
                <div className="mb-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Additional PubMed Search Terms
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
              
              {/* Summarizing Section */}
              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-800 mb-4 pb-2 border-b">
                  AI Summary Configuration
                </h2>
                <p className="text-sm text-gray-600 mb-3">
                  In addition to summarizing the papers found, is there any specific information or
                  questions you want to ask about these proteins?
                </p>
                <div className="relative">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value.slice(0, 200))}
                    maxLength={200}
                    rows={4}
                    className="block w-full px-4 py-3 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="e.g. Focus on protein interactions with APP, or tell me about potential therapeutic applications"
                  />
                  <div className="absolute bottom-3 right-3 text-xs font-medium px-2 py-1 bg-gray-100 rounded text-gray-500">
                    {question.length}/200
                  </div>
                </div>
              </section>
              
              {/* Action Button */}
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={startResearch}
                  disabled={loading}
                  className={`btn-glow btn-glow-primary inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg shadow-lg text-white bg-gradient-to-r from-indigo-600 to-blue-600 ${
                    loading ? 'opacity-75 cursor-not-allowed' : ''
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
      
      {/* Footer */}
      <footer className="mt-12 py-6 bg-gray-50 border-t border-gray-200">
        <div className="container mx-auto px-4 text-center text-sm text-gray-600">
          ProtSearch helps researchers discover and summarize scientific literature about proteins.
        </div>
      </footer>
    </div>
  );
}