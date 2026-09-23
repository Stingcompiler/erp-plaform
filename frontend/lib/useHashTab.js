"use client";

// The open tab of a long page, kept in the URL hash (#backups) so a reload,
// the back button or a link from elsewhere lands on the same section. The
// first render uses the default — the static export has no hash on the
// server — and the hash is read right after mount.

import { useCallback, useEffect, useState } from "react";

export function useHashTab(ids, fallback = ids[0]) {
  const [tab, setTabState] = useState(fallback);
  const known = ids.join(",");

  useEffect(() => {
    const read = () => {
      const hash = window.location.hash.slice(1);
      if (hash && known.split(",").includes(hash)) setTabState(hash);
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [known]);

  const setTab = useCallback((id) => {
    setTabState(id);
    // replaceState: switching tabs should not fill the back history.
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
  }, []);

  // A tab that disappears (the role changed) falls back to the first one.
  const current = ids.includes(tab) ? tab : fallback;
  return [current, setTab];
}
