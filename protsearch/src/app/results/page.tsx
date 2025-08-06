"use client";

import { useSearchParams, useRouter } from 'next/navigation';
import { useState, useEffect } from 'react';
import { BeakerIcon, ArrowLeftIcon, DocumentTextIcon, ClipboardIcon, ArrowTopRightOnSquareIcon, ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/24/outline";
import Link from 'next/link';

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

interface ResultsData {
  success: boolean;
  papers: Paper[];
  summary: string;
  saved_file: string | null;
}

export default function ResultsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [results, setResults] = useState<ResultsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'summary' | 'papers'>('summary');
  const [expandedAbstracts, setExpandedAbstracts] = useState<Record<number, boolean>>({});
  
  useEffect(() => {
    const resultsJson = localStorage.getItem('protsearch_results');
    if (resultsJson) {
      try {
        const parsedResults = JSON.parse(resultsJson);
        setResults(parsedResults);
      } catch (e) {
        setError('Failed to load results data');
      }
    } else {
      setError('No results found');
    }
    setLoading(false);
  }, []);
  
  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
      .then(() => {
        setCopiedText(label);
        setTimeout(() => setCopiedText(null), 2000);
      })
      .catch(() => {
        setError('Failed to copy to clipboard');
      });
  };

  const toggleAbstract = (index: number) => {
    setExpandedAbstracts(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };
  
  // Convert PubMed IDs and DOIs in text to hyperlinks
  const processTextWithLinks = (text: string) => {
    if (!text) return [];

    // Split by paragraphs first to preserve formatting
    const paragraphs = text.split('\n\n');

    return paragraphs.map((paragraph, paragraphIndex) => {
      // Process each paragraph for DOIs and PMIDs
      let processedParagraph = paragraph;
      
      // Replace DOIs with hyperlinks
      processedParagraph = processedParagraph.replace(
        /(https?:\/\/doi\.org\/[0-9a-zA-Z.\/\-_]+)/g, 
        '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">$1</a>'
      );
      
      // Replace PubMed URLs with hyperlinks
      processedParagraph = processedParagraph.replace(
        /(https?:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/[0-9]+\/)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">$1</a>'
      );
      
      // Handle PMID mentions
      processedParagraph = processedParagraph.replace(
        /PMID:\s*(\d+)/g,
        'PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/$1/" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">$1</a>'
      );

      // Add HTML line breaks instead of using React elements
      const htmlWithLineBreaks = processedParagraph
        .split('\n')
        .join('<br />');

      // Return the paragraph with links and HTML line breaks
      return (
        <p 
          key={paragraphIndex} 
          className="mb-4" 
          dangerouslySetInnerHTML={{ __html: htmlWithLineBreaks }} 
        />
      );
    });
  };
  
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-blue-50 flex items-center justify-center">
        <div className="animate-spin h-10 w-10 border-4 border-indigo-600 border-t-transparent rounded-full"></div>
      </div>
    );
  }
  
  if (error || !results) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-blue-50">
        <header className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <BeakerIcon className="h-8 w-8" />
                <h1 className="text-2xl font-bold tracking-tight" style={{
                  textShadow: `-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000`
                }}>ProtSearch</h1>
              </div>
            </div>
          </div>
        </header>
        
        <div className="container mx-auto px-4 py-12 text-center">
          <div className="bg-white rounded-xl shadow-sm p-8 border border-gray-100 max-w-2xl mx-auto">
            <h2 className="text-xl font-semibold text-gray-800 mb-4">Error</h2>
            <p className="text-gray-600">{error || 'Something went wrong'}</p>
            <Link href="/" className="btn-glow mt-6 inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-lg text-gray-700 bg-white">
              <ArrowLeftIcon className="h-5 w-5 mr-2" /> Back to Search
            </Link>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-blue-50">
      <header className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <BeakerIcon className="h-8 w-8" />
              <h1 className="text-2xl font-bold tracking-tight" style={{
                textShadow: `-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000`
              }}>ProtSearch</h1>
            </div>
            <span className="text-sm opacity-75">Research Results</span>
          </div>
        </div>
      </header>
      
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <Link href="/" className="btn-glow inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-lg text-gray-700 bg-white">
            <ArrowLeftIcon className="h-5 w-5 mr-2" /> Back to Search
          </Link>
          
          <div className="inline-flex rounded-lg shadow-sm">
            <button
              onClick={() => setActiveTab('summary')}
              className={`px-4 py-2 text-sm font-medium ${
                activeTab === 'summary'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-700'
              } border border-gray-300 rounded-l-lg hover:bg-gray-50`}
            >
              AI Summary
            </button>
            <button
              onClick={() => setActiveTab('papers')}
              className={`px-4 py-2 text-sm font-medium ${
                activeTab === 'papers'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-700'
              } border border-gray-300 rounded-r-lg hover:bg-gray-50`}
            >
              Papers ({results.papers.length})
            </button>
          </div>
        </div>
        
        {activeTab === 'summary' ? (
          <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100 mb-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-gray-800">AI Research Summary</h2>
              <button
                onClick={() => copyToClipboard(results.summary, 'summary')}
                className="btn-glow inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-sm font-medium rounded-lg text-gray-700 bg-white"
              >
                <ClipboardIcon className="h-4 w-4 mr-1" />
                {copiedText === 'summary' ? 'Copied!' : 'Copy'}
              </button>
            </div>
            
            <div className="prose prose-indigo max-w-none">
              {processTextWithLinks(results.summary)}
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
            <h2 className="text-xl font-semibold text-gray-800 mb-4">Found Papers</h2>
            <div className="space-y-6">
              {results.papers.map((paper, index) => (
                <div key={index} className="border-b pb-4 last:border-0">
                  <h3 className="font-medium text-lg text-gray-900 mb-1">{paper.title}</h3>
                  <p className="text-sm text-gray-600 mb-2">{paper.authors}</p>
                  <div className="flex items-center text-xs text-gray-500 mb-3 space-x-3">
                    <span>{paper.journal}</span>
                    <span>•</span>
                    <span>{paper.year}</span>
                    {paper.doi && (
                      <>
                        <span>•</span>
                        <span>
                          DOI: <a 
                            href={`https://doi.org/${paper.doi}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                          >
                            {paper.doi}
                          </a>
                        </span>
                      </>
                    )}
                  </div>
                  
                  {/* Abstract with expand/collapse toggle */}
                  <div className="mb-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs font-medium text-gray-500">Abstract</span>
                      <button 
                        onClick={() => toggleAbstract(index)} 
                        className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center"
                      >
                        {expandedAbstracts[index] ? (
                          <>
                            <ChevronUpIcon className="h-3 w-3 mr-1" /> Show Less
                          </>
                        ) : (
                          <>
                            <ChevronDownIcon className="h-3 w-3 mr-1" /> Show More
                          </>
                        )}
                      </button>
                    </div>
                    <p className={`text-sm text-gray-700 ${expandedAbstracts[index] ? '' : 'line-clamp-3'}`}>
                      {paper.abstract}
                    </p>
                  </div>
                  
                  <div className="flex space-x-2">
                    <a 
                      href={paper.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-glow inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-xs font-medium rounded-lg text-gray-700 bg-white"
                    >
                      <ArrowTopRightOnSquareIcon className="h-3 w-3 mr-1" />
                      PubMed
                    </a>
                    <button
                      onClick={() => copyToClipboard(paper.abstract, `abstract-${index}`)}
                      className="btn-glow inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-xs font-medium rounded-lg text-gray-700 bg-white"
                    >
                      <ClipboardIcon className="h-3 w-3 mr-1" />
                      {copiedText === `abstract-${index}` ? 'Copied!' : 'Copy Abstract'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      
      <footer className="mt-12 py-6 bg-gray-50 border-t border-gray-200">
        <div className="container mx-auto px-4 text-center text-sm text-gray-600">
          ProtSearch helps researchers discover and summarize scientific literature about proteins.
        </div>
      </footer>
      
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
        
        /* Add line-clamp utility if not already included in your Tailwind config */
        .line-clamp-3 {
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
      `}</style>
    </div>
  );
}