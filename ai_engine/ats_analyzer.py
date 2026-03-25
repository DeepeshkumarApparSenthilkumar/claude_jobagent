import sys
import os
import json
import logging
import time
import anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import init_db, get_unprocessed_jobs, update_ats_score

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

RESUME_PATH = os.path.join(os.path.dirname(__file__), "..", "resume", "base_resume.txt")
MODEL = "claude-sonnet-4-20250514"


def load_resume() -> str:
    if not os.path.exists(RESUME_PATH):
        raise FileNotFoundError(f"Resume not found at {RESUME_PATH}. Please add your resume.")
    with open(RESUME_PATH, encoding="utf-8") as f:
        return f.read().strip()


def analyze_job(resume: str, job: dict, client: anthropic.Anthropic) -> dict:
    prompt = f"""You are an expert ATS (Applicant Tracking System) analyzer.

Compare the following resume against the job description and return a JSON object ONLY.

RESUME:
{resume}

JOB TITLE: {job['title']}
COMPANY: {job['company']}
JOB DESCRIPTION:
{job['description']}

Return ONLY valid JSON with this exact structure:
{{
  "score": <integer 0-100>,
  "matching_keywords": [<list of keywords found in both resume and JD>],
  "missing_keywords": [<list of important keywords in JD but missing from resume>],
  "summary": "<2-3 sentence assessment of fit>"
}}

Scoring guide:
- 90-100: Excellent match, most keywords present, strong fit
- 80-89: Good match, apply with minor tailoring
- 70-79: Moderate match, needs tailoring
- Below 70: Poor match, skip

Return only the JSON, no markdown, no explanation."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    return json.loads(text)


def analyze_all() -> dict:
    init_db()
    resume = load_resume()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    jobs = get_unprocessed_jobs()

    if not jobs:
        logger.info("No unprocessed jobs to analyze.")
        return {"analyzed": 0, "qualified": 0, "skipped": 0}

    logger.info(f"Analyzing {len(jobs)} jobs...")
    analyzed = qualified = skipped = 0

    for job in jobs:
        if not job.get("description"):
            logger.warning(f"Job {job['id']} has no description, skipping.")
            skipped += 1
            continue

        try:
            result = analyze_job(resume, job, client)
            score = int(result.get("score", 0))
            update_ats_score(job["id"], score)
            analyzed += 1

            if score >= 80:
                qualified += 1
                logger.info(
                    f"  [QUALIFIED] [{job['id']}] {job['title']} @ {job['company']} — Score: {score}"
                )
                logger.info(f"    Matching: {result.get('matching_keywords', [])}")
                logger.info(f"    Missing:  {result.get('missing_keywords', [])}")
            else:
                logger.info(
                    f"  [SKIP] [{job['id']}] {job['title']} @ {job['company']} — Score: {score}"
                )

            # Store full result alongside score for resume tailor to use
            result_path = os.path.join(
                os.path.dirname(__file__), "..", "logs", f"ats_{job['id']}.json"
            )
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump({**result, "job_id": job["id"], "job_title": job["title"], "company": job["company"]}, f, indent=2)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for job {job['id']}: {e}")
            skipped += 1
        except Exception as e:
            logger.error(f"Error analyzing job {job['id']}: {e}")
            skipped += 1

        time.sleep(1)  # Rate limiting

    logger.info(f"ATS analysis complete: {analyzed} analyzed, {qualified} qualified, {skipped} skipped")
    return {"analyzed": analyzed, "qualified": qualified, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = analyze_all()
    print(f"Results: {stats}")
