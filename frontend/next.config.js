const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

/** @type {(phase: string) => import('next').NextConfig} */
module.exports = (phase) => ({
  reactStrictMode: true,
  // Built as a static export and served directly by Django/whitenoise in
  // production (see backend/core/frontend.py) — one deployable web service.
  // trailingSlash keeps every route as a `dir/index.html`, which is what the
  // Django catch-all view expects for both `/dashboard` and `/dashboard/`.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // The dev server keeps its own cache. Sharing `.next` with `next build`
  // meant that rebuilding `out/` while `next dev` was running swapped the
  // chunks under the live server ("Cannot find module './9124.js'",
  // "Cannot read properties of undefined (reading 'call')").
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
});
