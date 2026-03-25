import sys
import os
import logging
import anthropic
from dotenv import load_dotenv
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

RESUME_PATH = os.path.join(os.path.dirname(__file__), "..", "resume", "base_resume.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "resume")
MODEL = "claude-sonnet-4-20250514"


def load_resume() -> str:
    with open(RESUME_PATH, encoding="utf-8") as f:
        return f.read().strip()


def generate(job: dict, client: anthropic.Anthropic = None) -> str:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    resume = load_resume()
    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are an expert career coach writing a compelling cover letter.

Write a professional, personalized cover letter for this job application.

INSTRUCTIONS:
- Opening: Express genuine enthusiasm for the specific company and role
- Body paragraph 1: Highlight 2-3 most relevant experiences from the resume
- Body paragraph 2: Connect your skills directly to the job requirements
- Closing: Express eagerness to discuss, include a call to action
- Tone: Professional but enthusiastic, not generic
- Length: 3-4 paragraphs, under 400 words
- Do NOT use hollow phrases like "I am writing to express my interest"
- Do NOT start with "Dear Hiring Manager" — use a compelling opening line

RESUME:
{resume}

JOB TITLE: {job['title']}
COMPANY: {job['company']}
JOB DESCRIPTION:
{job['description']}

TODAY'S DATE: {today}

Output ONLY the cover letter text, formatted and ready to send. No metadata."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    cover_letter = message.content[0].text.strip()

    output_path = os.path.join(OUTPUT_DIR, f"cover_{job['id']}.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Cover Letter: {job['title']} at {job['company']}\n")
        f.write(f"# Job ID: {job['id']} | Generated: {today}\n\n")
        f.write(cover_letter)

    logger.info(f"Cover letter saved: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    test_job = {
        "id": 999,
        "title": "AI Engineer Intern",
        "company": "Anthropic",
        "description": "Build LLM-powered applications with Python, PyTorch, RAG pipelines.",
    }
    path = generate(test_job)
    print(f"Cover letter saved to: {path}")
