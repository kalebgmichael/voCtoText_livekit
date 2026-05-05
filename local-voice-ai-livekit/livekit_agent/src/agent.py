import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.agents.llm.mcp import MCPServerHTTP
from livekit.plugins import openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from mcp import ClientSession as MCPClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(".env.local")

_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice-agent")

# MCP_*_URL vars in this set are called manually inside function_tools, not auto-registered
# as AgentSession mcp_servers. This prevents duplicate tool definitions and keeps browser
# sessions isolated to get_listing_details (Playwright SSE) and search/details calls (Airbnb).
_FUNCTION_TOOL_MCP_KEYS = {"MCP_AIRBNB_URL", "MCP_PLAYWRIGHT_URL"}


def _normalize_listing(raw: dict) -> dict:
    """Flatten the deeply-nested airbnb_search result into a simple dict."""
    name = raw.get("demandStayListing", {}).get("description", {}).get("name", {}).get(
        "localizedStringWithTranslationPreference", ""
    ) or raw.get("name", "Unnamed listing")
    price = (
        raw.get("structuredDisplayPrice", {})
        .get("primaryLine", {})
        .get("accessibilityLabel", "")
        or ""
    )
    price_detail = (
        raw.get("structuredDisplayPrice", {})
        .get("explanationData", {})
        .get("priceDetails", "")
        or ""
    )
    return {
        "id": raw.get("id", ""),
        "url": raw.get("url", ""),
        "name": name.strip(),
        "price": price.strip(),
        "priceDetail": price_detail.strip(),
        "rating": raw.get("avgRatingA11yLabel", "").strip(),
        "badge": raw.get("badges", "").strip(),
    }



# Known site aliases — add entries here to support opening by name
_SITE_ALIASES: dict[str, str] = {
    "roc": "https://net.labtlclivorno.it/",
}


def _build_instructions() -> str:
    base = (
        "You are a helpful voice AI assistant in a real-time voice call. "
        "Your output will be converted to audio so you must never include "
        "emojis, asterisks, markdown formatting, bullet points, or any "
        "special characters in your responses. "
        "Keep your responses concise and conversational, ideally under "
        "3 sentences unless the user asks for detail. "
        "You are curious, friendly, and have a sense of humor. "
        "Your name is livROC. When someone greets you by name — for example 'hey livroc', "
        "'hi livroc', 'livroc', or any variation — respond naturally as if you were just listening, "
        "starting with a filler like 'Ehmm...' then follow with 'what can I help you with?' "
        "Sound natural and attentive, not robotic. Do not repeat your full introduction. "
        "When you perform any action, always start your reply with 'Roger that,' followed by "
        "a brief description of what you are doing, for example: 'Roger that, opening that for you now.' "
        "When a user asks about accommodation, rooms, or places to stay "
        "in a city, ask for their minimum and maximum price per night and "
        "number of guests before calling search_accommodations. If they "
        "say no limit or skip it, use 0 for both. "
        "After search_accommodations returns, immediately call "
        "open_listing_in_browser for each of the top 3 listing URLs "
        "so they open in the user's browser. "
        "When the user says any of the following — open, visit, go to, navigate to, "
        "take me to, show me, load, pull up, launch — followed by a URL or site name, "
        "you MUST call open_url_in_browser immediately with no clarification questions. "
        "If the user gives a URL without a protocol (e.g. 'google.com'), pass it as-is; "
        "the tool normalises it. Never say you need a URL. Just call the tool. "
    )
    if _SITE_ALIASES:
        alias_lines = "; ".join(
            f'"{name}" → {url}' for name, url in _SITE_ALIASES.items()
        )
        base += (
            f"You know these named sites: {alias_lines}. "
            "Any phrase that includes one of these names — 'open roc', 'go to roc', "
            "'show me roc', or just the bare name 'roc' — MUST trigger open_url_in_browser "
            "with the mapped URL. Never ask what the name means. "
        )
    return base


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                _build_instructions()
                + "When the user asks for more details, more information, or wants "
                "to know about the listings, call get_listing_details with the "
                "top 3 listing URLs from the last search. "
                "When the user asks to take a screenshot and says listing 1, 2, "
                "or 3, call take_screenshot with the corresponding URL from the "
                "last search (listing 1 = first URL, listing 2 = second URL, "
                "listing 3 = third URL). If no listing number is given, use "
                "the first URL. Do not take a screenshot when the user only "
                "asks for details or information."
            ),
        )

    @function_tool()
    async def search_accommodations(
        self,
        context: RunContext,
        location: str,
        checkin: str = "",
        checkout: str = "",
        adults: int = 1,
        min_price: int = 0,
        max_price: int = 0,
    ) -> str:
        """Search Airbnb for accommodations and display results on screen.

        Args:
            location: City or location to search in.
            checkin: Check-in date in YYYY-MM-DD format (optional).
            checkout: Check-out date in YYYY-MM-DD format (optional).
            adults: Number of adults (default 1).
            min_price: Minimum price per night in USD (0 = no minimum).
            max_price: Maximum price per night in USD (0 = no maximum).
        """
        await context.session.say(
            f"Searching for places in {location}, give me a moment.",
            allow_interruptions=False,
        )

        mcp_url = os.getenv("MCP_AIRBNB_URL", "http://mcp_airbnb:8080/mcp")
        listings: list = []

        logger.info(
            "[tool:search_accommodations] START location=%r adults=%d checkin=%r checkout=%r min_price=%d max_price=%d mcp_url=%s",
            location,
            adults,
            checkin or "none",
            checkout or "none",
            min_price,
            max_price,
            mcp_url,
        )
        t0 = time.perf_counter()

        try:
            params: dict = {"location": location, "adults": adults}
            if checkin:
                params["checkin"] = checkin
            if checkout:
                params["checkout"] = checkout
            if min_price > 0:
                params["minPrice"] = min_price
            if max_price > 0:
                params["maxPrice"] = max_price

            logger.debug("[tool:search_accommodations] MCP params=%s", params)

            t_mcp = time.perf_counter()
            async with (
                streamablehttp_client(mcp_url) as (read, write, _),
                MCPClientSession(read, write) as mcp_session,
            ):
                logger.debug("[tool:search_accommodations] MCP session initialized")
                await mcp_session.initialize()
                result = await mcp_session.call_tool("airbnb_search", params)
            mcp_ms = int((time.perf_counter() - t_mcp) * 1000)

            logger.info(
                "[tool:search_accommodations] MCP call done in %dms — isError=%s content_items=%d",
                mcp_ms,
                result.isError,
                len(result.content),
            )

            for content in result.content:
                logger.debug(
                    "[tool:search_accommodations] content type=%s size=%d chars",
                    content.type,
                    len(getattr(content, "text", "") or ""),
                )
                if content.type == "text":
                    try:
                        data = json.loads(content.text)
                        raw = (
                            data
                            if isinstance(data, list)
                            else data.get("searchResults", data.get("listings", []))
                        )
                        listings = [_normalize_listing(r) for r in raw]
                        logger.info(
                            "[tool:search_accommodations] parsed %d raw → %d normalized listings",
                            len(raw),
                            len(listings),
                        )
                    except (json.JSONDecodeError, AttributeError) as parse_err:
                        logger.warning(
                            "[tool:search_accommodations] JSON parse failed: %s",
                            parse_err,
                        )

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "[tool:search_accommodations] FAILED after %dms — %s: %s",
                elapsed_ms,
                type(exc).__name__,
                exc,
            )
            return "Could not fetch listings right now, please try again."

        # Publish to LiveKit data channel so the frontend panel updates.
        t_pub = time.perf_counter()
        room = context.session.room_io.room
        payload = json.dumps({"listings": listings[:10]})
        await room.local_participant.publish_data(
            payload,
            topic="listings",
            reliable=True,
        )
        logger.info(
            "[tool:search_accommodations] published %d listings to data channel in %dms (payload %d bytes)",
            min(len(listings), 10),
            int((time.perf_counter() - t_pub) * 1000),
            len(payload),
        )
        total_ms = int((time.perf_counter() - t0) * 1000)

        if not listings:
            logger.info(
                "[tool:search_accommodations] END no results total=%dms", total_ms
            )
            return f"No listings found in {location}."

        # Log each listing at DEBUG so you can inspect without noise at INFO.
        for i, listing in enumerate(listings[:10]):
            logger.debug(
                "[tool:search_accommodations] listing[%d] name=%r price=%r rating=%r thumbnail=%s url=%s",
                i,
                listing.get("name"),
                listing.get("price"),
                listing.get("rating"),
                "yes" if listing.get("thumbnail") else "no",
                listing.get("url"),
            )

        logger.info(
            "[tool:search_accommodations] END total=%dms listings=%d location=%r",
            total_ms,
            len(listings),
            location,
        )

        top3 = listings[:3]
        spoken = ". ".join(
            "{n}. {name}, {price}".format(
                n=i + 1,
                name=listing.get("name", "a listing"),
                price=listing.get("price", "price unknown"),
            )
            + (
                ", rated " + listing["rating"].split(" out")[0]
                if listing.get("rating")
                else ""
            )
            for i, listing in enumerate(top3)
        )
        top3_urls = [listing["url"] for listing in top3 if listing.get("url")]
        return (
            f"Found {len(listings)} places in {location}. "
            f"Top 3: {spoken}. All results shown on screen. "
            f"Top 3 listing URLs (use these if user asks for more details): {top3_urls}"
        )

    @function_tool()
    async def get_listing_details(
        self,
        context: RunContext,
        urls: list[str],
    ) -> str:
        """Get detailed info and screenshots of Airbnb listings when the user asks for more details.

        Args:
            urls: List of Airbnb listing URLs to get details for (max 3).
        """
        await context.session.say(
            "Pulling up the details and screenshots for those listings, this may take a few seconds.",
            allow_interruptions=False,
        )

        mcp_airbnb_url = os.getenv("MCP_AIRBNB_URL", "http://mcp_airbnb:8080/mcp")
        playwright_url = os.getenv("MCP_PLAYWRIGHT_URL", "http://mcp_playwright:8080/mcp")
        room = context.session.room_io.room
        urls = urls[:3]

        logger.info("[tool:get_listing_details] START urls=%d", len(urls))
        t0 = time.perf_counter()
        details: list[str] = []

        # --- Step 1: structured data via Airbnb MCP (fast, no browser) ---
        try:
            async with (
                streamablehttp_client(mcp_airbnb_url) as (read, write, _),
                MCPClientSession(read, write) as mcp_session,
            ):
                await mcp_session.initialize()
                for i, url in enumerate(urls):
                    try:
                        listing_id = url.split("/rooms/")[1].split("?")[0].strip("/")
                        logger.info(
                            "[tool:get_listing_details] airbnb id=%s (%d/%d)",
                            listing_id, i + 1, len(urls),
                        )
                        result = await mcp_session.call_tool(
                            "airbnb_listing_details",
                            {"id": listing_id, "ignoreRobotsText": True},
                        )
                        for content in result.content:
                            if content.type == "text":
                                details.append(f"Listing {i + 1} ({url}):\n{content.text[:2000]}")
                                break
                    except Exception as exc:
                        logger.warning("[tool:get_listing_details] airbnb failed url=%s: %s", url, exc)
        except Exception as exc:
            logger.error("[tool:get_listing_details] airbnb MCP error: %s", exc)

        # Signal frontend to clear previous detail screenshots before new batch arrives.
        try:
            await room.local_participant.publish_data(
                b"{}", topic="listing_screenshot_clear", reliable=True
            )
        except Exception:
            pass

        # --- Step 2: screenshots via Playwright (one stateless call per URL) ---
        for i, url in enumerate(urls):
            try:
                js = (
                    "async (page) => {"
                    "  await page.setViewportSize({ width: 1024, height: 768 });"
                    f"  await page.goto({json.dumps(url)}, {{ waitUntil: 'domcontentloaded', timeout: 20000 }});"
                    "  const buf = await page.screenshot({ type: 'jpeg' });"
                    "  return buf.toString('base64');"
                    "}"
                )
                async with (
                    streamablehttp_client(playwright_url) as (read, write, _),
                    MCPClientSession(read, write) as pw,
                ):
                    await pw.initialize()
                    shot = await pw.call_tool("browser_run_code", {"code": js})

                b64 = None
                for content in shot.content:
                    if content.type == "text" and not shot.isError:
                        b64 = content.text.strip()
                        break

                if b64:
                    payload = json.dumps({"url": url, "screenshot": b64, "mimeType": "image/jpeg"})
                    await room.local_participant.publish_data(
                        payload, topic="listing_screenshot", reliable=True
                    )
                    logger.info("[tool:get_listing_details] screenshot %d/%d sent size=%d", i + 1, len(urls), len(payload))
                else:
                    logger.warning("[tool:get_listing_details] screenshot %d/%d empty or error", i + 1, len(urls))
            except Exception as exc:
                logger.warning("[tool:get_listing_details] playwright failed url=%s: %s", url, exc)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info("[tool:get_listing_details] END elapsed=%dms details=%d", elapsed_ms, len(details))

        if not details:
            return "Could not retrieve listing details. Describe each listing using the name, price, and rating from the search results."

        return (
            "Listing details below. Screenshots are being shown on screen. "
            "For each listing give 2 to 3 spoken sentences covering "
            "name, price, room type, key amenities, and rating. Keep it conversational.\n\n"
            + "\n\n".join(details)
        )

    @function_tool()
    async def open_listing_in_browser(
        self,
        context: RunContext,
        url: str,
    ) -> str:
        """Open an Airbnb listing URL directly in the user's browser tab.

        Args:
            url: The full Airbnb listing URL to open.
        """
        logger.info("[tool:open_listing_in_browser] url=%s", url)

        room = context.session.room_io.room
        payload = json.dumps({"url": url})
        t0 = time.perf_counter()
        await room.local_participant.publish_data(
            payload,
            topic="open_url",
            reliable=True,
        )
        logger.info(
            "[tool:open_listing_in_browser] published open_url in %dms",
            int((time.perf_counter() - t0) * 1000),
        )
        return "Opening that listing in your browser now."

    @function_tool()
    async def open_url_in_browser(
        self,
        context: RunContext,
        url: str,
    ) -> str:
        """Open any URL or named site in a new browser tab.

        Call this whenever the user says open, visit, go to, navigate to, take me to,
        show me, load, pull up, or launch followed by a URL or site name.
        Also call it when the user says just a known site name (e.g. "roc").
        Do NOT ask for clarification — call the tool immediately.

        Args:
            url: Full URL (https://example.com), bare domain (example.com),
                 or a known site alias (e.g. "roc"). Aliases and protocol are
                 resolved automatically.
        """
        resolved = _SITE_ALIASES.get(url.strip().lower())
        if resolved:
            url = resolved
        elif not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        logger.info("[tool:open_url_in_browser] url=%s", url)
        room = context.session.room_io.room

        # Immediate verbal feedback + tab open — both happen before any slow I/O
        await context.session.say("Roger that, opening that for you now.", allow_interruptions=False)
        await room.local_participant.publish_data(
            json.dumps({"url": url}), topic="open_url", reliable=True
        )

        # Playwright navigation runs headless in background — no screenshot needed here,
        # so don't block the tool return on it.
        playwright_url = os.getenv("MCP_PLAYWRIGHT_URL", "http://mcp_playwright:8080/mcp")

        async def _navigate_bg() -> None:
            js = (
                "async (page) => {"
                "  await page.setViewportSize({ width: 1280, height: 800 });"
                f"  await page.goto({json.dumps(url)}, {{ waitUntil: 'domcontentloaded', timeout: 20000 }});"
                "  return 'ok';"
                "}"
            )
            try:
                async with (
                    streamablehttp_client(playwright_url) as (read, write, _),
                    MCPClientSession(read, write) as pw,
                ):
                    await pw.initialize()
                    await pw.call_tool("browser_run_code", {"code": js})
                logger.info("[tool:open_url_in_browser] playwright bg navigation done url=%s", url)
            except Exception as exc:
                logger.warning("[tool:open_url_in_browser] playwright bg failed: %s", exc)

        asyncio.create_task(_navigate_bg())

        return f"Opened {url} in your browser."

    @function_tool()
    async def take_screenshot(
        self,
        context: RunContext,
        url: str,
    ) -> str:
        """Take a screenshot of any URL and display it in the chat.

        Args:
            url: The full URL of the webpage to screenshot.
        """
        playwright_url = os.getenv("MCP_PLAYWRIGHT_URL", "http://mcp_playwright:8080/mcp")
        room = context.session.room_io.room

        await context.session.say(
            "Taking a screenshot now, one moment please.",
            allow_interruptions=False,
        )

        logger.info("[tool:take_screenshot] url=%s", url)
        t0 = time.perf_counter()

        js = (
            "async (page) => {"
            "  await page.setViewportSize({ width: 1280, height: 800 });"
            f"  await page.goto({json.dumps(url)}, {{ waitUntil: 'domcontentloaded', timeout: 20000 }});"
            "  const buf = await page.screenshot({ type: 'jpeg' });"
            "  return buf.toString('base64');"
            "}"
        )

        try:
            async with (
                streamablehttp_client(playwright_url) as (read, write, _),
                MCPClientSession(read, write) as pw,
            ):
                await pw.initialize()
                shot = await pw.call_tool("browser_run_code", {"code": js})

            b64 = None
            for content in shot.content:
                if content.type == "text" and not shot.isError:
                    b64 = content.text.strip()
                    break

            if b64:
                payload = json.dumps({"url": url, "screenshot": b64, "mimeType": "image/jpeg"})
                await room.local_participant.publish_data(payload, topic="screenshot", reliable=True)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.info("[tool:take_screenshot] done in %dms size=%d bytes", elapsed_ms, len(payload))
                return f"Screenshot of {url} is now shown on screen."
            else:
                logger.warning("[tool:take_screenshot] empty result isError=%s", shot.isError)
                return f"Could not capture screenshot of {url}."
        except Exception as exc:
            logger.error("[tool:take_screenshot] failed: %s", exc)
            return f"Could not take a screenshot of {url}. Please try again."


server = AgentServer(
    num_idle_processes=0,
    initialize_process_timeout=60.0,
)


def prewarm(proc: JobProcess):
    logger.info("[prewarm] loading VAD model")
    t0 = time.perf_counter()
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("[prewarm] VAD loaded in %dms", int((time.perf_counter() - t0) * 1000))


server.setup_fnc = prewarm


def _build_mcp_servers() -> list[MCPServerHTTP]:
    servers = []
    for key, value in os.environ.items():
        if (
            key.startswith("MCP_")
            and key.endswith("_URL")
            and value
            and key not in _FUNCTION_TOOL_MCP_KEYS
        ):
            logger.info("[mcp] registering AgentSession server %s → %s", key, value)
            servers.append(MCPServerHTTP(url=value))
    if not servers:
        logger.info(
            "[mcp] no extra MCP servers registered via env (airbnb+playwright handled as function_tools)"
        )
    return servers


@server.rtc_session()
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    llama_model = os.getenv("LLAMA_MODEL", "gemma4:e4b")
    llama_base_url = os.getenv("LLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    stt_base_url = os.getenv("STT_BASE_URL", "http://whisper:80/v1")
    stt_model = os.getenv("STT_MODEL", "Systran/faster-whisper-small")
    stt_api_key = os.getenv("STT_API_KEY", "no-key-needed")
    tts_base_url = os.getenv("TTS_BASE_URL", "http://kokoro:8880/v1")
    tts_voice = os.getenv("TTS_VOICE", "af_nova")

    mcp_servers = _build_mcp_servers()

    logger.info(
        "[session] config — LLM=%s STT=%s TTS=%s voice=%s extra_mcp=%d",
        llama_model,
        stt_model,
        tts_base_url,
        tts_voice,
        len(mcp_servers),
    )

    session = AgentSession(
        stt=openai.STT(
            base_url=stt_base_url,
            model=stt_model,
            api_key=stt_api_key,
        ),
        llm=openai.LLM(
            base_url=llama_base_url,
            model=llama_model,
            api_key="no-key-needed",
            timeout=300.0,
            temperature=0.7,
        ),
        tts=openai.TTS(
            base_url=tts_base_url,
            model="kokoro",
            voice=tts_voice,
            api_key="no-key-needed",
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.5,
        mcp_servers=mcp_servers,
    )

    logger.info("[session] connecting to room=%s", ctx.room.name)
    await ctx.connect()

    # Session-level keepalive: prevents WebRTC publisher connection timeout during
    # long LLM generation and tool calls (can exceed 30s with local model).
    # Runs for the entire session duration and cleans itself up on disconnect.
    async def _session_keepalive() -> None:
        while True:
            try:
                await ctx.room.local_participant.publish_data(b"{}", topic="keepalive", reliable=False)
            except Exception:
                pass
            await asyncio.sleep(5)

    asyncio.create_task(_session_keepalive())

    logger.info("[session] connected — starting agent")
    await session.start(agent=Assistant(), room=ctx.room)
    logger.info("[session] agent started and ready")
    await session.say("Hey, I am livROC, a live voice agent for the Remote Operation Center in Livorno. How can I help you today?")


if __name__ == "__main__":
    cli.run_app(server)
