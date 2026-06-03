# Portfolio IQ — Demo Site

Single-page static site that **sells the concept** of the colleague's 3-agent Fabric reporting pipeline. Designed for live client demos.

## What it does

- Hero + value prop
- 3-agent architecture explanation
- **[Generate Report]** button → ~4-second animated overlay walking through the agents → reveals slide thumbnails + downloadable `.pptx`
- All static. No backend. No secrets. No failure modes during a live demo.

## Local preview

Just open `index.html` in a browser. No build step.

```powershell
# Either:
start index.html

# Or via Python http server (better — proper MIME types):
python -m http.server 8000
# then visit http://localhost:8000
```

## Deploy to Vercel

```powershell
# One-time
npm i -g vercel
vercel login

# Deploy from this folder
cd "...\03_enerwave_portfolio_reporting_agent\website"
vercel              # preview deployment (gets a unique URL)
vercel --prod       # promote to production
```

Vercel auto-detects this as a static site (no framework). The `vercel.json` only sets MIME headers for the `.pptx` and cache headers for thumbnails.

## File layout

```
website/
├── index.html              ← single page
├── style.css               ← Deloitte palette (#000 / #86BC25 / #F5F5F5)
├── script.js               ← button → overlay animation → reveal flow (vanilla JS)
├── vercel.json             ← static config + MIME headers
├── _export_thumbnails.py   ← one-shot script that generated public/thumbnails/ via PowerPoint COM
├── README.md               ← this file
└── public/
    ├── PortfolioIQ_January2026.pptx    ← the downloadable deck (copied from colleague's v7 render)
    └── thumbnails/
        └── slide_01.png ... slide_10.png   ← 1600x900 PNGs for the result-page preview grid
```

## Refreshing the deck

When the colleague's pipeline produces a fresher PPTX:

```powershell
# 1. Drop the new deck in
copy "...\Fabric\presentations\pptxs\<latest>.pptx" public\PortfolioIQ_January2026.pptx

# 2. Regenerate thumbnails
python _export_thumbnails.py

# 3. Redeploy
vercel --prod
```

## Tweaking the demo

| What | Where |
|---|---|
| Hero copy / KPIs | `index.html` (hero + .stats section) |
| Step labels / timing | `script.js` STEPS array, `index.html` .steps list |
| Colors | `style.css` `:root` block |
| Number of slides | `script.js` NUM_SLIDES constant |
| Filename in the download link | `index.html` `<a href="public/...pptx" download>` |

## Notes

- The PPTX in `public/` is **the colleague's v7 January 2026 render** — content is real Enerwave portfolio data. Confirm with your DPO before broadcasting publicly.
- Animation timing is tuned to feel "live" without losing audience attention (~4.2s total). Adjust in `script.js` STEPS if needed.
- No external CDNs or fonts — everything self-contained for offline demos.
