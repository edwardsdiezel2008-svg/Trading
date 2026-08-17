# hollow-creek-timber/

A standalone marketing site for a fictional hardwood lumber yard — not part
of the trading toolkit, just living alongside it in its own folder.

**Everything about the business — the name (Hollow Creek Timber Co.), the
Whitfield family history, the address, phone, prices, testimonials — is
invented placeholder content.** Swap it for a real business's details before
using this for anything real. Species descriptions and Janka hardness values
are factually accurate for the species named; prices are not.

No build step: raw HTML/CSS/JS. Every board face and the hero log
cross-section are drawn procedurally on `<canvas>` in `js/grain.js` (seeded
per species, so they look the same on every visit) — there's no stock
photography to source or license.

## View it

```bash
cd hollow-creek-timber
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## What's functional vs. what needs wiring

- **Board foot calculator** (`#calculator`) is fully functional client-side math.
- **Quote request form** (`#quote`) validates and shows a success message, but
  does not actually send anywhere — there's no backend. Wire it to a form
  service (Formspree, Netlify Forms) or your own endpoint before relying on it.
- **Species detail modals** and the catalog grid are fully functional.

## Customize

Business details live in the copy in `index.html`, and the price/hardness/use
data for each species lives in `SPECIES_DATA` near the bottom of `js/main.js`.
Colors and type are CSS custom properties at the top of `css/style.css`.
