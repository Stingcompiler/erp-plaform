import { guideRoute } from "@/components/marketing/content/routes";

// Static export: every slug is listed at build time; unknown slugs are 404.
export const dynamicParams = false;

const route = guideRoute("en");
export const generateStaticParams = route.generateStaticParams;
export const generateMetadata = route.generateMetadata;
export default route.Page;
