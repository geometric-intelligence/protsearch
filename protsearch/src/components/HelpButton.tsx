"use client";

import { useState, useEffect, useRef } from "react";
import { DocumentTextIcon, XMarkIcon } from "@heroicons/react/24/outline";

type HelpButtonProps = {
  embedded?: boolean;
  apiKey?: string;
  rememberKey?: boolean;
  onApiKeyChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onToggleRemember?: () => void;
};

const NOTES = [
  "Enter protein names (comma-separated) and press the arrow to search Europe PMC.",
  "Search together — choose papers per protein or papers mentioning all proteins.",
  "AI summary notes — ask specific questions for the summary section. This does not change which papers are found.",
  "Paper search terms — add extra terms to narrow your search and filter which papers are retrieved.",
  "Using an API key will not affect which papers are found, only the number of papers found and the summary quality.",
  "With an API key, full papers are used when publicly available. Without a key, only abstracts are used.",
];

export default function HelpButton({
  embedded = false,
  apiKey = "",
  rememberKey = true,
  onApiKeyChange,
  onToggleRemember,
}: HelpButtonProps) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const showApiKey = Boolean(onApiKeyChange);

  return (
    <div
      className={embedded ? "relative" : "fixed right-5 top-5 z-50"}
      ref={panelRef}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
          open
            ? "border-brand/30 bg-brand-muted text-brand"
            : "border-border bg-white text-muted hover:border-gray-300 hover:text-gray-700"
        }`}
        aria-expanded={open}
        aria-label="Notes"
      >
        <DocumentTextIcon className="h-4 w-4" />
        Notes
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-border bg-white p-5 shadow-lg animate-fade-up ${
            embedded ? "" : ""
          }`}
        >
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">Notes</h2>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>

          <ul className="space-y-2.5 text-sm leading-relaxed text-muted">
            {NOTES.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand/50" />
                <span>{note}</span>
              </li>
            ))}
          </ul>

          {showApiKey && (
            <div className="mt-5 border-t border-border pt-4">
              <label className="mb-1 block text-xs font-medium text-gray-600">
                API key (optional)
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={onApiKeyChange}
                className="mb-2 w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand/40 focus:outline-none focus:ring-2 focus:ring-brand/15"
                placeholder="OpenAI or Gemini key"
              />
              {onToggleRemember && (
                <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={rememberKey}
                    onChange={onToggleRemember}
                    className="rounded border-gray-300 text-brand focus:ring-brand/30"
                  />
                  Remember in browser
                </label>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
