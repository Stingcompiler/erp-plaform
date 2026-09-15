// Server-side route builders for the generated content pages. Each route
// file under app/(marketing) (and its en/ twin) is three lines that pick a
// language here; everything a static export needs — the param list, the
// metadata with hreflang, the JSON-LD — is produced in one place so the two
// language trees cannot drift.
import JsonLd from "@/components/seo/JsonLd";
import { GUIDES_INDEX_PATH, INDEX_COPY, SOLUTIONS_INDEX_PATH } from "@/lib/content";
import { COMPARISONS, comparison } from "@/lib/content/compare";
import { GUIDES, guide } from "@/lib/content/guides";
import { SOLUTIONS, solution } from "@/lib/content/solutions";
import { marketingMetadata } from "@/lib/marketingMeta";
import { articleJsonLd, breadcrumbJsonLd, faqJsonLd, webPageJsonLd } from "@/lib/seo";

import ComparePage from "./ComparePage";
import GuidePage from "./GuidePage";
import { GuidesIndexPage, SolutionsIndexPage } from "./IndexPages";
import SolutionPage from "./SolutionPage";

const HOME = { ar: "الرئيسية", en: "Home" };

function indexTitle(path, language) {
  return INDEX_COPY[path][language].title;
}

export function solutionsIndexRoute(language) {
  const path = SOLUTIONS_INDEX_PATH;
  return {
    metadata: marketingMetadata(path, language),
    Page: function SolutionsIndexRoute() {
      return (
        <>
          <JsonLd data={[webPageJsonLd(path, language), breadcrumbJsonLd([[HOME[language], "/"], [indexTitle(path, language), path]], language)]} />
          <SolutionsIndexPage />
        </>
      );
    },
  };
}

export function guidesIndexRoute(language) {
  const path = GUIDES_INDEX_PATH;
  return {
    metadata: marketingMetadata(path, language),
    Page: function GuidesIndexRoute() {
      return (
        <>
          <JsonLd data={[webPageJsonLd(path, language), breadcrumbJsonLd([[HOME[language], "/"], [indexTitle(path, language), path]], language)]} />
          <GuidesIndexPage />
        </>
      );
    },
  };
}

export function solutionRoute(language) {
  return {
    generateStaticParams: () => SOLUTIONS.map((item) => ({ slug: item.slug })),
    generateMetadata: async ({ params }) => {
      const { slug } = await params;
      return marketingMetadata(`${SOLUTIONS_INDEX_PATH}/${slug}`, language);
    },
    Page: async function SolutionRoute({ params }) {
      const { slug } = await params;
      const item = solution(slug);
      const path = `${SOLUTIONS_INDEX_PATH}/${slug}`;
      const copy = item[language];
      return (
        <>
          <JsonLd
            data={[
              webPageJsonLd(path, language),
              faqJsonLd(copy.faq),
              breadcrumbJsonLd(
                [[HOME[language], "/"], [indexTitle(SOLUTIONS_INDEX_PATH, language), SOLUTIONS_INDEX_PATH], [copy.title, path]],
                language
              ),
            ]}
          />
          <SolutionPage slug={slug} />
        </>
      );
    },
  };
}

export function guideRoute(language) {
  return {
    generateStaticParams: () => GUIDES.map((item) => ({ slug: item.slug })),
    generateMetadata: async ({ params }) => {
      const { slug } = await params;
      const item = guide(slug);
      const base = marketingMetadata(`${GUIDES_INDEX_PATH}/${slug}`, language);
      return {
        ...base,
        openGraph: {
          ...base.openGraph,
          type: "article",
          publishedTime: item.published,
          modifiedTime: item.modified,
        },
      };
    },
    Page: async function GuideRoute({ params }) {
      const { slug } = await params;
      const item = guide(slug);
      const path = `${GUIDES_INDEX_PATH}/${slug}`;
      const copy = item[language];
      return (
        <>
          <JsonLd
            data={[
              articleJsonLd({
                path,
                language,
                title: copy.title,
                description: copy.description,
                published: item.published,
                modified: item.modified,
                minutes: item.minutes,
              }),
              breadcrumbJsonLd(
                [[HOME[language], "/"], [indexTitle(GUIDES_INDEX_PATH, language), GUIDES_INDEX_PATH], [copy.title, path]],
                language
              ),
            ]}
          />
          <GuidePage slug={slug} />
        </>
      );
    },
  };
}

export function compareRoute(language) {
  return {
    generateStaticParams: () => COMPARISONS.map((item) => ({ slug: item.slug })),
    generateMetadata: async ({ params }) => {
      const { slug } = await params;
      return marketingMetadata(`/compare/${slug}`, language);
    },
    Page: async function CompareRoute({ params }) {
      const { slug } = await params;
      const item = comparison(slug);
      const path = `/compare/${slug}`;
      return (
        <>
          <JsonLd data={[webPageJsonLd(path, language), breadcrumbJsonLd([[HOME[language], "/"], [item[language].title, path]], language)]} />
          <ComparePage slug={slug} />
        </>
      );
    },
  };
}
