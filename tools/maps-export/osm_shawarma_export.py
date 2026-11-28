#!/usr/bin/env python3
"""Export shawarma places from OpenStreetMap (Overpass API) inside a bounding box.

No API key or billing needed. Reads the area from boundary.txt (lat,lng corners),
searches names and cuisine tags, and writes a CSV. Standard library only.
"""
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request

DEFAULT_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TERMS = "شاورما|شاورمة|شوارما|shawarma|shawerma"


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


def read_bbox(path):
    """Return (south, west, north, east) from a file of lat,lng lines."""
    lats, lngs = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lat, lng = (float(x) for x in line.split(",")[:2])
                lats.append(lat)
                lngs.append(lng)
    return min(lats), min(lngs), max(lats), max(lngs)


def build_query(bbox, terms):
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    # Regex is case-insensitive (the trailing ,i). Filter by name OR by cuisine tag.
    return f"""[out:json][timeout:90];
(
  node["amenity"~"restaurant|fast_food|cafe"]["name"~"{terms}",i]{box};
  way["amenity"~"restaurant|fast_food|cafe"]["name"~"{terms}",i]{box};
  node["amenity"~"restaurant|fast_food"]["cuisine"~"shawarma|shawerma",i]{box};
  way["amenity"~"restaurant|fast_food"]["cuisine"~"shawarma|shawerma",i]{box};
);
out center tags;"""


def fetch(url, query):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"User-Agent": "maps-export-script/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def to_rows(elements):
    rows, seen = [], set()
    for el in elements:
        key = (el.get("type"), el.get("id"))
        if key in seen:
            continue
        seen.add(key)
        tags = el.get("tags", {})
        center = el.get("center", {})
        lat = el.get("lat", center.get("lat", ""))
        lng = el.get("lon", center.get("lon", ""))
        rows.append({
            "name": tags.get("name", ""),
            "name_en": tags.get("name:en", ""),
            "amenity": tags.get("amenity", ""),
            "cuisine": tags.get("cuisine", ""),
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "opening_hours": tags.get("opening_hours", ""),
            "street": tags.get("addr:street", ""),
            "city": tags.get("addr:city", ""),
            "lat": lat,
            "lng": lng,
            "osm_url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        })
    rows.sort(key=lambda r: r["name"])
    return rows


def main():
    env = load_env()
    url = env.get("OVERPASS_URL", DEFAULT_URL)
    terms = env.get("SHAWARMA_TERMS", DEFAULT_TERMS)
    out = env.get("OUTPUT_CSV", "shawarma-osm.csv")
    bbox_file = env.get("SEARCH_POLYGON_FILE", "boundary.txt")

    if not os.path.exists(bbox_file):
        sys.exit(f"Missing {bbox_file}")
    bbox = read_bbox(bbox_file)
    query = build_query(bbox, terms)

    try:
        result = fetch(url, query)
    except Exception as err:  # network, timeout or HTTP error
        sys.exit(f"Overpass request failed: {err}")

    rows = to_rows(result.get("elements", []))
    fields = ["name", "name_en", "amenity", "cuisine", "phone", "website",
              "opening_hours", "street", "city", "lat", "lng", "osm_url"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} places to {out}")
    if not rows:
        print("No matches. Try a larger or different area, or add spellings to SHAWARMA_TERMS.")


if __name__ == "__main__":
    main()
