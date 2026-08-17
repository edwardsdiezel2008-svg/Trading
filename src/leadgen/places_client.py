"""Thin wrapper around the Places API (New) Text Search endpoint.

Text Search (New) can return contact fields (phone, website, hours) directly
on the search response when they're included in the field mask, so a single
paginated search is enough - no separate Place Details call per result.
Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""
from __future__ import annotations

import time
from typing import Any

import requests

from src.leadgen.config import get_api_key

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "places.primaryTypeDisplayName",
        "places.currentOpeningHours.weekdayDescriptions",
        "nextPageToken",
    ]
)

MAX_PAGE_SIZE = 20
# Google recommends a short delay before a nextPageToken becomes valid.
NEXT_PAGE_DELAY_SECONDS = 2.0


class PlacesApiError(RuntimeError):
    pass


def search_text(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Runs a Places Text Search, paginating until max_results is reached
    or Google has no more pages. Returns raw place dicts as returned by the API.
    """
    api_key = get_api_key()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    results: list[dict[str, Any]] = []
    page_token: str | None = None

    while len(results) < max_results:
        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": min(MAX_PAGE_SIZE, max_results - len(results)),
        }
        if page_token:
            body["pageToken"] = page_token
            time.sleep(NEXT_PAGE_DELAY_SECONDS)

        response = requests.post(SEARCH_URL, json=body, headers=headers, timeout=30)
        if response.status_code != 200:
            raise PlacesApiError(
                f"Places API request failed ({response.status_code}): {response.text}"
            )

        payload = response.json()
        results.extend(payload.get("places", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break

    return results[:max_results]
