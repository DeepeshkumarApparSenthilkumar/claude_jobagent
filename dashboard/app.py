import sys
import os
import subprocess
import io
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    except ImportError:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        except ImportError:
            return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except ImportError:
        return ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.tracker import init_db, get_all_jobs, get_today_stats

st.set_page_config(
    page_title="Job Agent Dashboard",
    page_icon="🤖",
    layout="wide",
)

init_db()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🤖 Job Agent")
    st.markdown("---")
    if st.button("▶ Run Agent Now", type="primary", use_container_width=True):
        script = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with st.spinner("Running job agent..."):
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                cwd=os.path.join(os.path.dirname(__file__), ".."),
            )
        if result.returncode == 0:
            st.success("Agent run complete!")
        else:
            st.error("Agent run failed. Check logs.")
            st.code(result.stderr[-2000:] if result.stderr else "No output")
        st.rerun()

    st.markdown("---")
    page = st.radio("Navigate", ["Overview", "Jobs Table", "Resume Manager"])
    st.markdown("---")
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("Refresh", use_container_width=True):
        st.rerun()


# ── Load data ────────────────────────────────────────────────────────
all_jobs = get_all_jobs()
df = pd.DataFrame(all_jobs) if all_jobs else pd.DataFrame(
    columns=["id", "title", "company", "url", "source", "ats_score", "status", "applied_at", "created_at"]
)

today = datetime.now().strftime("%Y-%m-%d")
week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

today_stats = get_today_stats()
total_applied = len(df[df["status"] == "applied"]) if not df.empty else 0
week_applied = len(df[(df["status"] == "applied") & (df["applied_at"] >= week_ago)]) if not df.empty and "applied_at" in df.columns else 0


# ── Page: Overview ───────────────────────────────────────────────────
if page == "Overview":
    st.title("📊 Overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Applied Today", today_stats["applied"])
    col2.metric("Applied This Week", week_applied)
    col3.metric("Applied All Time", total_applied)
    col4.metric("Jobs Found Today", today_stats["found"])

    st.markdown("---")

    if not df.empty and "ats_score" in df.columns:
        scored = df[df["ats_score"].notna()].copy()
        if not scored.empty:
            st.subheader("ATS Score Distribution")
            bins = [0, 50, 60, 70, 80, 90, 100]
            labels = ["0-50", "51-60", "61-70", "71-80", "81-90", "91-100"]
            scored["score_range"] = pd.cut(scored["ats_score"], bins=bins, labels=labels, right=True)
            dist = scored["score_range"].value_counts().sort_index()
            st.bar_chart(dist)

            qualified = len(scored[scored["ats_score"] >= 80])
            total_scored = len(scored)
            rate = round(qualified / total_scored * 100, 1) if total_scored > 0 else 0
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Jobs Scored", total_scored)
            col_b.metric("Qualified (≥80)", qualified)
            col_c.metric("Qualification Rate", f"{rate}%")
        else:
            st.info("No jobs with ATS scores yet. Run the agent to analyze jobs.")
    else:
        st.info("No data yet. Click **Run Agent Now** to start.")

    st.markdown("---")
    st.subheader("Status Breakdown")
    if not df.empty:
        status_counts = df["status"].value_counts()
        st.bar_chart(status_counts)

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Jobs Skipped Today")
        st.metric("Low ATS (< 80)", today_stats["skipped"])
    with col_r:
        st.subheader("Errors Today")
        log_path = os.path.join(os.path.dirname(__file__), "..", "logs", f"daily_{today}.log")
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as f:
                lines = f.readlines()
            errors = [l.strip() for l in lines if "ERROR" in l]
            st.metric("Errors in Log", len(errors))
            if errors:
                with st.expander("View errors"):
                    for e in errors[-10:]:
                        st.code(e)


# ── Page: Jobs Table ─────────────────────────────────────────────────
elif page == "Jobs Table":
    st.title("📋 All Jobs")

    if df.empty:
        st.info("No jobs in database yet.")
    else:
        col1, col2, col3 = st.columns(3)
        status_filter = col1.multiselect(
            "Filter by Status",
            options=df["status"].unique().tolist(),
            default=df["status"].unique().tolist(),
        )
        source_filter = col2.multiselect(
            "Filter by Source",
            options=df["source"].unique().tolist(),
            default=df["source"].unique().tolist(),
        )
        date_filter = col3.date_input(
            "From Date",
            value=datetime.now() - timedelta(days=30),
        )

        filtered = df[
            df["status"].isin(status_filter) &
            df["source"].isin(source_filter) &
            (df["created_at"] >= str(date_filter))
        ].copy()

        st.markdown(f"Showing **{len(filtered)}** of {len(df)} jobs")

        display_cols = ["id", "title", "company", "ats_score", "status", "source", "created_at"]
        display_cols = [c for c in display_cols if c in filtered.columns]

        def color_score(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            if val >= 80:
                return "color: #22c55e; font-weight: bold"
            if val >= 70:
                return "color: #f59e0b"
            return "color: #ef4444"

        styled = filtered[display_cols].style.applymap(color_score, subset=["ats_score"])
        st.dataframe(styled, use_container_width=True, height=500)

        # Detail expander
        if len(filtered) > 0:
            selected_id = st.selectbox("View job details", filtered["id"].tolist())
            job_row = filtered[filtered["id"] == selected_id].iloc[0]
            with st.expander(f"Details: {job_row['title']} @ {job_row['company']}"):
                st.markdown(f"**URL:** [{job_row['url']}]({job_row['url']})")
                st.markdown(f"**ATS Score:** {job_row.get('ats_score', 'Not analyzed')}")
                st.markdown(f"**Status:** {job_row['status']}")
                if "description" in job_row and job_row["description"]:
                    st.text_area("Description", job_row["description"], height=200)


# ── Page: Resume Manager ─────────────────────────────────────────────
elif page == "Resume Manager":
    st.title("📄 Resume Manager")

    resume_dir = os.path.join(os.path.dirname(__file__), "..", "resume")
    base_resume_path = os.path.join(resume_dir, "base_resume.txt")

    st.subheader("Upload Your Resume")

    uploaded = st.file_uploader(
        "Upload resume (PDF or DOCX)",
        type=["pdf", "docx"],
        help="Your resume will be converted to text and saved for ATS analysis.",
    )

    if uploaded is not None:
        file_bytes = uploaded.read()
        ext = uploaded.name.rsplit(".", 1)[-1].lower()

        with st.spinner("Extracting text from resume..."):
            if ext == "pdf":
                extracted = extract_text_from_pdf(file_bytes)
            elif ext == "docx":
                extracted = extract_text_from_docx(file_bytes)
            else:
                extracted = ""

        if not extracted:
            st.error(
                "Could not extract text. Make sure pdfplumber and python-docx are installed:\n"
                "`pip install pdfplumber python-docx`"
            )
        else:
            st.success(f"Extracted {len(extracted.split())} words from {uploaded.name}")
            preview = st.text_area("Preview / Edit extracted text:", value=extracted, height=350)
            if st.button("Save as Base Resume", type="primary"):
                os.makedirs(resume_dir, exist_ok=True)
                with open(base_resume_path, "w", encoding="utf-8") as f:
                    f.write(preview)
                st.success(f"Resume saved to {base_resume_path}")
                st.balloons()

    st.markdown("---")

    # Show current saved resume
    if os.path.exists(base_resume_path):
        with open(base_resume_path, encoding="utf-8") as f:
            base_content = f.read()
        with st.expander("View / Edit Current Saved Resume"):
            edited = st.text_area("Edit:", value=base_content, height=400, key="edit_base")
            if st.button("Save Changes"):
                with open(base_resume_path, "w", encoding="utf-8") as f:
                    f.write(edited)
                st.success("Saved!")
    else:
        st.info("No resume saved yet. Upload one above.")

    st.markdown("---")
    st.subheader("Tailored Resumes")

    if os.path.exists(resume_dir):
        tailored_files = sorted(
            [f for f in os.listdir(resume_dir) if f.startswith("tailored_")],
            reverse=True,
        )
        cover_files = sorted(
            [f for f in os.listdir(resume_dir) if f.startswith("cover_")],
            reverse=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**{len(tailored_files)} tailored resumes**")
            for fname in tailored_files[:20]:
                job_id = fname.replace("tailored_", "").replace(".txt", "")
                fpath = os.path.join(resume_dir, fname)
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                with st.expander(f"Job #{job_id}"):
                    st.text(content[:1500] + ("..." if len(content) > 1500 else ""))
                    st.download_button(
                        f"Download {fname}",
                        data=content,
                        file_name=fname,
                        key=f"dl_t_{job_id}",
                    )

        with col_b:
            st.markdown(f"**{len(cover_files)} cover letters**")
            for fname in cover_files[:20]:
                job_id = fname.replace("cover_", "").replace(".txt", "")
                fpath = os.path.join(resume_dir, fname)
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                with st.expander(f"Job #{job_id}"):
                    st.text(content[:1500] + ("..." if len(content) > 1500 else ""))
                    st.download_button(
                        f"Download {fname}",
                        data=content,
                        file_name=fname,
                        key=f"dl_c_{job_id}",
                    )
    else:
        st.info("No resumes generated yet.")
