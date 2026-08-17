"""Dashboard for finding Google Maps listings with no website.

Run with `python scripts/find_leads_dashboard.py`, then open the browser
tab it launches and click "Find leads."
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from src.leadgen.finder import find_leads
from src.leadgen.places_client import PlacesApiError

app = Flask(__name__)

MAX_ALLOWED_RESULTS = 100


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Enter what to search for, e.g. 'plumbers in Austin, TX'."}), 400

    try:
        max_results = int(data.get("max_results", 20))
    except (TypeError, ValueError):
        max_results = 20
    max_results = max(1, min(max_results, MAX_ALLOWED_RESULTS))

    try:
        result = find_leads(query, max_results=max_results)
    except PlacesApiError as exc:
        return jsonify({"error": str(exc)}), 502
    except RuntimeError as exc:
        # Missing/invalid API key.
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)


def main():
    app.run(debug=True, port=5050)


if __name__ == "__main__":
    main()
