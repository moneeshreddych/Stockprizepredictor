import os
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

BATCH_SIZE = 100
REQUEST_TIMEOUT = 15
DELAY_SECONDS = 0.25


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return

        values = {key.lower(): value for key, value in attrs}
        name = (values.get("property") or values.get("name") or "").lower()
        content = values.get("content")

        if not content:
            return

        if name in {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }:
            self.images.append(content.strip())


session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139 Safari/537.36"
    }
)


def extract_image_url(article_url):
    try:
        response = session.get(
            article_url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        parser = ImageParser()
        parser.feed(response.text[:1_500_000])

        for image in parser.images:
            image_url = urljoin(response.url, image)
            if image_url.startswith(("http://", "https://")):
                return image_url

    except requests.RequestException as error:
        print(f"FETCH FAILED: {article_url} | {error}")
    except Exception as error:
        print(f"PARSE FAILED: {article_url} | {error}")

    return None


def load_null_image_rows():
    rows = []
    start = 0

    while True:
        response = (
            supabase.table("news_articles")
            .select("url,title")
            .is_("image_url", "null")
            .not_.is_("url", "null")
            .order("published_at", desc=True)
            .range(start, start + BATCH_SIZE - 1)
            .execute()
        )
        

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < BATCH_SIZE:
            break

        start += BATCH_SIZE

    return rows


def update_image(article_url, image_url):
    supabase.table("news_articles").update(
        {"image_url": image_url}
    ).eq("url", article_url).is_("image_url", "null").execute()


def main():
    rows = load_null_image_rows()

    print(f"Articles with NULL image_url: {len(rows)}")

    updated = 0
    failed = 0

    for index, row in enumerate(rows, start=1):
        article_url = row.get("url")
        title = row.get("title") or "Untitled"

        safe_title = title[:90].encode("ascii", errors="replace").decode("ascii")
        print(f"[{index}/{len(rows)}] {safe_title}")

        image_url = extract_image_url(article_url)

        if image_url:
            update_image(article_url, image_url)
            updated += 1
            print(f"  IMAGE: {image_url}")
        else:
            failed += 1
            print("  IMAGE: not found")

        time.sleep(DELAY_SECONDS)

    print("\nIMAGE BACKFILL COMPLETE")
    print(f"Updated: {updated}")
    print(f"Not found/blocked: {failed}")


if __name__ == "__main__":
    main()
