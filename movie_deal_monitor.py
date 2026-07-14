import json
import os
import time
import requests
from datetime import date, timedelta
from pathlib import Path

PUSHOVER_TOKEN = os.environ['PUSHOVER_TOKEN']
PUSHOVER_USER  = os.environ['PUSHOVER_USER']

SCRIPT_DIR = Path(__file__).parent
SEEN_FILE  = SCRIPT_DIR / "seen_deals.json"

PRICE_THRESHOLD = 12.00

MOVIES = [
    "Good Will Hunting",
    "Gladiator",
    "Up",
    "Batman Begins",
    "The Matrix",
    "Inception",
    "Toy Story",
    "Forrest Gump",
    "The Last Samurai",
    "Iron Man",
    "The Dark Knight",
    "300",
    "Cast Away",
    "Interstellar",
    "The King's Speech",
    "Spirited Away",
    "The Dark Knight Rises",
    "Unbreakable",
    "The Imitation Game",
    "The Prince of Egypt",
    "Sicario",
    "No Country for Old Men",
    "Moneyball",
    "The Princess Bride",
    "Shutter Island",
    "The Bourne Identity",
    "Ocean's Eleven",
    "Elf",
    "Anchorman",
    "Home Alone",
    "The Departed",
    "Memento",
    "The Incredibles",
    "Dead Poets Society",
    "School of Rock",
    "Sleepless in Seattle",
    "Catch Me If You Can",
    "Zombieland",
    "The Emperor's New Groove",
]

JW_QUERY = """
query SearchMovie($query: String!) {
  searchTitles(
    country: US, language: "en", first: 1, source: "justwatch",
    filter: { searchQuery: $query, objectTypes: [MOVIE] }
  ) {
    edges { node {
      offers(country: US, platform: WEB) {
        monetizationType retailPrice(language: "en") presentationType
        package { clearName }
      }
    } }
  }
}
"""


def parse_price(raw):
    if raw is None:
        return None
    try:
        return float(str(raw).lstrip("$"))
    except (ValueError, TypeError):
        return None


def amazon_deals(title):
    resp = requests.post(
        "https://apis.justwatch.com/graphql",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
        json={"query": JW_QUERY, "variables": {"query": title}},
        timeout=15,
    )
    resp.raise_for_status()
    edges = resp.json().get("data", {}).get("searchTitles", {}).get("edges", [])
    if not edges:
        return []

    best = None
    for offer in edges[0]["node"]["offers"]:
        if offer["monetizationType"] != "BUY":
            continue
        if offer["package"]["clearName"] != "Amazon Video":
            continue
        if offer["presentationType"] not in ("HD", "_4K", "SD"):
            continue
        if offer["presentationType"] == "SD" and title != "The King's Speech":
            continue
        price = parse_price(offer.get("retailPrice"))
        if price is None or price >= PRICE_THRESHOLD:
            continue
        if best is None or price < best:
            best = price
    return [("Amazon", best)] if best is not None else []


def itunes_deals(title):
    resp = requests.get(
        "https://itunes.apple.com/search",
        params={"term": title, "entity": "movie", "country": "us", "limit": 5},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    # Find best title match
    title_lower = title.lower()
    match = None
    for r in results:
        if r.get("wrapperType") != "track":
            continue
        if title_lower in r.get("trackName", "").lower():
            match = r
            break
    if not match and results:
        match = results[0]
    if not match:
        return []

    hd_price = parse_price(match.get("trackHdPrice"))
    if hd_price is not None and hd_price < PRICE_THRESHOLD:
        return [("iTunes", hd_price)]
    return []


def load_seen():
    if not SEEN_FILE.exists():
        return {}
    data = json.loads(SEEN_FILE.read_text())
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    return {k: v for k, v in data.items() if v >= cutoff}


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(seen, indent=2))


def send_pushover(title, message):
    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_TOKEN,
            "user":  PUSHOVER_USER,
            "title": title,
            "message": message,
            "sound": "cashregister",
        }, timeout=10)
        print(f"  Pushover: {r.status_code}")
    except Exception as e:
        print(f"  Pushover error: {e}")


def main():
    seen = load_seen()
    today = date.today().isoformat()
    new_deals = 0

    new_alerts = []

    for movie in MOVIES:
        try:
            deals = amazon_deals(movie) + itunes_deals(movie)
            for store, price in deals:
                key = f"{movie}|{store}"
                if key not in seen:
                    new_alerts.append((movie, store, price))
                    seen[key] = today
                    new_deals += 1
                    print(f"  Deal: {movie} — ${price:.2f} on {store}")
            time.sleep(0.5)
        except Exception as e:
            print(f"  Error ({movie}): {e}")

    if new_alerts:
        lines = [f"{movie} — ${price:.2f} on {store}" for movie, store, price in new_alerts]
        send_pushover(
            f"🎬 {len(new_alerts)} Movie Deal{'s' if len(new_alerts) > 1 else ''}",
            "\n".join(lines),
        )

    save_seen(seen)
    print(f"Done. {new_deals} new deal(s) found.")


if __name__ == "__main__":
    main()
