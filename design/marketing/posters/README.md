# «فيزانو برو» — poster series

Four advertising posters for Vezano Pro (vezano.app), each in four formats,
plus a light variant of the main poster: 20 images and 5 print PDFs, in
Arabic (the primary set) and in English (the same 20 + 5, file names ending
in `-en`). `out/contact-sheet.png` and `out/contact-sheet-en.png` show each
set at a glance.

## Goal and audience

**Goal:** bring medium and large stores and companies in Sudan to the free
trial: «ابدأ تجربتك المجانية — 14 يومًا», activated the same day.

**Audience:** owners and managers of stores with one or many branches
(retail, wholesale, distribution) who today use paper, Excel or separate
programs, and who deal every day with network and power cuts and with
payments through Bankak and other bank apps.

Arabic first. The English set is for English-speaking decision makers,
partners, investors and LinkedIn.

## Each language has its own identity

Each set is purely one language, from the words to the app on screen:

| | Arabic set | English set |
|---|---|---|
| Name and lockup | «فيزانو برو» (mark on the right) | "Vezano Pro" (mark on the left) |
| Type | Readex Pro 700 headlines, Tajawal text | Readex Pro 700 headlines, Inter text |
| Direction | RTL: text on the right, screen and overlays on the left | LTR: the mirror image |
| App screenshots | the Arabic app, «شركة النور للتجارة», amounts in ج.س (`frontend/public/marketing/`) | the English app, "Al Noor Trading", amounts in SDG (`assets/en/`) |
| Small visuals | «نقطة البيع»، الخرطوم / أم درمان / بحري، «تحويل بنكي مسجّل» | "Point of sale", Khartoum / Omdurman / Bahri, "Transfer recorded" |

No English line appears on the Arabic posters (the main poster's small
English line was removed) and no Arabic on the English ones; `vezano.app`
is the only shared text.

## English set

Same layouts mirrored to LTR (text on the left, overlays on the other side),
Readex Pro 700 for headlines and the "Vezano Pro" wordmark ("Pro" in teal),
Inter for everything else, and the English app on every screen.

| # | Headline | Supporting points |
|---|---|---|
| 1 | One system for your whole business — every branch | Sales · Inventory · Purchasing · Customers · Staff · Financial management — Keeps selling when the network drops |
| 2 | All your branches in one place / each person sees what’s theirs | Each branch sees its own data; head office sees everything · 12 roles with clear permissions · Approvals for discounts and till shifts · A log of every action |
| 3 | Selling never stops / even when the network or power goes out | The till sells and collects payments offline · Everything is saved and synced once when you’re back online · No duplicates, nothing lost |
| 4 | Bankak and bank-app payments / recorded and matched | Record each transfer with its transaction number · Match your bank statement in one click · A debt ledger that knows who owes you and since when |

CTA «Start your free trial — 14 days», «Activated the same day», `vezano.app`;
the A4 QR says «Scan to sign up». The same honesty rules apply (below). In
the visuals: "Point of sale", branches Khartoum / Omdurman / Bahri with
"Head office sees all", "Offline: still selling → Back online: synced", and a
"Transfer recorded · Matched to statement" card (amounts in SDG).

### English screenshots (`assets/en/`)

dashboard, dashboard-dark, pos, pos-dark, inventory, debts and users at
1440×900, the same views and crops as the Arabic site captures, taken from a
throwaway local copy of the app — never production:

1. A scratch SQLite database (`DATABASE_URL=sqlite:///…`, `DEBUG=True`,
   `VEZANO_ENV_FILE=/dev/null` so no real `.env` is read), `migrate`,
   `seed_roles`, then a company "Al Noor Trading" (currency SDG, branches
   "Main branch – Khartoum" and "Omdurman branch") with fictional staff on
   `@alnoor.example`: Ahmed Elnour (Business Owner), Huda Saleh (Finance
   Department), Khalid Ibrahim (Branch Manager, Omdurman), Mona Eltayeb (Sales
   Officer), Sara Osman (General Manager), Yousif Hassan (Inventory Officer).
2. `manage.py seed_demo --owner demo-owner@alnoor.example --scale 2500
   --sales 60 --lang en --yes` — `--lang en` writes the catalogue, customers,
   suppliers, leads and public page in English (same prices and SKUs as the
   Arabic run).
3. Quiet screens: the company's layout set to multi-branch (no first-run
   question), items under their reorder level restocked, a till shift open.
4. Django on :8010, `next dev` on :3010, signed in as the owner with the
   `erp_language=en` cookie and `erp.language=en` in local storage; light and
   dark via `erp.theme`; the POS cart holds basmati rice, cooking oil, black
   tea, sugar and long-life milk (44,000.00 SDG), like the Arabic capture.

## Messages, one per poster

| # | File key | Headline | Supporting points | Visual |
|---|---|---|---|---|
| 1 | `01-main` | نظام واحد يدير متجرك بكل فروعه | المبيعات · المخزون · المشتريات · العملاء · الموظفون · الإدارة المالية — ويستمر حتى مع انقطاع الشبكة | dashboard in a browser frame + POS on a phone |
| 2 | `02-branches` | كل فروعك في مكان واحد — وكل موظف يرى ما يخصّه | كل فرع يرى بياناته والإدارة ترى الكل · 12 دورًا بصلاحيات واضحة · موافقات للخصم واعتماد الورديات · سجل لكل عملية | branches → hub diagram (the logo's idea) + users screen |
| 3 | `03-offline` | البيع ما بيقف — حتى لو قطعت الشبكة أو الكهرباء | الكاشير يبيع ويحصّل دون إنترنت · كل العمليات تُحفظ وتُزامَن مرة واحدة عند عودة الاتصال · بلا تكرار ولا ضياع | POS screen + "offline → synced" motif |
| 4 | `04-bankak` | بنكك والتطبيقات البنكية… مسجّلة ومطابَقة | سجّل التحويل برقم العملية · طابِق كشف الحساب بضغطة · دفتر ديون يعرف من يدين لك ومنذ متى | debts ledger + a recorded, matched transfer card |

Every poster carries the lockup (mark + «فيزانو برو»), the CTA
«ابدأ تجربتك المجانية — 14 يومًا», «تفعيل في نفس اليوم» and `vezano.app`.

**Claims we keep honest** (checked against the product):

- Bank apps are **not integrated**: a transfer is recorded by hand with its
  transaction number and matched against an uploaded statement. The poster
  says «سجّل التحويل برقم العملية», never "automatic".
- No WhatsApp notifications, no double-entry accounting (we say
  «الإدارة المالية»), no prices (pricing is deferred), no testimonials or
  customer logos.
- The trial is 14 days (`VEZANO_TRIAL_DAYS`); 12 roles matches the site.
- «حتى لو قطعت … الكهرباء» assumes the till device itself stays on (a laptop,
  tablet or phone on battery).
- Screens are the demo company («شركة النور للتجارة»); the branch names in
  the diagram (الخرطوم، أم درمان، بحري) and the transfer card figures are
  illustrations.

## Formats and where to use them

| Folder | Size | Layout | Use |
|---|---|---|---|
| `out/story/` | 1080×1920 | tall: lockup, big headline, points, visual, full-width CTA | Instagram/Facebook/WhatsApp status stories, TikTok covers |
| `out/square/` | 1080×1080 | compact: headline, 2–3 points, a cropped strip of the screen, CTA row | Instagram/Facebook feed posts, WhatsApp groups |
| `out/landscape/` | 1200×628 | split: text and CTA on the right, screen on the left (mirrored in English) | LinkedIn and Facebook link posts and ads, X/Twitter cards |
| `out/a4/` | 2480×3508 (A4, 300 dpi) + `.pdf` (210×297 mm) | print: ≥17 mm safe margins, CTA band with a QR code to `https://vezano.app/register/` | shop-window and counter posters, flyers, exhibitions |

Themes: all four posters in dark (navy `#0f1d2c`, teal accents); the main
poster also in light. File names are `<poster>-<theme>.png`, and
`<poster>-<theme>-en.png` for English (A4: `.pdf` beside each PNG).

**Printing:** the backgrounds bleed to the page edge but there is no extra
bleed area; ask the printer for "fit to page" or add 3 mm bleed in their
tool. The PDF keeps text as vector; the app screenshots are the 1440×900
marketing captures, upscaled about 1.5× on A4 — fine for posters viewed at
arm's length; recapture them at 2× for large-format prints. Big soft shadows
are dropped in the PDF (some viewers draw them as dark boxes).

**QR check:** the generator decodes every A4 PNG's QR with jsQR and writes
the result to `out/qr-check.txt` and `out/qr-check-en.txt` (fails the run on
a mismatch). All ten A4 QR codes decode to `https://vezano.app/register/`.

## Regenerating

From the repo root (needs `frontend/node_modules` with Playwright's Chromium
and sharp, and a network connection for Google Fonts and cdn.jsdelivr.net):

```sh
node design/marketing/posters/generate.mjs                 # both sets: 40 PNGs, 10 PDFs, QR checks, 2 contact sheets
node design/marketing/posters/generate.mjs --lang=en       # one set only (ar | en)
node design/marketing/posters/generate.mjs --sheets        # only rebuild the two contact sheets
node design/marketing/posters/generate.mjs square offline  # only matching format/poster names
```

Everything lives in `generate.mjs`: copy per poster (`POSTERS`, `tx(ar, en)`),
shared strings (`COPY`), the LTR mirroring of overlays (`m()`), colours
(`THEME`), type sizes per format (`SIZES`), one layout per format
(`layout()`), and the visuals (browser frame, phone, branch diagram, sync
motif, transfer card). The logo comes from `frontend/lib/brandMark.js`, the
screenshots from `frontend/public/marketing/` (Arabic) and `assets/en/`
(English); a crop written for the Arabic screen is mirrored for the English
one (`mpos()`), and a leading `=` keeps a style or crop as written. It stops if a font fails to
load and warns if text spills out of the safe area.

Re-rendering changes PNG bytes slightly (anti-aliasing) even when nothing
visible changed; render only the set you edited (`--lang=`) to keep the
other set's files untouched.
