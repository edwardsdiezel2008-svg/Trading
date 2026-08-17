"""Launches the Lead Finder dashboard: search Google Maps and pull out
businesses with no listed website, with everything needed to contact them
(phone, address, hours, Maps link), one button click.

Requires GOOGLE_MAPS_API_KEY (see src/leadgen/config.py for setup).

Usage:
  python scripts/find_leads_dashboard.py
"""
from __future__ import annotations

import sys
import threading
import webbrowser

sys.path.insert(0, ".")

from src.leadgen.app import app

PORT = 5050


def main():
    url = f"http://127.0.0.1:{PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Lead Finder dashboard starting at {url}")
    app.run(port=PORT, debug=False)


if __name__ == "__main__":
    main()
