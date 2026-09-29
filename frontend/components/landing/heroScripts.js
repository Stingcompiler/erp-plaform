// The inline script that arms the home hero's entrance (the CSS is the
// "Public site motion" block in app/globals.css, the timings lib/motion.js).
//
// HERO_ARM runs while the HTML is still being parsed, right after the
// headline and before React: unless the visitor asked for reduced motion it puts
// `motion-ok` on <html>, and the hero's parts (never the headline) play
// their short entrance from the first frame. `hero-done` then drops every
// motion rule: counted from the first animation frame (rendering is held
// until the stylesheet arrives, so that is the first paint), with a
// fail-safe in case no frame ever comes.
//
// It is only in the exported HTML (the hero drops it after hydration and
// never renders it on a client-side navigation), so the entrance plays on a
// page load only; coming back to the home page from inside the site shows
// the hero at rest.
import { HERO_TOTAL_MS } from "../../lib/motion.js";

const DONE_AFTER_MS = HERO_TOTAL_MS + 150;
const FAILSAFE_MS = 15000;

export const HERO_ARM = `(function(){try{var c=document.documentElement.classList;if(c.contains("hero-done")||!window.matchMedia||matchMedia("(prefers-reduced-motion: reduce)").matches)return;c.add("motion-ok");var done=function(){c.add("hero-done")};requestAnimationFrame(function(){setTimeout(done,${DONE_AFTER_MS})});setTimeout(done,${FAILSAFE_MS})}catch(e){}})();`;
