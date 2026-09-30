"use client";

// A screenshot inside a browser-window frame. Both themes are rendered and
// CSS picks one, so the picture follows the visitor's theme without JS.
// width/height are the capture's pixels: with h-auto they give the box its
// aspect ratio before the file arrives, so nothing below it moves.
export default function Shot({ light, dark, alt, priority = false, className = "", width = 1440, height = 900 }) {
  const shared = "block h-auto w-full";
  return (
    <figure className={`overflow-hidden rounded-card border border-line bg-surface shadow-card ${className}`}>
      <div className="flex items-center gap-1.5 border-b border-line bg-paper px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/60" />
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={light} alt={alt} className={`${shared} ${dark !== light ? "dark:hidden" : ""}`} width={width} height={height} loading={priority ? "eager" : "lazy"} decoding="async" />
      {dark !== light && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={dark} alt="" aria-hidden="true" className={`${shared} hidden dark:block`} width={width} height={height} loading="lazy" decoding="async" />
      )}
    </figure>
  );
}
