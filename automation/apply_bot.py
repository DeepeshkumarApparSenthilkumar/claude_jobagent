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

PROFILE_DIR = r"C:\Users\dk505\.linkedin-mcp\profile"
ATS_THRESHOLD = 80
INTERN_KEYWORDS = ["intern", "internship", "co-op", "coop"]


def human_delay(min_s: float = 3.0, max_s: float = 8.0):
    time.sleep(random.uniform(min_s, max_s))


def is_internship(job: dict) -> bool:
    text = (job.get("title", "") + " " + job.get("description", "")[:300]).lower()
    return any(k in text for k in INTERN_KEYWORDS)


def get_tailored_resume_path(job_id: int) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "resume")
    tailored = os.path.join(base, f"tailored_{job_id}.txt")
    fallback = os.path.join(base, "base_resume.txt")
    return tailored if os.path.exists(tailored) else fallback


def click_first_visible(page, selectors: list[str], timeout: int = 3000) -> bool:
    """Try each selector in order, click the first visible one. Returns True if clicked."""
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=timeout):
                btn.click()
                return True
        except Exception:
            continue
    return False


def apply_to_job(job: dict, page) -> bool:
    """Attempt LinkedIn Easy Apply. Returns True on success."""
    url = job["url"]
    job_id = job["id"]

    try:
        logger.info(f"Opening: [{job_id}] {job['title']} @ {job['company']}")
        page.goto(url, timeout=30000)
        human_delay(3, 5)

        # Find and click Easy Apply button
        easy_apply_clicked = click_first_visible(page, [
            "button.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='Apply']",
            ".jobs-apply-button",
        ], timeout=8000)

        if not easy_apply_clicked:
            logger.warning(f"  No Easy Apply button for job {job_id} — skipping")
            mark_failed(job_id, "no_easy_apply_button")
            return False

        human_delay(2, 3)

        # Multi-step form — up to 10 steps
        for step in range(10):
            logger.debug(f"  Step {step + 1}")

            # Fill phone number if field is empty
            try:
                phone = page.locator("input[id*='phoneNumber'], input[name*='phone']").first
                if phone.is_visible(timeout=1500):
                    if not phone.input_value():
                        phone.fill(os.environ.get("PHONE_NUMBER", ""))
                        human_delay(0.5, 1.0)
            except Exception:
                pass

            # Upload resume if file input visible
            try:
                file_input = page.locator("input[type='file']").first
                if file_input.is_visible(timeout=1500):
                    resume_path = get_tailored_resume_path(job_id)
                    logger.info(f"  Uploading: {os.path.basename(resume_path)}")
                    file_input.set_input_files(resume_path)
                    human_delay(1, 2)
            except Exception:
                pass

            # Check for Submit
            try:
                submit = page.locator("button[aria-label='Submit application']").first
                if submit.is_visible(timeout=2000):
                    submit.click()
                    human_delay(2, 3)
                    logger.info(f"  ✅ Submitted: [{job_id}] {job['title']} @ {job['company']}")
                    mark_applied(job_id)
                    return True
            except Exception:
                pass

            # Check for Next / Review / Continue
            advanced = click_first_visible(page, [
                "button[aria-label='Continue to next step']",
                "button[aria-label='Review your application']",
                "button[aria-label='Next']",
                "button:has-text('Next')",
                "button:has-text('Review')",
                "button:has-text('Continue')",
            ], timeout=2000)

            if advanced:
                human_delay(1.5, 3)
                continue

            # Modal may have closed
            logger.warning(f"  Stuck at step {step + 1} for job {job_id}")
            break

        logger.error(f"  ❌ Could not complete: [{job_id}] {job['title']}")
        mark_failed(job_id, "form_incomplete")
        return False

    except PlaywrightTimeout as e:
        logger.error(f"  Timeout on job {job_id}: {e}")
        mark_failed(job_id, "timeout")
        return False
    except Exception as e:
        logger.error(f"  Error on job {job_id}: {e}")
        mark_failed(job_id, str(e)[:100])
        return False


def apply_batch(jobs: list[dict]) -> dict:
    if not jobs:
        logger.info("No jobs to apply to.")
        return {"applied": 0, "failed": 0, "skipped": 0}

    applied = failed = skipped = 0

    # Filter: internships only + must be LinkedIn URL
    intern_jobs = []
    for job in jobs:
        if "linkedin.com" not in job.get("url", ""):
            logger.info(f"  Skipping non-LinkedIn: {job['title']} @ {job['company']}")
            skipped += 1
            continue
        if not is_internship(job):
            logger.info(f"  Skipping non-internship: {job['title']} @ {job['company']}")
            skipped += 1
            continue
        intern_jobs.append(job)

    logger.info(f"Intern jobs to apply: {len(intern_jobs)} (skipped {skipped} non-intern/non-LinkedIn)")

    if not intern_jobs:
        return {"applied": 0, "failed": 0, "skipped": skipped}

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = browser.new_page()

        # Verify session
        page.goto("https://www.linkedin.com/feed/", timeout=20000)
        human_delay(3, 4)

        if "login" in page.url or "authwall" in page.url:
            logger.error("LinkedIn session expired. Run: uvx linkedin-scraper-mcp --login")
            browser.close()
            return {"applied": 0, "failed": len(intern_jobs), "skipped": skipped}

        logger.info("LinkedIn session active. Starting applications...")

        for job in intern_jobs:
            if job.get("ats_score", 0) < ATS_THRESHOLD:
                logger.info(f"  Skipping low ATS: {job['title']} ({job['ats_score']})")
                skipped += 1
                continue

            success = apply_to_job(job, page)
            if success:
                applied += 1
            else:
                failed += 1

            human_delay(5, 10)

        browser.close()

    logger.info(f"Apply batch done — Applied: {applied} | Failed: {failed} | Skipped: {skipped}")
    return {"applied": applied, "failed": failed, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = apply_batch([])
    print(f"Result: {result}")
