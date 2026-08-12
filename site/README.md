# site/

A standalone, static 3D portfolio site — not part of the trading toolkit,
just living alongside it in its own folder.

No build step: it's raw HTML/CSS/JS. The "3D" is a raymarched scene
(metaballs, lighting, ambient occlusion, fresnel rim light) written directly
as a WebGL fragment shader in `js/shader-bg.js` — no Three.js or other
dependency. Everything else (scroll reveal, nav, 3D-tilt project cards,
scroll progress bar) is vanilla JS in `js/main.js`.

## View it

Any static file server works, e.g.:

```bash
cd site
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

(Opening `index.html` directly via `file://` also works in most browsers,
since there are no fetch/XHR calls.)

## Customize

All copy in `index.html` — name, bio, project cards, contact links — is
placeholder content ("Jordan Vale") for you to replace with your own.
Colors and type live as CSS custom properties at the top of `css/style.css`.
