"""
Gender classification review dashboard.

Users can filter entries, inspect per-method details, and either
*verify* a prediction or *correct* it.  Review decisions are stored in
``data/output/gender_reviewed.csv`` — a self-contained copy of the
full summary with two extra columns:

- ``review_status``:  verified | corrected | (empty = unreviewed)
- ``corrected_gender``: the human-assigned label (only when corrected)

Run from project root:
    streamlit run scripts/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

SUMMARY_CSV = Path(__file__).resolve().parent.parent / "data" / "output" / "gender_summary.csv"
REVIEW_CSV = Path(__file__).resolve().parent.parent / "data" / "output" / "gender_reviewed.csv"

GENDER_OPTIONS = ["male", "female", "unknown", "institution"]

METHODS = {
    "pqg": "Paren. qualifier",
    "gg": "gender_guesser",
    "gnd": "GND",
    "hfgc": "HF ClassifyGender",
    "hfg": "HF Genderize",
    "hv": "HIVOTO",
    "nqg": "NQG",
    "wgs": "Wiki-Gendersort",
    "llm": "LLM",
}

CERT_ORDER = ["high", "low", "contested", "single", "uncertain", "no_data"]
GENDER_COLOURS = {
    "male": "#4A90D9",
    "female": "#D94A7A",
    "unknown": "#999999",
    "institution": "#E8A838",
}

st.set_page_config(page_title="Gender Review", layout="wide")


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_summary() -> pd.DataFrame:
    df = pd.read_csv(SUMMARY_CSV, dtype=str)
    for col in df.columns:
        if col.endswith("_confidence") or col in ("iaa",):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["n_methods_answered"] = pd.to_numeric(df["n_methods_answered"], errors="coerce").astype("Int64")
    return df


def load_reviews() -> pd.DataFrame:
    """Load or initialise the reviewed CSV (with review_status + corrected_gender)."""
    summary = load_summary()
    if REVIEW_CSV.exists():
        rev = pd.read_csv(REVIEW_CSV, dtype=str)
        # Ensure columns match latest summary (new methods may have been added)
        for col in summary.columns:
            if col not in rev.columns:
                rev[col] = None
        for col in ("review_status", "corrected_gender"):
            if col not in rev.columns:
                rev[col] = None
        # Sync numeric types
        for col in rev.columns:
            if col.endswith("_confidence") or col in ("iaa",):
                rev[col] = pd.to_numeric(rev[col], errors="coerce")
        rev["n_methods_answered"] = pd.to_numeric(rev["n_methods_answered"], errors="coerce").astype("Int64")
        return rev
    # First run — copy from summary + add review columns
    summary["review_status"] = None
    summary["corrected_gender"] = None
    summary.to_csv(REVIEW_CSV, index=False)
    return summary


def save_reviews(rev_df: pd.DataFrame) -> None:
    rev_df.to_csv(REVIEW_CSV, index=False)


# Session-state wrapper around the review dataframe
if "reviews" not in st.session_state:
    st.session_state.reviews = load_reviews()

df = st.session_state.reviews
total = len(df)

# ── Sidebar filters ──────────────────────────────────────────────────────────

st.sidebar.title("Filters")

# Cert tier
certs_available = [c for c in CERT_ORDER if c in df["cert"].unique()]
default_certs = [c for c in ("uncertain", "contested", "low") if c in certs_available]
selected_certs = st.sidebar.multiselect("Certainty tier", certs_available, default=default_certs)

# Predicted gender
genders_available = sorted(df["predicted_gender"].dropna().unique())
selected_genders = st.sidebar.multiselect("Predicted gender", genders_available, default=genders_available)

# IAA range
iaa_min, iaa_max = st.sidebar.slider("IAA range", 0.0, 1.0, (0.0, 1.0), 0.01)

# n methods
n_methods_range = st.sidebar.slider(
    "Methods answered",
    int(df["n_methods_answered"].min()),
    int(df["n_methods_answered"].max()),
    (int(df["n_methods_answered"].min()), int(df["n_methods_answered"].max())),
)

# Text search
search = st.sidebar.text_input("Search name / note / xml_id")

# Review status filter
st.sidebar.markdown("---")
st.sidebar.markdown("**Review status**")
review_options = ["unreviewed", "verified", "corrected"]
selected_review = st.sidebar.multiselect("Review status", review_options, default=["unreviewed"])

# ── Apply filters ─────────────────────────────────────────────────────────────

mask = (
    df["cert"].isin(selected_certs)
    & df["predicted_gender"].isin(selected_genders)
    & df["n_methods_answered"].between(*n_methods_range)
)

# IAA filter (NaN iaa treated as matching if range includes 0)
iaa_mask = df["iaa"].between(iaa_min, iaa_max) | df["iaa"].isna()
mask = mask & iaa_mask

if search:
    search_lower = search.lower()
    text_mask = (
        df["name"].str.lower().str.contains(search_lower, na=False)
        | df["xml_id"].str.lower().str.contains(search_lower, na=False)
        | df["note"].fillna("").str.lower().str.contains(search_lower, na=False)
    )
    mask = mask & text_mask

# Review status filter
review_mask = pd.Series(False, index=df.index)
if "unreviewed" in selected_review:
    review_mask |= df["review_status"].isna() | (df["review_status"] == "")
if "verified" in selected_review:
    review_mask |= df["review_status"] == "verified"
if "corrected" in selected_review:
    review_mask |= df["review_status"] == "corrected"
mask = mask & review_mask

filtered = df[mask].copy()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("Gender Classification Review")
st.markdown(f"**{len(filtered):,}** of {total:,} entries selected")

# ── Review progress ───────────────────────────────────────────────────────────

n_verified = (df["review_status"] == "verified").sum()
n_corrected = (df["review_status"] == "corrected").sum()
n_unreviewed = total - n_verified - n_corrected
prog_cols = st.columns(4)
prog_cols[0].metric("Total", total)
prog_cols[1].metric("Unreviewed", int(n_unreviewed))
prog_cols[2].metric("Verified", int(n_verified))
prog_cols[3].metric("Corrected", int(n_corrected))

# ── Overview metrics ──────────────────────────────────────────────────────────

cols = st.columns(len(selected_certs) if selected_certs else 1)
for i, tier in enumerate(selected_certs):
    n = (filtered["cert"] == tier).sum()
    cols[i % len(cols)].metric(tier.upper(), n)

# ── Distribution charts ──────────────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.subheader("Predicted gender")
    gender_dist = filtered["predicted_gender"].value_counts()
    st.bar_chart(gender_dist)

with col2:
    st.subheader("Cert tier")
    cert_dist = filtered["cert"].value_counts().reindex([c for c in CERT_ORDER if c in filtered["cert"].values])
    st.bar_chart(cert_dist)

# ── Per-method label breakdown ────────────────────────────────────────────────

st.subheader("Per-method label breakdown (filtered rows)")

method_data = []
for short, name in METHODS.items():
    col_name = f"{short}_gender"
    if col_name not in filtered.columns:
        continue
    vc = filtered[col_name].value_counts()
    method_data.append({
        "Method": name,
        "Answered": int(filtered[col_name].notna().sum()),
        "male": int(vc.get("male", 0)),
        "female": int(vc.get("female", 0)),
        "unknown": int(vc.get("unknown", 0)),
        "institution": int(vc.get("institution", 0)),
    })
method_df = pd.DataFrame(method_data)
st.dataframe(method_df, use_container_width=True, hide_index=True)

# ── Data table ────────────────────────────────────────────────────────────────

st.subheader("Entries")

# Choose visible columns
display_cols_default = [
    "xml_id", "name", "note", "predicted_gender", "review_status", "corrected_gender",
    "cert", "iaa", "n_methods_answered",
]
# Add method gender columns
method_gender_cols = [f"{s}_gender" for s in METHODS if f"{s}_gender" in df.columns]
all_display = display_cols_default + method_gender_cols
if "llm_cert" in df.columns:
    all_display.insert(all_display.index("cert") + 1, "llm_cert")

# Compact view toggle
compact = st.checkbox("Compact view (hide method columns)", value=True)
if compact:
    show_cols = display_cols_default + (["llm_cert"] if "llm_cert" in df.columns else [])
else:
    show_cols = all_display

# Add confidence columns in expanded view
if not compact:
    conf_cols = [f"{s}_confidence" for s in METHODS if f"{s}_confidence" in df.columns]
    show_cols = show_cols + conf_cols
    # Deduplicate while preserving order
    seen = set()
    show_cols = [c for c in show_cols if c not in seen and not seen.add(c)]

show_cols = [c for c in show_cols if c in filtered.columns]

st.dataframe(
    filtered[show_cols].reset_index(drop=True),
    use_container_width=True,
    height=600,
)

# ── Review queue ──────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("Review queue")

if len(filtered) == 0:
    st.info("No entries match the current filters.")
else:
    # Maintain a position index in session state
    if "review_pos" not in st.session_state:
        st.session_state.review_pos = 0

    # Clamp to valid range
    pos = st.session_state.review_pos = max(0, min(st.session_state.review_pos, len(filtered) - 1))

    # Progress bar
    st.progress((pos + 1) / len(filtered), text=f"Entry {pos + 1} of {len(filtered)}")

    # Navigation row
    nav_cols = st.columns([1, 1, 2, 1, 1, 1])
    with nav_cols[0]:
        if st.button("⏮ First", use_container_width=True, disabled=(pos == 0)):
            st.session_state.review_pos = 0
            st.rerun()
    with nav_cols[1]:
        if st.button("◀ Prev", use_container_width=True, disabled=(pos == 0)):
            st.session_state.review_pos = pos - 1
            st.rerun()
    with nav_cols[2]:
        jump = st.number_input(
            "Go to #", min_value=1, max_value=len(filtered), value=pos + 1,
            step=1, label_visibility="collapsed", key=f"jump_input_{pos}",
        )
    with nav_cols[3]:
        if st.button("Go", use_container_width=True):
            st.session_state.review_pos = jump - 1
            st.rerun()
    with nav_cols[4]:
        if st.button("Next ▶", use_container_width=True, disabled=(pos >= len(filtered) - 1)):
            st.session_state.review_pos = pos + 1
            st.rerun()
    with nav_cols[5]:
        if st.button("Last ⏭", use_container_width=True, disabled=(pos >= len(filtered) - 1)):
            st.session_state.review_pos = len(filtered) - 1
            st.rerun()

    # Current entry
    row_series = filtered.iloc[pos]
    idx = filtered.index[pos]  # index into the full df
    selected_id = row_series["xml_id"]

    # ── Entry card ────────────────────────────────────────────────────────────
    cur_status = row_series.get("review_status", "") or ""
    cur_corrected = row_series.get("corrected_gender", "") or ""

    # Status badge
    if cur_status == "verified":
        st.success(f"✅ **Verified** — {selected_id}")
    elif cur_status == "corrected":
        st.warning(f"✏️ **Corrected** → `{cur_corrected}` — {selected_id}")
    else:
        st.info(f"🔍 **Unreviewed** — {selected_id}")

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(f"### {row_series['name']}")
        note_val = row_series.get("note", "") or ""
        if note_val:
            st.caption(note_val)
        st.markdown(
            f"**Predicted:** `{row_series['predicted_gender']}`&ensp;&ensp;"
            f"**Cert:** `{row_series['cert']}`&ensp;&ensp;"
            f"**IAA:** {row_series['iaa']}&ensp;&ensp;"
            f"**Methods:** {row_series['n_methods_answered']}"
        )

    with c2:
        detail_rows = []
        for short, name in METHODS.items():
            g_col = f"{short}_gender"
            c_col = f"{short}_confidence"
            if g_col in row_series.index and pd.notna(row_series[g_col]):
                detail_rows.append({
                    "Method": name,
                    "Gender": row_series[g_col],
                    "Confidence": row_series.get(c_col, "–"),
                })
        if detail_rows:
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

    # LLM reasoning
    llm_results_path = SUMMARY_CSV.parent.parent / "results" / "llm_gender_results.csv"
    if llm_results_path.exists():
        llm_df = pd.read_csv(llm_results_path, dtype=str)
        llm_row = llm_df[llm_df["xml_id"] == selected_id]
        if not llm_row.empty and "llm_reasoning" in llm_row.columns:
            reasoning = llm_row.iloc[0]["llm_reasoning"]
            if pd.notna(reasoning):
                with st.expander("LLM reasoning", expanded=False):
                    st.write(reasoning)

    # ── Action buttons ────────────────────────────────────────────────────────
    def _advance():
        """Move to next unreviewed entry in the filtered list, or just +1."""
        for i in range(pos + 1, len(filtered)):
            status = filtered.iloc[i].get("review_status", "")
            if not status or pd.isna(status):
                st.session_state.review_pos = i
                return
        # No more unreviewed — stay at next or current
        st.session_state.review_pos = min(pos + 1, len(filtered) - 1)

    st.markdown("#### Actions")
    btn_cols = st.columns([1, 1, 2, 1, 1])

    with btn_cols[0]:
        if st.button("✅ Verify", use_container_width=True, type="primary"):
            df.at[idx, "review_status"] = "verified"
            df.at[idx, "corrected_gender"] = None
            save_reviews(df)
            _advance()
            st.rerun()

    with btn_cols[1]:
        if st.button("✅ Verify + Skip ⏩", use_container_width=True,
                      help="Verify and jump to next unreviewed"):
            df.at[idx, "review_status"] = "verified"
            df.at[idx, "corrected_gender"] = None
            save_reviews(df)
            _advance()
            st.rerun()

    with btn_cols[2]:
        correct_gender = st.selectbox(
            "Correct to:",
            GENDER_OPTIONS,
            index=GENDER_OPTIONS.index(row_series["predicted_gender"])
            if row_series["predicted_gender"] in GENDER_OPTIONS else 0,
            key="correct_gender_select",
            label_visibility="collapsed",
        )

    with btn_cols[3]:
        if st.button("✏️ Correct", use_container_width=True):
            df.at[idx, "review_status"] = "corrected"
            df.at[idx, "corrected_gender"] = correct_gender
            save_reviews(df)
            _advance()
            st.rerun()

    with btn_cols[4]:
        if cur_status:
            if st.button("↩ Undo", use_container_width=True):
                df.at[idx, "review_status"] = None
                df.at[idx, "corrected_gender"] = None
                save_reviews(df)
                st.rerun()

# ── Export ────────────────────────────────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.download_button(
    "Download filtered CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="gender_review_filtered.csv",
    mime="text/csv",
)
