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
    lead_score: float
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
            "lead_score": self.lead_score,
            "hours": self.hours,
            "maps_url": self.maps_url,
            "place_id": self.place_id,
        }


def _lead_score(rating: float | None, review_count: int, phone: str) -> float:
    """Scores how good a business prospect this lead is, out of 5 stars.

    Not Google's star rating (that's the business's customer rating) - this
    is "how good a lead is this," based on signals that the business is
    real, established, and reachable: review volume (an established
    business is more likely to be a paying customer, not a dead listing),
    review score, and having a phone number on file.
    """
    score = 1.0

    if review_count >= 200:
        score += 2.0
    elif review_count >= 50:
        score += 1.5
    elif review_count >= 10:
        score += 1.0
    elif review_count >= 1:
        score += 0.5

    if rating is not None:
        if rating >= 4.5:
            score += 1.5
        elif rating >= 4.0:
            score += 1.0
        elif rating >= 3.0:
            score += 0.5

    if phone:
        score += 0.5

    return min(5.0, round(score * 2) / 2)


def _to_lead(place: dict[str, Any]) -> Lead:
    rating = place.get("rating")
    review_count = place.get("userRatingCount", 0)
    phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber") or ""

    return Lead(
        name=place.get("displayName", {}).get("text", "(unnamed)"),
        address=place.get("formattedAddress", ""),
        phone=phone,
        rating=rating,
        review_count=review_count,
        business_status=place.get("businessStatus", ""),
        category=place.get("primaryTypeDisplayName", {}).get("text", "")
        if isinstance(place.get("primaryTypeDisplayName"), dict)
        else "",
        lead_score=_lead_score(rating, review_count, phone),
        hours=place.get("currentOpeningHours", {}).get("weekdayDescriptions", []),
        maps_url=place.get("googleMapsUri", ""),
        place_id=place.get("id", ""),
    )


def find_leads(
    query: str,
    max_results: int = 20,
    near: str | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    min_lead_score: float = 0.0,
) -> dict[str, Any]:
    """Searches Google Maps for `query` and returns places with no listed
    website, sorted by lead score (best prospects first - see `_lead_score`).

    If `near` is set, it's geocoded and results are restricted to within
    `radius_km` of that point, regardless of what's in `query`.

    `min_lead_score` drops leads scoring below it (e.g. 4.0 for "4+ stars
    only") - applied after scoring, so `stats.without_website` still
    reflects every no-website place found, separate from how many passed
    the score filter.
    """
    location_restrict = None
    origin = None
    if near:
        lat, lng = geocode_address(near)
        origin = {"address": near, "lat": lat, "lng": lng, "radius_km": radius_km}
        location_restrict = bounding_rectangle(lat, lng, radius_km)

    places = search_text(query, max_results=max_results, location_restrict=location_restrict)
    no_website = [
        p for p in places
        if not p.get("websiteUri") and p.get("businessStatus") != "CLOSED_PERMANENTLY"
    ]
    leads = [_to_lead(p) for p in no_website]
    leads.sort(key=lambda lead: (lead.lead_score, lead.review_count), reverse=True)

    shown = [lead for lead in leads if lead.lead_score >= min_lead_score]

    return {
        "leads": [lead.to_dict() for lead in shown],
        "stats": {
            "total_found": len(places),
            "without_website": len(leads),
            "shown": len(shown),
        },
        "origin": origin,
    }
