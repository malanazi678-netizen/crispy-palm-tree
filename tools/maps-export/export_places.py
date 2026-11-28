#!/usr/bin/env python3
"""Export Google Maps places (Places API New, Text Search) for a polygon, split into a grid.

Reads settings from .env, the area from boundary.txt (one "lat,lng" per line, 4 corners),
and writes OUTPUT_CSV. Standard library only.
"""
import csv
import json
import os
import sys
import time
import urllib.request

API_URL = os.environ.get("PLACES_API_URL", "https://places.googleapis.com/v1/places:searchText")
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.rating", "places.userRatingCount", "places.nationalPhoneNumber",
    "places.googleMapsUri", "nextPageToken",
])


def load_env(path=".env"):
    """Values from .env; real environment variables override them."""
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    env.update(os.environ)
    return env


def read_bounds(path):
    pts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lat, lng = (float(x) for x in line.split(",")[:2])
                pts.append((lat, lng))
    lats = [p[0] for p in pts]
    lngs = [p[1] for p in pts]
    return min(lats), min(lngs), max(lats), max(lngs)  # south, west, north, east


def grid_cells(south, west, north, east, n):
    lat_step = (north - south) / n
    lng_step = (east - west) / n
    for i in range(n):
        for j in range(n):
            yield (south + i * lat_step, west + j * lng_step,
                   south + (i + 1) * lat_step, west + (j + 1) * lng_step)


def search(api_key, query, cell):
    s, w, n, e = cell
    results, page_token = [], None
    while True:
        body = {
            "textQuery": query,
            "maxResultCount": 20,
            "locationRestriction": {"rectangle": {
                "low": {"latitude": s, "longitude": w},
                "high": {"latitude": n, "longitude": e},
            }},
        }
        if page_token:
            body["pageToken"] = page_token
        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "X-Goog-Api-Key": api_key,
                     "X-Goog-FieldMask": FIELDS})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            print(f"  HTTP {err.code}: {err.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
            break
        results.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)  # next page token needs a short delay before it is valid
    return results


def main():
    env = load_env()
    api_key = env.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        sys.exit("Missing GOOGLE_MAPS_API_KEY in .env")
    keywords = [k.strip() for k in env.get("SEARCH_KEYWORDS", "").split(",") if k.strip()]
    grid = int(env.get("GRID_SIZE", "3"))
    out = env.get("OUTPUT_CSV", "places.csv")
    bounds = read_bounds(env.get("SEARCH_POLYGON_FILE", "boundary.txt"))

    seen, rows = set(), []
    for kw in keywords:
        for cell in grid_cells(*bounds, grid):
            for p in search(api_key, kw, cell):
                pid = p.get("id")
                if pid in seen:
                    continue
                seen.add(pid)
                loc = p.get("location", {})
                rows.append({
                    "keyword": kw,
                    "name": p.get("displayName", {}).get("text", ""),
                    "address": p.get("formattedAddress", ""),
                    "rating": p.get("rating", ""),
                    "rating_count": p.get("userRatingCount", ""),
                    "phone": p.get("nationalPhoneNumber", ""),
                    "lat": loc.get("latitude", ""),
                    "lng": loc.get("longitude", ""),
                    "maps_url": p.get("googleMapsUri", ""),
                })
            print(f"{kw}: cell done, unique so far {len(rows)}")

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} places to {out}")


if __name__ == "__main__":
    main()
