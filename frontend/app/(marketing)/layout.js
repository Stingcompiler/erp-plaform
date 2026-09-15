// The public pages. The group exists so the canonical and Open Graph URL of
// the home page can be declared here (app/page.js is a client component and
// cannot export metadata) without the root layout stamping a canonical onto
// the noindex application routes. Nested layouts override per page.
export const metadata = {
  alternates: { canonical: "/" },
  openGraph: { url: "/" },
};

export default function MarketingLayout({ children }) {
  return children;
}
