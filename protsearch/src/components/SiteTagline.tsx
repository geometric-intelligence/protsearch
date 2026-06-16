export const SITE_TAGLINE = "AI-assisted protein literature search";

export const SITE_BLURB =
  "Search Europe PMC for papers on your proteins, then get a cited AI summary grounded in what we retrieve.";

type SiteTaglineProps = {
  centered?: boolean;
  showBlurb?: boolean;
  className?: string;
};

export default function SiteTagline({
  centered = false,
  showBlurb = false,
  className = "",
}: SiteTaglineProps) {
  return (
    <div
      className={`${centered ? "text-center" : "text-left"} ${className}`.trim()}
    >
      <p className="text-sm font-medium text-gray-800">{SITE_TAGLINE}</p>
      {showBlurb && (
        <p
          className={`mt-1.5 max-w-lg text-sm leading-relaxed text-muted ${
            centered ? "mx-auto" : ""
          }`}
        >
          {SITE_BLURB}
        </p>
      )}
    </div>
  );
}
