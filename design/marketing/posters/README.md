# «فيزانو برو» — poster series

Four advertising posters for Vezano Pro (vezano.app), each in four formats,
plus a light variant of the main poster: 20 images and 5 print PDFs.
`out/contact-sheet.png` shows all 20 at a glance.

## Goal and audience

**Goal:** bring medium and large stores and companies in Sudan to the free
trial: «ابدأ تجربتك المجانية — 14 يومًا», activated the same day.

**Audience:** owners and managers of stores with one or many branches
(retail, wholesale, distribution) who today use paper, Excel or separate
programs, and who deal every day with network and power cuts and with
payments through Bankak and other bank apps.

Arabic first (RTL); the main poster alone carries one small English line.

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
| `out/landscape/` | 1200×628 | split: text and CTA on the right, screen on the left | LinkedIn and Facebook link posts and ads, X/Twitter cards |
| `out/a4/` | 2480×3508 (A4, 300 dpi) + `.pdf` (210×297 mm) | print: ≥17 mm safe margins, CTA band with a QR code to `https://vezano.app/register/` | shop-window and counter posters, flyers, exhibitions |

Themes: all four posters in dark (navy `#0f1d2c`, teal accents); the main
poster also in light. File names are `<poster>-<theme>.png`.

**Printing:** the backgrounds bleed to the page edge but there is no extra
bleed area; ask the printer for "fit to page" or add 3 mm bleed in their
tool. The PDF keeps text as vector; the app screenshots are the 1440×900
marketing captures, upscaled about 1.5× on A4 — fine for posters viewed at
arm's length; recapture them at 2× for large-format prints. Big soft shadows
are dropped in the PDF (some viewers draw them as dark boxes).

**QR check:** the generator decodes every A4 PNG's QR with jsQR and writes
the result to `out/qr-check.txt` (fails the run on a mismatch).

## Regenerating

From the repo root (needs `frontend/node_modules` with Playwright's Chromium
and sharp, and a network connection for Google Fonts and cdn.jsdelivr.net):

```sh
node design/marketing/posters/generate.mjs                 # all 20 PNGs, 5 PDFs, QR check, contact sheet
node design/marketing/posters/generate.mjs square offline  # only matching format/poster names
```

Everything lives in `generate.mjs`: copy per poster (`POSTERS`), colours
(`THEME`), type sizes per format (`SIZES`), one layout per format
(`layout()`), and the visuals (browser frame, phone, branch diagram, sync
motif, transfer card). The logo comes from `frontend/lib/brandMark.js`, the
screenshots from `frontend/public/marketing/`. It stops if a font fails to
load and warns if text spills out of the safe area.
