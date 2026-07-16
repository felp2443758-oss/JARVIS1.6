"""Google APIs integration: Weather (Maps Platform) + Calendar OAuth + Geocoding."""
from __future__ import annotations
import os
import json
import time
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
WEATHER_URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "email",
    "profile",
]


# ---------- Geocoding ----------
async def geocode(city: str) -> Optional[Dict[str, float]]:
    if not GOOGLE_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(GEOCODE_URL, params={"address": city, "key": GOOGLE_API_KEY})
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        formatted = data["results"][0].get("formatted_address", city)
        return {"lat": loc["lat"], "lng": loc["lng"], "name": formatted}


DEFAULT_CITY = os.environ.get("DEFAULT_CITY", "Belo Horizonte, MG")


async def reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """Return a human-readable place name for given coordinates."""
    if not GOOGLE_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(
                GEOCODE_URL,
                params={"latlng": f"{lat},{lng}", "key": GOOGLE_API_KEY, "language": "pt-BR"},
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        # Prefer locality
        for res in data["results"]:
            comps = res.get("address_components", [])
            locality = next((c["long_name"] for c in comps if "locality" in c.get("types", [])), None)
            admin = next((c["short_name"] for c in comps if "administrative_area_level_1" in c.get("types", [])), None)
            if locality:
                return f"{locality}{', ' + admin if admin else ''}"
        return data["results"][0].get("formatted_address")
    except Exception:
        return None


# ---------- Weather ----------
async def get_weather(city: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
    """Calls Google Maps Platform Weather API (currentConditions:lookup).
    Priority: explicit lat/lng -> city geocode -> DEFAULT_CITY fallback.
    Falls back to a hard-coded mock if the API key/endpoint isn't accessible."""
    target_city = city or DEFAULT_CITY
    if not GOOGLE_API_KEY:
        return _fallback_weather(target_city, reason="no_api_key")

    geo: Optional[Dict[str, Any]] = None
    if lat is not None and lng is not None:
        name = await reverse_geocode(lat, lng) or "Localização atual"
        geo = {"lat": lat, "lng": lng, "name": name}
    else:
        geo = await geocode(target_city)
        if not geo:
            # Last-resort: try Belo Horizonte hardcoded coords
            geo = {"lat": -19.9167, "lng": -43.9345, "name": "Belo Horizonte, MG"}

    params = {
        "key": GOOGLE_API_KEY,
        "location.latitude": str(geo["lat"]),
        "location.longitude": str(geo["lng"]),
        "unitsSystem": "METRIC",
        "languageCode": "pt-BR",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(WEATHER_URL, params=params)
        if r.status_code != 200:
            return _fallback_weather(city, reason=f"http_{r.status_code}", geo=geo)
        d = r.json()
        # Schema reference: weatherCondition.description.text, temperature.degrees,
        # feelsLikeTemperature.degrees, relativeHumidity, wind.speed.value, etc.
        cond = (d.get("weatherCondition") or {})
        desc_obj = cond.get("description") or {}
        return {
            "city": geo["name"],
            "temp_c": round(((d.get("temperature") or {}).get("degrees") or 0)),
            "feels_like_c": round(((d.get("feelsLikeTemperature") or {}).get("degrees") or 0)),
            "humidity": int(d.get("relativeHumidity") or 0),
            "description": desc_obj.get("text") or cond.get("type") or "",
            "wind_kmh": round(((d.get("wind") or {}).get("speed") or {}).get("value") or 0),
            "icon": cond.get("iconBaseUri"),
            "source": "google_weather_api",
        }
    except Exception as e:
        return _fallback_weather(city, reason=f"exception:{e}", geo=geo)


def _fallback_weather(city: str, reason: str = "", geo: Optional[dict] = None) -> Dict[str, Any]:
    return {
        "city": (geo or {}).get("name", city or "Belo Horizonte, MG"),
        "temp_c": 22,
        "feels_like_c": 22,
        "humidity": 60,
        "description": "dados meteorológicos indisponíveis no momento",
        "wind_kmh": 8,
        "source": "fallback",
        "fallback_reason": reason,
    }


# ---------- Google Calendar OAuth ----------
def oauth_login_url(state: str) -> Optional[str]:
    if not (GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI):
        return None
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{OAUTH_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> Optional[Dict[str, Any]]:
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI):
        return None
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(OAUTH_TOKEN_URL, data=data)
        if r.status_code != 200:
            return None
        return r.json()


async def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    data = {
        "refresh_token": refresh_token,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(OAUTH_TOKEN_URL, data=data)
        if r.status_code != 200:
            return None
        return r.json()


async def list_today_events(access_token: str) -> List[Dict[str, Any]]:
    today = date.today()
    time_min = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    time_max = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "20",
    }
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(CALENDAR_EVENTS_URL, headers=headers, params=params)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
    out: List[Dict[str, Any]] = []
    for it in items:
        start = it.get("start") or {}
        dt = start.get("dateTime") or start.get("date") or ""
        time_str = dt[11:16] if "T" in dt else "All day"
        out.append({
            "time": time_str,
            "title": it.get("summary", "(sem título)"),
            "location": it.get("location", ""),
        })
    return out
