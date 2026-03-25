import sys
import os
import time
import random
import logging
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import mark_applied, mark_failed

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

LINKEDIN_EMAIL = os.environ.get("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.environ.get("LINKEDIN_PASSWORD", "")
PROFILE_DIR = r"C:\Users\dk505\.linkedin-mcp\profile"
ATS_THRESHOLD = 80


def human_delay(min_s: float = 3.0, max_s: float = 8.0):
    time.sleep(random.uniform(min_s, max_s))


def get_tailored_resume_path(job_id: int) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "resume")
    tailored = os.path.join(base, f"tailored_{job_id}.txt")
    fallback = os.path.join(base, "base_resume.txt")
    return tailored if os.path.exists(tailored) else fallback


def apply_to_job(job: dict, page) -> bool:
    """Attempt LinkedIn Easy Apply on a single job. Returns True on success."""
    url = job["url"]
    job_id = job["id"]

    try:
        logger.info(f"Navigating to: {url}")
        page.goto(url, timeout=30000)
        human_delay(3, 6)

        # Click Easy Apply button
        easy_apply_btn = page.locator("button.jobs-apply-button").first
        if not easy_apply_btn.is_visible(timeout=8000):
            logger.warning(f"No Easy Apply button found for job {job_id}")
            return False

        easy_apply_btn.click()
        human_delay(2, 4)

        # Handle multi-step form
        max_steps = 10
        for step in range(max_steps):
            logger.debug(f"  Form step {step + 1}")

            # Fill phone if empty
            phone_field = page.locator("input[id*='phoneNumber']").first
            if phone_field.is_visible(timeout=2000):
                val = phone_field.input_value()
                if not val:
                    phone_field.fill(os.environ.get("PHONE_NUMBER", ""))
                    human_delay(0.5, 1.5)

            # Upload resume if file input is visible
            resume_path = get_tailored_resume_path(job_id)
            file_input = page.locator("input[type='file']").first
            if file_input.is_visible(timeout=2000):
                logger.info(f"  Uploading resume: {resume_path}")
                file_input.set_input_files(resume_path)
                human_delay(1, 3)

            # Check for Submit button
            submit_btn = page.locator("button[aria-label='Submit application']").first
            if submit_btn.is_visible(timeout=3000):
                submit_btn.click()
                human_delay(2, 4)
                logger.info(f"  Application submitted for job {job_id}")
                mark_applied(job_id)
                return True

            # Check for Next / Review / Continue button
            next_btn = (
                page.locator("button[aria-label='Continue to next step']").first
                or page.locator("button[aria-label='Review your application']").first
                or page.locator("button:has-text('Next')").first
                or page.locator("button:has-text('Review')").first
            )
            if next_btn.is_visible(timeout=3000):
                next_btn.click()
                human_delay(2, 4)
                continue

            # Modal closed or unexpected state
            logger.warning(f"  Unexpected form state at step {step + 1} for job {job_id}")
            break

        logger.error(f"Could not complete application for job {job_id} after {max_steps} steps")
        mark_failed(job_id, "max_steps_reached")
        return False

    except PlaywrightTimeout as e:
        logger.error(f"Timeout on job {job_id}: {e}")
        mark_failed(job_id, f"timeout: {e}")
        return False
    except Exception as e:
        logger.error(f"Error applying to job {job_id}: {e}")
        mark_failed(job_id, str(e))
        return False


def apply_batch(jobs: list[dict]) -> dict:
    if not jobs:
        logger.info("No jobs to apply to.")
        return {"applied": 0, "failed": 0}

    applied = failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = browser.new_page()

        # Verify logged in
        page.goto("https://www.linkedin.com/feed/", timeout=20000)
        human_delay(3, 5)

        if "login" in page.url or "authwall" in page.url:
            logger.error("LinkedIn session expired. Run: uvx linkedin-scraper-mcp --login")
            browser.close()
            return {"applied": 0, "failed": len(jobs)}

        for job in jobs:
            if job.get("ats_score", 0) < ATS_THRESHOLD:
                logger.info(f"Skipping job {job['id']} — ATS score {job['ats_score']} < {ATS_THRESHOLD}")
                continue

            if "linkedin.com" not in job.get("url", ""):
                logger.info(f"Skipping non-LinkedIn job {job['id']}: {job['url']}")
                continue

            success = apply_to_job(job, page)
            if success:
                applied += 1
            else:
                failed += 1

            human_delay(5, 10)

        browser.close()

    logger.info(f"Apply batch done: {applied} applied, {failed} failed")
    return {"applied": applied, "failed": failed}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Test with empty list
    result = apply_batch([])
    print(f"Result: {result}")
