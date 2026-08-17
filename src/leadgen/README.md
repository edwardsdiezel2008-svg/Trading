# Lead Finder

Finds businesses on Google Maps that have **no website listed** - the ones
most likely to need (and pay for) one - and gives you everything needed to
contact them in one place: phone number, address, rating/review count,
hours, and a link to the listing.

## Setup

1. Get a Google Maps Platform API key with **Places API (New)** and
   **Geocoding API** enabled (Geocoding is only needed if you use the
   starting-address/radius search):
   https://console.cloud.google.com/google/maps-apis/credentials
2. Set it as an environment variable, or put it in a `.env` file at the repo
   root (gitignored, never commit it):
   ```
   GOOGLE_MAPS_API_KEY=your-key-here
   ```
3. Install dependencies (already in `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```

## Run the dashboard

```bash
python scripts/find_leads_dashboard.py
```

This opens a browser tab at `http://127.0.0.1:5050`. Type what you're
looking for (e.g. `roofers`, `coffee shops`, `dentists`), optionally set a
**starting address** and **radius** to restrict the search geographically,
set how many results to pull, and click **Find leads**. Results stream into
the results feed below the button as readable cards (name, category,
address, phone, hours, Maps link) and can be exported to CSV with one click.
Each card also shows a 1-5 star **lead score** - not Google's customer
rating, but how good a prospect the business looks like (established,
reachable, reviewed) based on review volume, review score, and whether a
phone number is on file. Leads are sorted best-score-first, businesses
marked permanently closed on Google are dropped since they're not real
leads, and the **★ 4+** checkbox filters the list down to only leads
scoring 4 stars or higher.

If no starting address is given, put the location in the search box itself
(e.g. `roofers in Tampa, FL`), same as searching on Google Maps directly.

## How it works

- Uses the Places API (New) Text Search endpoint, which can return contact
  fields (phone, website, hours, rating) directly in the search response -
  no separate lookup per result needed.
- A place is treated as a lead when the API response has no `websiteUri`.
- Pagination pulls additional pages (20 results each) up to the requested
  max (capped at 100 per search to bound API cost).
- The starting address is resolved to coordinates via the Geocoding API
  (also needs to be enabled on the same project), then results are
  restricted to a bounding box approximating that radius around it (a
  rectangle, not a precise circle - Places' circle restriction caps out at
  50km, too small for a 100km ask).

## Cost note

Text Search (New) with contact fields (phone/website/hours) bills at the
"Pro SKU" rate, higher than a plain text search. Check current pricing at
https://mapsplatform.google.com/pricing/ before running large searches -
`max_results` directly controls how many billed results you pull per run.
