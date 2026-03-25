import os
import sys
import logging
import yaml
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Setup logging before importing modules
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
today = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join(LOG_DIR, f"daily_{today}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

from db.tracker import init_db, get_qualified_jobs
from scrapers.indeed_scraper import scrape as indeed_scrape
from scrapers.linkedin_mcp_client import scrape as linkedin_scrape
from ai_engine.ats_analyzer import analyze_all
from ai_engine.resume_tailor import tailor
from ai_engine.cover_letter import generate
from automation.apply_bot import apply_batch
from scheduler.email_digest import send as send_digest
import anthropic


def load_config() -> dict:
    with open(os.path.join(os.path.dirname(__file__), "config.yaml")) as f:
        return yaml.safe_load(f)


def run():
    logger.info("=" * 60)
    logger.info(f"Job Agent starting — {datetime.now().isoformat()}")
    logger.info("=" * 60)

    config = load_config()
    cfg = config["job_search"]
    threshold = cfg.get("ats_score_threshold", 80)
    daily_limit = cfg.get("daily_application_limit", 10)
    errors = []

    # ── Step 1: Initialize DB ────────────────────────────────────────
    try:
        init_db()
        logger.info("[1/6] Database initialized.")
    except Exception as e:
        logger.error(f"DB init failed: {e}")
        errors.append(f"DB init: {e}")

    # ── Step 2: Scrape Indeed ────────────────────────────────────────
    logger.info("[2/6] Scraping Indeed...")
    try:
        indeed_count = indeed_scrape()
        logger.info(f"  Indeed: {indeed_count} new jobs saved.")
    except Exception as e:
        logger.error(f"Indeed scraper error: {e}")
        errors.append(f"Indeed: {e}")
        indeed_count = 0

    # ── Step 3: Scrape LinkedIn (MCP) ────────────────────────────────
    logger.info("[3/6] Scraping LinkedIn via MCP...")
    try:
        li_count = linkedin_scrape()
        logger.info(f"  LinkedIn: {li_count} new jobs saved.")
    except Exception as e:
        logger.error(f"LinkedIn scraper error: {e}")
        errors.append(f"LinkedIn: {e}")
        li_count = 0

    # ── Step 4: ATS Analysis ─────────────────────────────────────────
    logger.info("[4/6] Running ATS analysis...")
    try:
        ats_stats = analyze_all()
        logger.info(f"  ATS: {ats_stats}")
    except Exception as e:
        logger.error(f"ATS analyzer error: {e}")
        errors.append(f"ATS: {e}")
        ats_stats = {"analyzed": 0, "qualified": 0, "skipped": 0}

    # ── Step 5: Tailor + Apply ───────────────────────────────────────
    logger.info("[5/6] Tailoring resumes and applying...")
    qualified_jobs = get_qualified_jobs(threshold)
    qualified_jobs = qualified_jobs[:daily_limit]  # Enforce daily limit
    logger.info(f"  Qualified jobs to apply: {len(qualified_jobs)}")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    for job in qualified_jobs:
        try:
            logger.info(f"  Tailoring resume for job {job['id']}: {job['title']} @ {job['company']}")
            tailor(job, client=client)
        except Exception as e:
            logger.error(f"  Resume tailor failed for job {job['id']}: {e}")
            errors.append(f"Tailor job {job['id']}: {e}")

        try:
            logger.info(f"  Generating cover letter for job {job['id']}")
            generate(job, client=client)
        except Exception as e:
            logger.error(f"  Cover letter failed for job {job['id']}: {e}")
            errors.append(f"Cover letter job {job['id']}: {e}")

    # Apply batch
    try:
        apply_results = apply_batch(qualified_jobs)
        logger.info(f"  Apply results: {apply_results}")
    except Exception as e:
        logger.error(f"Apply bot error: {e}")
        errors.append(f"Apply bot: {e}")
        apply_results = {"applied": 0, "failed": 0}

    # ── Step 6: Email Digest ─────────────────────────────────────────
    logger.info("[6/6] Sending email digest...")
    try:
        send_digest(errors=errors)
    except Exception as e:
        logger.error(f"Email digest failed: {e}")

    # ── Summary ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("JOB AGENT RUN COMPLETE")
    logger.info(f"  Indeed new jobs:    {indeed_count}")
    logger.info(f"  LinkedIn new jobs:  {li_count}")
    logger.info(f"  ATS analyzed:       {ats_stats.get('analyzed', 0)}")
    logger.info(f"  Qualified (>={threshold}):   {ats_stats.get('qualified', 0)}")
    logger.info(f"  Applications sent:  {apply_results.get('applied', 0)}")
    logger.info(f"  Errors:             {len(errors)}")
    logger.info(f"  Log file:           {log_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
