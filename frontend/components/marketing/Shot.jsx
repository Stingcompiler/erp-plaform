"use client";

// A product screenshot (lib/marketingShots.js) inside a browser-window frame.
//
// One <img> in a <picture>, so a visitor downloads one file: the dark
// capture's <source> answers to prefers-color-scheme, which is what the
// exported HTML (and a visitor without JS) follows; when the visitor has
// picked a theme on the site that differs from the system's, the source's
// media is switched to match the class-based theme. Each source is a WebP
// srcset, so a phone takes the 720 px file and a 2× desktop the widest; the
// light JPEG is for a browser without WebP. width/height give the box its
// aspect ratio before the file arrives, so nothing below it moves.
import { useI18n } from "@/app/providers/I18nProvider";
import { SHOTS, SHOT_SIZE, shotFallback, shotLanguage, shotSrcSet } from "@/lib/marketingShots";

const DARK_MEDIA = { system: "(prefers-color-scheme: dark)", dark: "all", light: "not all" };

// `sizes`: how wide the picture is laid out, for srcset. The default is a
// full-width column inside the page gutter.
export default function Shot({ name, alt, priority = false, className = "", sizes = "(min-width: 1152px) 1088px, calc(100vw - 32px)" }) {
  const { language, theme } = useI18n();
  const spec = SHOTS[name] || SHOTS.dashboard;
  const key = SHOTS[name] ? name : "dashboard";
  const lang = shotLanguage(key, language);
  return (
    <figure className={`overflow-hidden rounded-card border border-line bg-surface shadow-card ${className}`}>
      <div className="flex items-center gap-1.5 border-b border-line bg-paper px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/60" />
      </div>
      <picture>
        {spec.themes.includes("dark") && (
          <source media={DARK_MEDIA[theme] || DARK_MEDIA.system} type="image/webp" srcSet={shotSrcSet(key, lang, "dark")} sizes={sizes} />
        )}
        <source type="image/webp" srcSet={shotSrcSet(key, lang, "light")} sizes={sizes} />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={shotFallback(key, lang)}
          alt={alt}
          width={SHOT_SIZE.width}
          height={SHOT_SIZE.height}
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : undefined}
          decoding="async"
          className="block h-auto w-full"
        />
      </picture>
    </figure>
  );
}
