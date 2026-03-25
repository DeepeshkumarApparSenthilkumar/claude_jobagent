import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            description TEXT,
            ats_score INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'new',
            applied_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def is_duplicate(url: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def add_job(title: str, company: str, url: str, source: str, description: str = "") -> int | None:
    if is_duplicate(url):
        return None
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO jobs (title, company, url, source, description) VALUES (?, ?, ?, ?, ?)",
        (title, company, url, source, description),
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def get_unprocessed_jobs() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE ats_score IS NULL AND status = 'new'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_qualified_jobs(threshold: int = 80) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE ats_score >= ? AND status = 'analyzed'",
        (threshold,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_jobs() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_ats_score(job_id: int, score: int):
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET ats_score = ?, status = 'analyzed' WHERE id = ?",
        (score, job_id),
    )
    conn.commit()
    conn.close()


def mark_applied(job_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = 'applied', applied_at = ? WHERE id = ?",
        (datetime.now().isoformat(), job_id),
    )
    conn.commit()
    conn.close()


def mark_failed(job_id: int, reason: str = ""):
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = 'failed' WHERE id = ?",
        (job_id,),
    )
    conn.commit()
    conn.close()


def get_today_stats() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    applied = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at LIKE ? AND status = 'applied'",
        (f"{today}%",),
    ).fetchone()[0]
    found = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE created_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    skipped = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE ats_score IS NOT NULL AND ats_score < 80 AND created_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    conn.close()
    return {"applied": applied, "found": found, "skipped": skipped}


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {DB_PATH}")
    test_id = add_job(
        title="AI Engineer Intern",
        company="Test Corp",
        url="https://example.com/job/1",
        source="test",
        description="We need Python, ML, LangChain skills.",
    )
    print(f"Test job inserted with id: {test_id}")
    print(f"Duplicate check: {is_duplicate('https://example.com/job/1')}")
    jobs = get_unprocessed_jobs()
    print(f"Unprocessed jobs: {len(jobs)}")
    print("DB test passed.")
