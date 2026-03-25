import sys
import os
import time
import random
import logging
import yaml
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import init_db, add_job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def build_indeed_url(title: str, location: str, start: int = 0) -> str:
    params = {
        "q": title,
        "l": location,
        "sort": "date",
        "start": start,
    }
    return f"https://www.indeed.com/jobs?{urlencode(params)}"


def parse_job_cards(soup: BeautifulSoup, source_url: str) -> list[dict]:
    jobs = []
    cards = soup.find_all("div", class_=lambda c: c and "job_seen_beacon" in c)
    if not cards:
        cards = soup.find_all("div", attrs={"data-jk": True})

    for card in cards:
        try:
            title_el = card.find("h2", class_=lambda c: c and "jobTitle" in (c or ""))
            if not title_el:
                title_el = card.find("a", attrs={"data-jk": True})
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.find("span", attrs={"data-testid": "company-name"})
            if not company_el:
                company_el = card.find(class_=lambda c: c and "companyName" in (c or ""))
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            link_el = card.find("a", attrs={"data-jk": True}) or card.find("a", href=True)
            jk = card.get("data-jk") or (link_el.get("data-jk") if link_el else None)
            url = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""

            desc_el = card.find("div", class_=lambda c: c and "job-snippet" in (c or ""))
            description = desc_el.get_text(" ", strip=True) if desc_el else ""

            if title and company and url:
                jobs.append({
                    "title": title,
                    "company": company,
                    "url": url,
                    "description": description,
                    "source": "indeed",
                })
        except Exception as e:
            logger.warning(f"Error parsing card: {e}")

    return jobs


def scrape_title(title: str, location: str, pages: int = 2) -> list[dict]:
    all_jobs = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(pages):
        start = page * 10
        url = build_indeed_url(title, location, start)
        logger.info(f"Scraping Indeed: {title} | page {page + 1} | {url}")
        try:
            # Use a rotating user-agent and referrer to reduce 403s
            session.headers.update({
                "User-Agent": random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
                ]),
                "Referer": "https://www.google.com/",
                "Accept-Encoding": "gzip, deflate, br",
            })
            resp = session.get(url, timeout=15)
            if resp.status_code == 403:
                logger.warning(f"  Indeed returned 403 (bot protection) for: {title}. Skipping.")
                break
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            jobs = parse_job_cards(soup, url)
            logger.info(f"  Found {len(jobs)} jobs on page {page + 1}")
            all_jobs.extend(jobs)
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")

        delay = random.uniform(4, 8)
        logger.debug(f"  Sleeping {delay:.1f}s")
        time.sleep(delay)

    return all_jobs


def scrape() -> int:
    init_db()
    config = load_config()
    cfg = config["job_search"]
    titles = cfg["titles"]
    location = cfg["location"]
    blacklist = set(cfg.get("blacklist_companies", []))

    total_new = 0

    for title in titles:
        jobs = scrape_title(title, location)
        for job in jobs:
            if job["company"] in blacklist:
                logger.info(f"Skipping blacklisted company: {job['company']}")
                continue
            job_id = add_job(
                title=job["title"],
                company=job["company"],
                url=job["url"],
                source=job["source"],
                description=job["description"],
            )
            if job_id:
                total_new += 1
                logger.info(f"  Saved: [{job_id}] {job['title']} @ {job['company']}")
            else:
                logger.debug(f"  Duplicate: {job['url']}")

        delay = random.uniform(3, 6)
        time.sleep(delay)

    logger.info(f"Indeed scrape complete. New jobs saved: {total_new}")
    return total_new


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = scrape()
    print(f"New jobs found: {count}")
