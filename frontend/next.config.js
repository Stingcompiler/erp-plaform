/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Built as a static export and served directly by Django/whitenoise in
  // production (see backend/core/frontend.py) — one deployable web service.
  // trailingSlash keeps every route as a `dir/index.html`, which is what the
  // Django catch-all view expects for both `/dashboard` and `/dashboard/`.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

module.exports = nextConfig;
