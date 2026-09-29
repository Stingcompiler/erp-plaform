// The two inline scripts that run the home hero's entrance (the CSS is the
// "Public site motion" block in app/globals.css, the timings lib/motion.js).
//
// They run while the HTML is still being parsed, before React, so the hero
// is never painted first and hidden after:
//
//   HERO_ARM, just before the hero: unless the visitor asked for reduced
//   motion, put `motion-ok` on <html>; the hero's parts now start from
//   their masks. A fail-safe marks the hero done if nothing else does.
//
//   HERO_GO, right after the <h1>: wait for the headline's font (at most
//   HERO.fontWaitMs), then `hero-go` starts the entrance and `hero-done`
//   drops every motion rule once it has ended.
//
// They are only in the exported HTML (the hero drops them after
// hydration and never renders them on a client-side navigation), so the
// entrance plays on a page load only; coming back to the home page from
// inside the site shows the hero at rest.
import { HERO, HERO_TOTAL_MS } from "../../lib/motion.js";

const FAILSAFE_MS = HERO.fontWaitMs + HERO_TOTAL_MS + 1600;

export const HERO_ARM = `(function(){try{var c=document.documentElement.classList;if(c.contains("hero-done")||!window.matchMedia||matchMedia("(prefers-reduced-motion: reduce)").matches)return;c.add("motion-ok");setTimeout(function(){c.add("hero-done")},${FAILSAFE_MS})}catch(e){}})();`;

export const HERO_GO = `(function(){var d=document,c=d.documentElement.classList;try{if(!c.contains("motion-ok")||c.contains("hero-go")||c.contains("hero-done"))return;var h=d.currentScript&&d.currentScript.previousElementSibling,s=0,go=function(){if(s)return;s=1;requestAnimationFrame(function(){c.add("hero-go");setTimeout(function(){c.add("hero-done")},${HERO_TOTAL_MS + 50})})};setTimeout(go,${HERO.fontWaitMs});if(h&&d.fonts&&d.fonts.load){d.fonts.load(getComputedStyle(h).font,h.textContent).then(go,go)}else{go()}}catch(e){c.add("hero-done")}})();`;
