# rhk-rv-campground/

A website for **RHK RV Campground Park** (operated by RHK Holdings Ltd.), a
real, existing all-season RV lot rental park in Parkland County, Alberta.

## What's real vs. what still needs confirming

This was built from public web search results, not from the business's own
site — `rhkrvcampground.ca` did not resolve from this environment, and Yelp
was blocked. So:

**Confirmed from public search results:**
- Business name, RHK Holdings Ltd. as operator
- Phone: (780) 945-3487
- Location: Parkland County, Alberta
- Opened fall 2019, mid-to-long-term all-season RV lots
- Lot rent ~$700/month (as of the last publicly indexed info — **may be
  outdated**, the page says so explicitly)
- Includes sewer, water, Wi-Fi; power separately metered
- 30' × 60' lots, picnic table + fire pit per lot, fenced/gated, camera-monitored

**Not included because it couldn't be verified — needs the business's input:**
- **Exact street address** — the page only says "call for directions."
  Replace `.about-note` in `index.html` once you have it.
- **Current 2026 pricing** — flagged with a rate-note on the page itself.
  Confirm with the business before publishing.
- **The lumber yard** — mentioned in the "Also From RHK Holdings Ltd."
  section, but with no fabricated name, address, or details, since no
  public source connects one to this specific RHK Holdings Ltd. Replace
  that section's copy once you have the real business name and details.
- **Reviews** — no review text is quoted anywhere on the page. There's a
  "Read Our Reviews on Google" button instead, linking to a Google Maps
  search for the business name (not a fabricated direct listing URL).
  If you get real review quotes with permission to use them, they can be
  added directly to the `#reviews` section in `index.html`.

## Design notes

Built for an older-skewing audience per the request: larger base font size
(18px+), high-contrast light theme (not the dark themes used on the other
two demo sites in this repo), big tap targets, phone number treated as a
first-class action throughout, and no scroll-triggered fade-in animations —
content is visible immediately. The one animated element is the hero canvas
scene (a dusk pine forest with drifting embers), which is contained to its
own panel rather than full-bleed behind text, moves slowly and
autonomously (no mouse-tracking dependency), and freezes on a single frame
under `prefers-reduced-motion`.

## View it

```bash
cd rhk-rv-campground
python3 -m http.server 8000
```
