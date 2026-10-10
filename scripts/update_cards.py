"""Refresh static learning cards from a public RSS feed. No API key required.

News titles are quoted verbatim. Chinese concept explanations are curated,
not generated summaries of articles. Only allowlisted publisher paths are used.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FEED = "https://huggingface.co/blog/feed.xml"
PUBLISHERS = {"allenai", "nvidia", "microsoft", "LiquidAI", "tiiuae", "ServiceNow-AI"}


def build_cards(xml, concepts, now):
    items = []
    seen = set()
    for item in ET.fromstring(xml).findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        url = urlparse(link)
        parts = url.path.strip("/").split("/")
        if url.scheme != "https" or url.netloc != "huggingface.co" or not parts or parts[0] != "blog":
            continue
        if len(parts) != 2 and not (len(parts) == 3 and parts[1] in PUBLISHERS):
            continue
        if not title or link in seen:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
        if published > now or (now - published).days > 45:
            continue
        seen.add(link)
        items.append((published, title, link, parts))
    items.sort(key=lambda x: x[0], reverse=True)
    result, used = [], set()
    for published, title, link, parts in items:
        concept = next((c for c in concepts if c["id"] not in used and any(k in title.lower() for k in c["keywords"])), None)
        if not concept:
            continue
        used.add(concept["id"])
        card = {k: v for k, v in concept.items() if k != "keywords"}
        card.update(id=hashlib.sha256(link.encode()).hexdigest()[:16],
                    newsTitle=title, publishedAt=published.isoformat(), sourceUrl=link,
                    sourceName="Hugging Face" if len(parts) == 2 else parts[1] + " · Hugging Face")
        result.append(card)
        if len(result) == 5:
            break
    for concept in concepts:
        if len(result) == 5:
            break
        if concept["id"] not in used:
            result.append({k: v for k, v in concept.items() if k != "keywords"})
    return result


def main():
    concepts = json.loads((ROOT / "data/concepts.json").read_text())
    target = ROOT / "data/cards.json"
    try:
        request = Request(FEED, headers={"User-Agent": "Naiwa-AI-Daily/1.0"})
        with urlopen(request, timeout=30) as response:
            xml = response.read(3_000_001)
        if len(xml) > 3_000_000:
            raise ValueError("RSS exceeds size limit")
        now = datetime.now(timezone.utc)
        cards = build_cards(xml, concepts, now)
        if not any("newsTitle" in c for c in cards):
            raise ValueError("No usable recent news; retaining previous edition")
        payload = {"fetchedAt": now.isoformat(), "cards": cards}
    except Exception as error:
        print("Update failed; existing cards preserved:", error, file=sys.stderr)
        return 1
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print("Updated 5 cards;", sum("newsTitle" in c for c in cards), "linked to recent articles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
