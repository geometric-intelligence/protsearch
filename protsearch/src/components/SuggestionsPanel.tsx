"use client";

type SuggestionItem = {
  input?: string;
  exact?: boolean;
  suggestions?: string[];
  details?: Array<{ gene: string; score?: number; gene_name?: string; aliases?: string }>;
};

export default function SuggestionsPanel({
  suggestionsData,
  selectedSuggestions,
  onChoose,
  onApply,
  onIgnore,
}: {
  suggestionsData: SuggestionItem[];
  selectedSuggestions: Record<number, string>;
  onChoose: (index: number, gene: string) => void;
  onApply: () => void;
  onIgnore: () => void;
}) {
  return (
    <div className="mb-8 rounded-xl border border-amber-200/70 bg-amber-50/50 p-6 animate-fade-up">
      <h3 className="mb-1 text-base font-semibold text-gray-900">
        Review protein names
      </h3>
      <p className="mb-5 text-sm text-muted">
        Some names were not exact matches. Pick corrections below or continue with
        your original input.
      </p>

      <div className="mb-6 space-y-3">
        {suggestionsData.map((item, idx) => {
          if (item?.exact) {
            return (
              <div
                key={idx}
                className="rounded-lg border border-emerald-200/80 bg-white px-4 py-3"
              >
                <span className="font-mono text-sm text-emerald-800">{item.input}</span>
                <span className="ml-2 text-sm text-emerald-600">Exact match</span>
              </div>
            );
          }

          const hasOptions =
            (Array.isArray(item?.suggestions) && item.suggestions.length > 0) ||
            (Array.isArray(item?.details) && item.details.length > 0);

          if (!hasOptions) {
            return (
              <div
                key={idx}
                className="rounded-lg border border-orange-200/80 bg-white px-4 py-3"
              >
                <span className="font-mono text-sm text-orange-900">{item?.input}</span>
                <p className="mt-1 text-xs text-orange-700/90">
                  No exact match in database.
                </p>
              </div>
            );
          }

          const selectedGene = selectedSuggestions[idx];
          return (
            <div key={idx} className="rounded-lg border border-border bg-white px-4 py-3">
              <p className="mb-2 text-sm text-muted">
                <span className="font-medium text-gray-700">Input:</span>{" "}
                <span className="font-mono text-gray-900">{item?.input}</span>
              </p>
              <div className="flex flex-wrap gap-2">
                {item?.details?.map((d) => {
                  const chosen = selectedGene === d.gene;
                  return (
                    <button
                      key={d.gene}
                      type="button"
                      onClick={() => onChoose(idx, d.gene)}
                      className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                        chosen
                          ? "border-brand bg-brand text-white"
                          : "border-border bg-white text-gray-700 hover:border-brand/30 hover:bg-brand-muted"
                      }`}
                    >
                      {d.gene}
                      {typeof d.score === "number" && (
                        <span className="ml-1 opacity-70">({d.score}%)</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-3 border-t border-amber-200/50 pt-4">
        <button
          type="button"
          onClick={onApply}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-hover"
        >
          Apply and search
        </button>
        <button
          type="button"
          onClick={onIgnore}
          className="rounded-lg border border-border bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          Continue with original
        </button>
      </div>
    </div>
  );
}
