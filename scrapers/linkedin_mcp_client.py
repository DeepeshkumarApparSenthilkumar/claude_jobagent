"""
LinkedIn job scraper — uses a SINGLE persistent MCP session for all calls
to avoid repeated auth checks that trigger LinkedIn's bot detection.
"""
import sys
import os
import json
import re
import time
import random
import logging
import asyncio
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import init_db, add_job

logger = logging.getLogger(__name__)

UVX_PATH = r"C:\Users\dk505\.local\bin\uvx.exe"


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def extract_job_ids(result: dict) -> list[str]:
    if not result:
        return []
    ids = result.get("job_ids", [])
    if ids:
        return [str(jid) for jid in ids]
    # Fallback: parse from text
    text = ""
    sections = result.get("sections", {})
    if isinstance(sections, dict):
        text = " ".join(str(v) for v in sections.values())
    elif isinstance(sections, str):
        text = sections
    found = re.findall(r"/jobs/view/(\d{7,13})", text)
    return list(dict.fromkeys(found))


def parse_job_posting(text: str, job_id: str, url: str) -> dict:
    """
    Parse raw job_posting text. LinkedIn format is typically:
    Line 1: Company name
    Line 2: Job title
    Line 3: Location · Employment type · X applicants
    Line 4+: Description
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # LinkedIn raw text: company is line 0, title is line 1
    company = lines[0] if lines else "Unknown"
    title = lines[1] if len(lines) > 1 else "Unknown"

    # Skip location/metadata lines (they contain · or common location patterns)
    desc_start = 2
    for i, line in enumerate(lines[2:], start=2):
        if any(sep in line for sep in ["·", "ago", "applicants", "Full-time", "Part-time", "Contract", "Internship"]):
            desc_start = i + 1
        else:
            break

    description = "\n".join(lines[desc_start:]) if desc_start < len(lines) else "\n".join(lines[2:])

    # Sanity check: if title looks like a company/noise, swap
    noise_patterns = ["jobs via", "staffing", "hiring", "apply now"]
    if any(p in title.lower() for p in noise_patterns) and company and company != "Unknown":
        title, company = company, title

    return {
        "title": title or "Unknown",
        "company": company or "Unknown",
        "url": url,
        "description": description or text,
        "source": "linkedin",
    }


INTERN_KEYWORDS = ["intern", "internship", "co-op", "coop"]
USA_KEYWORDS = ["united states", "usa", "u.s.", "remote", "chicago", "new york",
                "san francisco", "seattle", "austin", "boston", "los angeles",
                "new york city", "nyc", "sf", "bay area", "nationwide"]
REJECT_LOCATION = ["india only", "canada only", "must be located in india",
                   "must be located in canada", "work authorization in india"]


def is_usa_job(description: str, title: str) -> bool:
    """Return True if job is in USA or remote (acceptable)."""
    text = (description + " " + title).lower()
    # Reject if explicitly non-USA
    if any(r in text for r in REJECT_LOCATION):
        return False
    # Accept if contains a USA location keyword
    if any(k in text for k in USA_KEYWORDS):
        return True
    # If no location info at all, accept (could be remote)
    return True


def is_intern_job(title: str, description: str) -> bool:
    """Return True if job is an internship."""
    text = (title + " " + description[:500]).lower()
    return any(k in text for k in INTERN_KEYWORDS)


async def scrape_with_session(session, titles: list, location: str, blacklist: set) -> int:
    """Run all searches using a single authenticated MCP session."""
    total_new = 0

    for title in titles:
        logger.info(f"LinkedIn MCP: searching '{title}' in '{location}'")
        is_intern_search = any(k in title.lower() for k in INTERN_KEYWORDS)

        search_args = {
            "keywords": title,
            "location": location,
            "easy_apply": True,
            "work_type": "remote",
            "max_pages": 2,
            "date_posted": "past_week",
        }
        if is_intern_search:
            search_args["experience_level"] = "internship"

        try:
            result = await session.call_tool("search_jobs", search_args)
            raw = None
            if result.content:
                for content in result.content:
                    if hasattr(content, "text"):
                        try:
                            raw = json.loads(content.text)
                        except json.JSONDecodeError:
                            raw = {"raw": content.text}
                        break
        except Exception as e:
            logger.error(f"  search_jobs failed for '{title}': {e}")
            time.sleep(random.uniform(3, 6))
            continue

        if not raw:
            logger.warning(f"  No result for '{title}'")
            time.sleep(random.uniform(3, 6))
            continue

        job_ids = extract_job_ids(raw)
        logger.info(f"  Found {len(job_ids)} job IDs for '{title}'")

        for job_id_li in job_ids[:15]:
            li_url = f"https://www.linkedin.com/jobs/view/{job_id_li}"

            try:
                detail_result = await session.call_tool("get_job_details", {"job_id": job_id_li})
                detail = None
                if detail_result.content:
                    for content in detail_result.content:
                        if hasattr(content, "text"):
                            try:
                                detail = json.loads(content.text)
                            except json.JSONDecodeError:
                                detail = {"raw": content.text}
                            break
            except Exception as e:
                logger.warning(f"  get_job_details failed for {job_id_li}: {e}")
                time.sleep(random.uniform(2, 4))
                continue

            if not detail:
                continue

            sections = detail.get("sections", {})
            actual_url = detail.get("url", li_url)

            if isinstance(sections, dict):
                raw_text = sections.get("job_posting", "") or "\n".join(str(v) for v in sections.values())
            else:
                raw_text = str(sections)

            if not raw_text.strip():
                continue

            job = parse_job_posting(raw_text, job_id_li, actual_url)

            if job["company"] in blacklist:
                logger.info(f"  Skipping blacklisted: {job['company']}")
                continue

            # USA filter
            if not is_usa_job(job["description"], job["title"]):
                logger.info(f"  Skipping non-USA job: {job['title']} @ {job['company']}")
                continue

            db_id = add_job(
                title=job["title"],
                company=job["company"],
                url=job["url"],
                source="linkedin",
                description=job["description"],
            )
            if db_id:
                total_new += 1
                logger.info(f"  Saved: [{db_id}] {job['title']} @ {job['company']}")
            else:
                logger.debug(f"  Duplicate: {job['url']}")

            time.sleep(random.uniform(2, 4))

        time.sleep(random.uniform(4, 8))

    return total_new


async def scrape_async() -> int:
    init_db()
    config = load_config()
    cfg = config["job_search"]
    titles = cfg["titles"]
    location = cfg["location"]
    blacklist = set(cfg.get("blacklist_companies", []))

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=UVX_PATH,
        args=["linkedin-scraper-mcp"],
        env={**os.environ, "PATH": os.environ.get("PATH", "") + r";C:\Users\dk505\.local\bin"},
    )

    logger.info("Starting single persistent LinkedIn MCP session...")
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info("MCP session initialized. Starting scrape...")
                total_new = await scrape_with_session(session, titles, location, blacklist)
    except Exception as e:
        logger.error(f"MCP session error: {e}")
        total_new = 0

    logger.info(f"LinkedIn scrape complete. New jobs: {total_new}")
    return total_new


def scrape() -> int:
    return asyncio.run(scrape_async())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = scrape()
    print(f"New LinkedIn jobs saved: {count}")
