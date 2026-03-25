# Claude Job Agent 🤖

An **fully automated job application agent** powered by Claude AI (Anthropic), LinkedIn MCP, Playwright, and Streamlit.

Built by [Deepesh Kumar Appar Senthilkumar](https://linkedin.com/in/deepesh-kumar-a90a16218) — M.S. AI @ Illinois Institute of Technology.

---

## What It Does

1. **Scrapes jobs** from LinkedIn (via MCP server) and Indeed for your target titles
2. **Scores each job** against your resume using Claude AI (ATS score 0–100)
3. **Tailors your resume** with job-specific keywords using Claude AI
4. **Generates a cover letter** personalized per company and role
5. **Auto-applies** via LinkedIn Easy Apply (Playwright automation)
6. **Emails a daily digest** with all results to your Gmail
7. **Dashboard** (Streamlit) to monitor everything and run manually

---

## Project Structure

```
job-agent/
├── config.yaml                  # Job titles, location, ATS threshold, keywords
├── main.py                      # Master orchestrator — runs full pipeline
├── requirements.txt             # Python dependencies
├── setup_scheduler.bat          # Windows Task Scheduler (runs 8 AM daily)
├── .env.template                # Copy to .env and fill in your keys
│
├── db/
│   └── tracker.py               # SQLite DB — jobs table, dedup, CRUD
│
├── scrapers/
│   ├── indeed_scraper.py        # Scrape Indeed with BeautifulSoup
│   └── linkedin_mcp_client.py  # LinkedIn via MCP server (single session)
│
├── ai_engine/
│   ├── ats_analyzer.py          # Claude API — score resume vs JD (0-100)
│   ├── resume_tailor.py         # Claude API — rewrite bullets for each job
│   └── cover_letter.py          # Claude API — personalized cover letter
│
├── automation/
│   └── apply_bot.py             # Playwright — LinkedIn Easy Apply bot
│
├── scheduler/
│   └── email_digest.py          # Gmail SMTP — daily HTML summary email
│
├── dashboard/
│   └── app.py                   # Streamlit — overview, jobs table, resume manager
│
├── resume/
│   └── base_resume.txt          # Your base resume (plain text)
│
└── logs/                        # Daily run logs
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/DeepeshkumarApparSenthilkumar/claude_jobagent.git
cd claude_jobagent
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Set Up LinkedIn MCP Server

```bash
# Install uv
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone and set up LinkedIn MCP
git clone https://github.com/stickerdaniel/linkedin-mcp-server.git
cd linkedin-mcp-server
uv sync

# Login to LinkedIn (one-time, saves browser session)
uvx linkedin-scraper-mcp --login
```

### 3. Configure

```bash
# Copy and fill in your credentials
cp .env.template .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...         # console.anthropic.com
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword
GMAIL_ADDRESS=your@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Google Account → Security → App Passwords
PHONE_NUMBER=+11234567890
```

Edit `config.yaml` to set your target job titles, location, and ATS threshold.

### 4. Add Your Resume

```bash
streamlit run dashboard/app.py
# Go to Resume Manager → Upload PDF or DOCX
```

### 5. Run

```bash
# Full pipeline (scrape → score → tailor → apply → email)
python main.py

# Or via dashboard
streamlit run dashboard/app.py
# Click "Run Agent Now"
```

### 6. Schedule Daily (Windows)

Run `setup_scheduler.bat` as Administrator — schedules `main.py` at 8:00 AM daily.

---

## Configuration (`config.yaml`)

```yaml
job_search:
  titles:
    - "AI Engineer Intern"
    - "Machine Learning Intern"
    - "AI Engineer"
    - "Machine Learning Engineer"
    - "Software Engineer"
  location: "United States"
  remote: true
  ats_score_threshold: 80        # Only apply to jobs scoring >= 80
  daily_application_limit: 10
  easy_apply_only: true
  keywords:
    - Python
    - LLM
    - RAG
    - LangChain
    - PyTorch
  blacklist_companies:
    - "Rex.zone"
    - "Jobs via Dice"
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI / LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| LinkedIn Scraping | [linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server) via MCP |
| Indeed Scraping | `requests` + `BeautifulSoup4` |
| Browser Automation | `Playwright` |
| Database | `SQLite` via `tracker.py` |
| Dashboard | `Streamlit` + `Pandas` |
| Email | Gmail SMTP (`smtplib`) |
| Scheduling | Windows Task Scheduler |

---

## Dashboard

```bash
streamlit run dashboard/app.py
```

- **Overview** — Applied today/week/all-time, ATS score distribution, status breakdown
- **Jobs Table** — Filter by status, source, date; view full job details
- **Resume Manager** — Upload resume (PDF/DOCX), view all tailored versions

---

## Notes

- LinkedIn session expires periodically — re-run `uvx linkedin-scraper-mcp --login` to refresh
- Indeed blocks automated requests with 403s — LinkedIn MCP is the primary source
- The agent uses a single persistent MCP browser session per run to avoid bot detection
- All sensitive files (`.env`, `jobs.db`, session profiles) are git-ignored

---

## License

MIT
