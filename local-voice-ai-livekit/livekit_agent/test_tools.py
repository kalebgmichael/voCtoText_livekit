"""
Quick smoke test for search_accommodations + screenshot_top_listings.
Runs against live local services (no LiveKit room needed).
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession as MCPClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(".env.local")

AIRBNB_URL = os.getenv("MCP_AIRBNB_URL", "http://localhost:8090/mcp")
PLAYWRIGHT_URL = os.getenv("MCP_PLAYWRIGHT_URL", "http://localhost:8091/mcp")


def _normalize_listing(raw: dict) -> dict:
    name = raw.get("demandStayListing", {}).get("description", {}).get("name", {}).get(
        "localizedStringWithTranslationPreference", ""
    ) or raw.get("name", "Unnamed listing")
    price = (
        raw.get("structuredDisplayPrice", {}).get("primaryLine", {}).get("accessibilityLabel", "") or ""
    )
    return {
        "id": raw.get("id", ""),
        "url": raw.get("url", ""),
        "name": name.strip(),
        "price": price.strip(),
        "rating": raw.get("avgRatingA11yLabel", "").strip(),
    }


async def test_search(location: str, min_price: int = 0, max_price: int = 0):
    print(f"\n=== search_accommodations: {location!r} min={min_price} max={max_price} ===")
    params: dict = {"location": location, "adults": 1}
    if min_price > 0:
        params["minPrice"] = min_price
    if max_price > 0:
        params["maxPrice"] = max_price

    async with (
        streamablehttp_client(AIRBNB_URL) as (read, write, _),
        MCPClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("airbnb_search", params)

    listings = []
    for content in result.content:
        if content.type == "text":
            data = json.loads(content.text)
            raw = data if isinstance(data, list) else data.get("searchResults", data.get("listings", []))
            listings = [_normalize_listing(r) for r in raw]
            break

    print(f"Found {len(listings)} listings")
    top3 = listings[:3]
    for i, l in enumerate(top3):
        print(f"  {i+1}. {l['name'][:60]} | {l['price']} | url={l['url'][:60]}")

    return [l["url"] for l in top3 if l.get("url")]


async def test_screenshot(urls: list[str]):
    print(f"\n=== screenshot_top_listings: {len(urls)} urls ===")
    async with (
        streamablehttp_client(PLAYWRIGHT_URL) as (read, write, _),
        MCPClientSession(read, write) as pw,
    ):
        await pw.initialize()
        for i, url in enumerate(urls[:3]):
            print(f"  Navigating to listing {i+1}...")
            await pw.call_tool("browser_navigate", {"url": url})
            result = await pw.call_tool("browser_screenshot", {})
            print(f"  Screenshot {i+1} raw content: {[(c.type, vars(c)) for c in result.content][:2]}")
            for content in result.content:
                if content.type == "image":
                    size_kb = len(content.data) * 3 // 4 // 1024
                    print(f"  Screenshot {i+1}: {size_kb}KB  mime={getattr(content,'mimeType','image/png')}  OK")
                    break
            else:
                print(f"  Screenshot {i+1}: no image content returned")


async def main():
    location = sys.argv[1] if len(sys.argv) > 1 else "Paris"
    min_price = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    max_price = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    urls = await test_search(location, min_price, max_price)

    if urls:
        await test_screenshot(urls)
    else:
        print("No URLs to screenshot.")


if __name__ == "__main__":
    asyncio.run(main())
