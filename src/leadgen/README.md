# Lead Finder

Finds businesses on Google Maps that have **no website listed** - the ones
most likely to need (and pay for) one - and gives you everything needed to
contact them in one place: phone number, address, rating/review count,
hours, and a link to the listing.

## Setup

1. Get a Google Maps Platform API key with **Places API (New)** enabled:
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
looking for the way you would on Google Maps itself (e.g. `roofers in
Tampa, FL`), set how many results to pull, and click **Find leads**. Results
are sorted by review count (most-established businesses first) and can be
exported to CSV with one click.

## How it works

- Uses the Places API (New) Text Search endpoint, which can return contact
  fields (phone, website, hours, rating) directly in the search response -
  no separate lookup per result needed.
- A place is treated as a lead when the API response has no `websiteUri`.
- Pagination pulls additional pages (20 results each) up to the requested
  max (capped at 100 per search to bound API cost).

## Cost note

Text Search (New) with contact fields (phone/website/hours) bills at the
"Pro SKU" rate, higher than a plain text search. Check current pricing at
https://mapsplatform.google.com/pricing/ before running large searches -
`max_results` directly controls how many billed results you pull per run.
