import sys
import os
import json
import logging
import anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

RESUME_PATH = os.path.join(os.path.dirname(__file__), "..", "resume", "base_resume.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "resume")
MODEL = "claude-sonnet-4-20250514"


def load_resume() -> str:
    with open(RESUME_PATH, encoding="utf-8") as f:
        return f.read().strip()


def load_ats_result(job_id: int) -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "logs", f"ats_{job_id}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def tailor(job: dict, client: anthropic.Anthropic = None) -> str:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    resume = load_resume()
    ats = load_ats_result(job["id"])
    missing_keywords = ats.get("missing_keywords", [])

    prompt = f"""You are a professional resume writer and career coach.

Tailor the following resume to better match the job description below.

INSTRUCTIONS:
- Rewrite bullet points to incorporate missing keywords naturally
- Keep all facts truthful — do NOT invent experience
- Maintain the same overall structure and format
- Prioritize keywords: {', '.join(missing_keywords) if missing_keywords else 'use keywords from the job description'}
- Keep the resume concise and ATS-friendly
- Output the full tailored resume text

BASE RESUME:
{resume}

JOB TITLE: {job['title']}
COMPANY: {job['company']}
JOB DESCRIPTION:
{job['description']}

Output ONLY the tailored resume text, ready to copy-paste. No explanations."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    tailored = message.content[0].text.strip()

    output_path = os.path.join(OUTPUT_DIR, f"tailored_{job['id']}.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Tailored Resume for: {job['title']} at {job['company']}\n")
        f.write(f"# Job ID: {job['id']}\n\n")
        f.write(tailored)

    logger.info(f"Tailored resume saved: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    test_job = {
        "id": 999,
        "title": "AI Engineer Intern",
        "company": "Test Corp",
        "description": "We need Python, PyTorch, LangChain, RAG, FastAPI skills.",
    }
    path = tailor(test_job)
    print(f"Saved to: {path}")
