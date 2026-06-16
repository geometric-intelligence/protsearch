"use client";

import Logo from "~/components/Logo";
import HelpButton from "~/components/HelpButton";
import { SITE_TAGLINE } from "~/components/SiteTagline";

type TopBarProps = {
  apiKey?: string;
  rememberKey?: boolean;
  onApiKeyChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onToggleRemember?: () => void;
};

export default function TopBar({
  apiKey,
  rememberKey,
  onApiKeyChange,
  onToggleRemember,
}: TopBarProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white">
      <div className="mx-auto flex min-h-14 max-w-5xl items-center justify-between gap-4 px-4 py-2.5 sm:px-6">
        <Logo href="/" size="sm" tagline={SITE_TAGLINE} />
        <HelpButton
          embedded
          apiKey={apiKey}
          rememberKey={rememberKey}
          onApiKeyChange={onApiKeyChange}
          onToggleRemember={onToggleRemember}
        />
      </div>
    </header>
  );
}
