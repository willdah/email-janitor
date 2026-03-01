"""
Streamlit app for reviewing email classifications and submitting corrections.

Run locally:  streamlit run src/email_janitor/corrections/app.py
Run via make: make corrections
"""

import streamlit as st

from email_janitor.config import DatabaseConfig
from email_janitor.corrections.db import (
    get_classifications,
    get_correction_stats,
    get_runs,
    insert_correction,
)
from email_janitor.schemas.schemas import EmailCategory

st.set_page_config(page_title="Email Janitor - Corrections", layout="wide")

CATEGORIES = [c.value for c in EmailCategory]

# ---------------------------------------------------------------------------
# Resolve database path
# ---------------------------------------------------------------------------
db_path = DatabaseConfig().path

if not db_path.exists():
    st.error(f"Database not found at `{db_path}`. Run the pipeline first to create it.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

runs = get_runs(db_path)
run_options = ["All runs"] + [
    f"{r['run_id'][:8]}... | {r['started_at'][:19]} | {r['emails_classified']} emails" for r in runs
]
run_index = st.sidebar.selectbox("Run", range(len(run_options)), format_func=lambda i: run_options[i])
selected_run_id = runs[run_index - 1]["run_id"] if run_index > 0 else None

category_options = ["All"] + CATEGORIES
selected_category = st.sidebar.selectbox("Category", category_options)
selected_category = None if selected_category == "All" else selected_category

max_confidence = st.sidebar.slider("Max confidence", min_value=1.0, max_value=5.0, value=5.0, step=0.5)
max_confidence_filter = max_confidence if max_confidence < 5.0 else None

hide_corrected = st.sidebar.checkbox("Hide already corrected", value=False)

# ---------------------------------------------------------------------------
# Load classifications
# ---------------------------------------------------------------------------
rows = get_classifications(
    db_path,
    run_id=selected_run_id,
    category=selected_category,
    max_confidence=max_confidence_filter,
    hide_corrected=hide_corrected,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Email Janitor - Corrections")
st.caption("Review classifications and submit corrections to build a ground-truth dataset.")
st.divider()

if not rows:
    st.info("No classifications match the current filters.")
    st.stop()

st.write(f"Showing **{len(rows)}** classifications")

# ---------------------------------------------------------------------------
# Classifications table
# ---------------------------------------------------------------------------
display_data = [
    {
        "ID": r["id"],
        "Subject": (r["subject"] or "")[:60],
        "Sender": (r["sender"] or "")[:40],
        "Classification": r["classification"],
        "Confidence": r["confidence"],
        "Corrected": r["corrected_classification"] or "",
    }
    for r in rows
]

st.dataframe(display_data, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Detail / correction panel
# ---------------------------------------------------------------------------
st.subheader("Review & Correct")

row_labels = [f"{r['id']} | {(r['subject'] or 'No subject')[:50]} | {r['classification']}" for r in rows]
selected_idx = st.selectbox("Select a classification", range(len(row_labels)), format_func=lambda i: row_labels[i])
row = rows[selected_idx]

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"**Sender:** {row['sender']}")
    st.markdown(f"**Subject:** {row['subject']}")
    st.markdown(f"**Classification:** {row['classification']}")
    st.markdown(f"**Confidence:** {row['confidence']}")
    st.markdown(f"**Classified at:** {row['classified_at']}")
with col2:
    st.markdown(f"**Reasoning:** {row['reasoning'] or 'N/A'}")
    st.markdown(f"**Refinements:** {row['refinement_count']}")
    st.markdown(f"**Action:** {row['action']}")

if row["corrected_classification"]:
    st.success(
        f"Already corrected to **{row['corrected_classification']}** "
        f"on {row['corrected_at'][:19]}. Notes: {row['correction_notes'] or 'none'}"
    )

with st.form("correction_form"):
    st.markdown("**Submit a correction**")
    current_idx = CATEGORIES.index(row["classification"]) if row["classification"] in CATEGORIES else 0
    corrected = st.selectbox("Correct classification", CATEGORIES, index=current_idx)
    notes = st.text_input("Notes (optional)")
    submitted = st.form_submit_button("Submit Correction")

    if submitted:
        if corrected == row["classification"]:
            st.warning("Corrected classification is the same as the original.")
        else:
            insert_correction(
                db_path,
                classification_id=row["id"],
                run_id=row["run_id"],
                email_id=row["email_id"],
                original_classification=row["classification"],
                corrected_classification=corrected,
                notes=notes,
            )
            st.success(f"Correction saved: {row['classification']} -> {corrected}")
            st.rerun()

# ---------------------------------------------------------------------------
# Footer stats
# ---------------------------------------------------------------------------
st.divider()
stats = get_correction_stats(db_path)
if stats["total"] > 0:
    breakdown = ", ".join(f"{k}: {v}" for k, v in stats["by_category"].items())
    st.caption(f"Total corrections: {stats['total']} | {breakdown}")
else:
    st.caption("No corrections submitted yet.")
