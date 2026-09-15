import { marketingMetadata } from "@/lib/marketingMeta";

export const metadata = marketingMetadata("/register", "en");

export default function RegisterLayout({ children }) {
  return children;
}
