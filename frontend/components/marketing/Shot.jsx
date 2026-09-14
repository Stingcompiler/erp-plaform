"use client";

// A screenshot inside a browser-window frame. Both themes are rendered and
// CSS picks one, so the picture follows the visitor's theme without JS.
export default function Shot({ light, dark, alt, priority = false, className = "" }) {
  const shared = "block w-full";
  return (
    <figure className={`overflow-hidden rounded-card border border-line bg-surface shadow-card ${className}`}>
      <div className="flex items-center gap-1.5 border-b border-line bg-paper px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/60" />
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={light} alt={alt} className={`${shared} ${dark !== light ? "dark:hidden" : ""}`} loading={priority ? "eager" : "lazy"} decoding="async" />
      {dark !== light && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={dark} alt="" aria-hidden="true" className={`${shared} hidden dark:block`} loading="lazy" decoding="async" />
      )}
    </figure>
  );
}

// Above the fold (`immediate`) animates on mount; everything else waits until
// it scrolls into view. Reduced-motion users get the final state at once.
