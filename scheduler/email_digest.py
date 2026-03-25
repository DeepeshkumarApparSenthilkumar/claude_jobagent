import sys
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import get_all_jobs, get_today_stats

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def build_html(stats: dict, jobs_today: list[dict], errors: list[str]) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    applied_rows = ""
    skipped_rows = ""

    for job in jobs_today:
        score = job.get("ats_score") or "N/A"
        score_color = "#22c55e" if isinstance(score, int) and score >= 80 else "#f59e0b"
        row = f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb">{job['title']}</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb">{job['company']}</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb;color:{score_color};font-weight:bold">{score}</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb"><a href="{job['url']}" style="color:#3b82f6">View</a></td>
        </tr>"""
        if job.get("status") == "applied":
            applied_rows += row
        elif isinstance(score, int) and score < 80:
            skipped_rows += row

    errors_html = ""
    if errors:
        error_items = "".join(f"<li style='color:#ef4444'>{e}</li>" for e in errors)
        errors_html = f"""
        <h3 style="color:#ef4444">Errors ({len(errors)})</h3>
        <ul>{error_items}</ul>"""

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#111827">
  <h1 style="color:#1d4ed8">Job Agent Daily Report</h1>
  <p style="color:#6b7280">{today}</p>

  <div style="display:flex;gap:16px;margin:24px 0">
    <div style="flex:1;background:#dbeafe;border-radius:8px;padding:16px;text-align:center">
      <div style="font-size:36px;font-weight:bold;color:#1d4ed8">{stats['applied']}</div>
      <div style="color:#3b82f6">Applied Today</div>
    </div>
    <div style="flex:1;background:#dcfce7;border-radius:8px;padding:16px;text-align:center">
      <div style="font-size:36px;font-weight:bold;color:#16a34a">{stats['found']}</div>
      <div style="color:#22c55e">Found Today</div>
    </div>
    <div style="flex:1;background:#fef3c7;border-radius:8px;padding:16px;text-align:center">
      <div style="font-size:36px;font-weight:bold;color:#d97706">{stats['skipped']}</div>
      <div style="color:#f59e0b">Skipped (Low ATS)</div>
    </div>
  </div>

  <h2>Applied Jobs</h2>
  {"<p style='color:#6b7280'>No applications sent today.</p>" if not applied_rows else f'''
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="background:#f3f4f6">
        <th style="padding:8px;text-align:left">Title</th>
        <th style="padding:8px;text-align:left">Company</th>
        <th style="padding:8px;text-align:left">ATS Score</th>
        <th style="padding:8px;text-align:left">Link</th>
      </tr>
    </thead>
    <tbody>{applied_rows}</tbody>
  </table>'''}

  <h2>Skipped Jobs (ATS &lt; 80)</h2>
  {"<p style='color:#6b7280'>None skipped today.</p>" if not skipped_rows else f'''
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="background:#f3f4f6">
        <th style="padding:8px;text-align:left">Title</th>
        <th style="padding:8px;text-align:left">Company</th>
        <th style="padding:8px;text-align:left">ATS Score</th>
        <th style="padding:8px;text-align:left">Link</th>
      </tr>
    </thead>
    <tbody>{skipped_rows}</tbody>
  </table>'''}

  {errors_html}

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
  <p style="color:#9ca3af;font-size:12px">Sent by Job Agent | Running on your machine</p>
</body>
</html>"""
    return html


def send(errors: list[str] = None) -> bool:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.error("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env")
        return False

    errors = errors or []
    stats = get_today_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    all_jobs = get_all_jobs()
    jobs_today = [j for j in all_jobs if j.get("created_at", "").startswith(today)]

    html_body = build_html(stats, jobs_today, errors)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Agent Report — {today} | Applied: {stats['applied']} | Found: {stats['found']}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        logger.info(f"Email digest sent to {GMAIL_ADDRESS}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok = send(errors=["Test error message"])
    print("Email sent!" if ok else "Email failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
