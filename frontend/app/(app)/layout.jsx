import { NOINDEX } from "@/lib/site";

import AppLayoutClient from "./AppLayoutClient";

// Every signed-in route lives under this group. The shell itself needs the
// client runtime (auth, sync, toasts), so the client half is a sibling file
// and this server layout only adds what a client file cannot export: the
// noindex rule that keeps the application out of search results.
export const metadata = { title: "مساحة العمل", robots: NOINDEX };

export default function AppLayout({ children }) {
  return <AppLayoutClient>{children}</AppLayoutClient>;
}
