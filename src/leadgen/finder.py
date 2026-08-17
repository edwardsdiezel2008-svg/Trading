"""Finds Google Maps listings that have no website on file - the leads most
likely to want (and pay for) a website or online presence, and the reason
they're leads: there's no listed link to check before you call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.leadgen.places_client import bounding_rectangle, geocode_address, search_text

DEFAULT_RADIUS_KM = 100.0


@dataclass
class Lead:
    name: str
    address: str
    phone: str
    rating: float | None
    review_count: int
    business_status: str
    category: str
    hours: list[str] = field(default_factory=list)
    maps_url: str = ""
    place_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "phone": self.phone,
            "rating": self.rating,
            "review_count": self.review_count,
            "business_status": self.business_status,
            "category": self.category,
            "hours": self.hours,
            "maps_url": self.maps_url,
            "place_id": self.place_id,
        }


def _to_lead(place: dict[str, Any]) -> Lead:
    return Lead(
        name=place.get("displayName", {}).get("text", "(unnamed)"),
        address=place.get("formattedAddress", ""),
        phone=place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber") or "",
        rating=place.get("rating"),
        review_count=place.get("userRatingCount", 0),
        business_status=place.get("businessStatus", ""),
        category=place.get("primaryTypeDisplayName", {}).get("text", "")
        if isinstance(place.get("primaryTypeDisplayName"), dict)
        else "",
        hours=place.get("currentOpeningHours", {}).get("weekdayDescriptions", []),
        maps_url=place.get("googleMapsUri", ""),
        place_id=place.get("id", ""),
    )


def find_leads(
    query: str,
    max_results: int = 20,
    near: str | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> dict[str, Any]:
    """Searches Google Maps for `query` and returns places with no listed
    website, sorted by review count (most-established businesses first -
    they're easier to verify and more likely to be a real, reachable lead).

    If `near` is set, it's geocoded and results are restricted to within
    `radius_km` of that point, regardless of what's in `query`.
    """
    location_restrict = None
    origin = None
    if near:
        lat, lng = geocode_address(near)
        origin = {"address": near, "lat": lat, "lng": lng, "radius_km": radius_km}
        location_restrict = bounding_rectangle(lat, lng, radius_km)

    places = search_text(query, max_results=max_results, location_restrict=location_restrict)
    no_website = [p for p in places if not p.get("websiteUri")]
    leads = [_to_lead(p) for p in no_website]
    leads.sort(key=lambda lead: lead.review_count, reverse=True)

    return {
        "leads": [lead.to_dict() for lead in leads],
        "stats": {
            "total_found": len(places),
            "without_website": len(leads),
        },
        "origin": origin,
    }
