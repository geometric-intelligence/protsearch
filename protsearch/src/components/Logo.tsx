import Link from "next/link";
import { BeakerIcon } from "@heroicons/react/24/outline";

type LogoProps = {
  href?: string;
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  tagline?: string;
  className?: string;
};

const sizes = {
  sm: { box: "h-9 w-9", icon: "h-4 w-4", title: "text-lg", gap: "gap-2.5" },
  md: { box: "h-10 w-10", icon: "h-5 w-5", title: "text-xl", gap: "gap-3" },
  lg: { box: "h-11 w-11", icon: "h-5 w-5", title: "text-2xl", gap: "gap-3" },
};

export default function Logo({
  href = "/",
  size = "md",
  showText = true,
  tagline,
  className = "",
}: LogoProps) {
  const s = sizes[size];
  const content = (
    <div className={`group inline-flex items-center ${s.gap} ${className}`}>
      <div
        className={`flex ${s.box} shrink-0 items-center justify-center rounded-xl border border-border bg-white text-brand transition-colors group-hover:border-brand/25 group-hover:bg-brand-muted/40`}
      >
        <BeakerIcon className={s.icon} strokeWidth={1.75} aria-hidden />
      </div>
      {showText && (
        <div className="text-left">
          <span className={`block font-semibold tracking-tight text-gray-900 ${s.title}`}>
            ProtSearch
          </span>
          {tagline && (
            <span className="block text-xs leading-snug text-muted">{tagline}</span>
          )}
        </div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="inline-block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
      >
        {content}
      </Link>
    );
  }

  return content;
}
