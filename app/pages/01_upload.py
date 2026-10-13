"""
app/pages/01_upload.py
-----------------------
Upload Data page — the owner's entry point into the system.

UI RULE (strictly enforced here):
  This file contains ONLY:
    1. st.* calls for layout and display
    2. Calls to service functions
    3. Rendering of the returned plain data objects

  NO Pandas calculations, NO SQL queries, NO prompt text live here.
  If you want to add business logic, add it to upload_service.py and
  call it from here. This ensures the page can be replaced by a React
  frontend later without rewriting any logic.

SESSION STATE KEYS USED:
  "upload_preview"  — UploadPreview from Phase A (set after file is read)
  "upload_result"   — UploadResult from Phase B (set after DB write)
  "last_file_key"   — Fingerprint of the current file to detect re-uploads
"""

import streamlit as st

from services.mapping_service import STANDARD_COLUMNS
from services.upload_service import (
    UploadPreview,
    UploadResult,
    execute_upload,
    suggest_mapping_from_file,
)

# Get the logged-in user's tenant ID
TENANT_ID = st.session_state.get("tenant_id", "demo_user")

# Required standard fields per file type — used for validation in the form.
_REQUIRED: dict[str, list[str]] = {
    "sales": ["date", "product", "revenue"],
    "expenses": ["date", "category", "amount"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────
st.title("📤 Upload Your Data")
st.caption(
    "Upload your sales or expenses file. "
    "We'll clean it automatically and load it into your dashboard."
)
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: render a method badge (how we matched a column)
# ─────────────────────────────────────────────────────────────────────────────
def _method_badge(method: str) -> str:
    """Return a short coloured emoji-label for the mapping method."""
    return {
        "rule": "✅ auto",
        "llm": "🤖 AI",
        "unmapped": "⚠️ manual",
    }.get(method, "❓ unknown")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — File type selector + file uploader
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("① Choose what you're uploading")

col_type, col_upload = st.columns([1, 2], gap="large")

with col_type:
    file_type: str = st.selectbox(
        "Type of data",
        options=["sales", "expenses"],
        format_func=lambda x: "📈 Sales" if x == "sales" else "💸 Expenses",
        help="Sales: items sold with revenue. Expenses: costs like rent or salaries.",
        key="sel_file_type",
    )

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload your CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Maximum 10 MB. CSV, XLSX, and XLS are supported.",
        key="widget_file_uploader",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Detect a new upload or file_type change → reset session state
# ─────────────────────────────────────────────────────────────────────────────
# We build a "fingerprint" from the file's name, size, and chosen type.
# If it changes, the user started fresh — wipe any previous results.
current_key = (
    f"{uploaded_file.name}|{uploaded_file.size}|{file_type}"
    if uploaded_file
    else None
)
if current_key != st.session_state.get("last_file_key"):
    st.session_state.pop("upload_preview", None)
    st.session_state.pop("upload_result", None)
    st.session_state["last_file_key"] = current_key


# ─────────────────────────────────────────────────────────────────────────────
# Phase A — Read file + suggest mapping (runs once per new file)
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_file is not None and "upload_preview" not in st.session_state:
    with st.spinner("Reading your file and matching column names…"):
        try:
            preview: UploadPreview = suggest_mapping_from_file(
                file_bytes=uploaded_file.read(),
                filename=uploaded_file.name,
                file_type=file_type,
                use_llm=False,   # Rules only for now; Phase 4 will enable LLM
            )
            st.session_state["upload_preview"] = preview
        except ValueError as err:
            st.error(f"❌ {err}")
            st.caption("Please check your file and try again.")
            st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — File preview
# ─────────────────────────────────────────────────────────────────────────────
if "upload_preview" in st.session_state and "upload_result" not in st.session_state:
    preview: UploadPreview = st.session_state["upload_preview"]

    st.divider()
    st.subheader("② Review Your File")

    m1, m2, m3 = st.columns(3)
    m1.metric("Rows in file", preview.raw_row_count)
    m2.metric("Columns found", len(preview.column_names))
    m3.metric(
        "Mapping status",
        "✅ Ready" if preview.suggested.is_complete else "⚠️ Needs review",
    )

    with st.expander("👁️ Preview (first 5 rows of your file)"):
        st.dataframe(preview.sample_rows, use_container_width=True)

    # ── Stage 3 — Column mapping form ────────────────────────────────────────
    st.divider()
    st.subheader("③ Confirm Column Mapping")
    st.caption(
        "We've automatically matched your columns to our standard fields. "
        "Review the table below — correct any that look wrong, "
        "then click **Confirm & Upload**."
    )
    st.markdown(
        "> ⭐ = required field &nbsp;&nbsp; ✅ auto = matched by rule "
        "&nbsp;&nbsp; 🤖 AI = matched by AI &nbsp;&nbsp; ⚠️ manual = needs your input"
    )

    standard_options = ["— skip (don't import this column) —"] + STANDARD_COLUMNS[file_type]
    required_fields = _REQUIRED[file_type]

    with st.form("mapping_form", border=True):

        # Table header
        h_raw, h_arrow, h_std, h_how = st.columns([2, 0.4, 2, 1.2])
        h_raw.markdown("**Your column**")
        h_std.markdown("**Standard field**")
        h_how.markdown("**How matched**")
        st.divider()

        for raw_col, suggested_std in preview.suggested.suggested.items():
            c_raw, c_arrow, c_std, c_how = st.columns([2, 0.4, 2, 1.2])

            with c_raw:
                # Mark required destination fields with a star
                is_dest_required = (suggested_std in required_fields)
                label = f"`{raw_col}`" + ("  ⭐" if is_dest_required else "")
                st.markdown(label)

            with c_arrow:
                st.markdown("→")

            with c_std:
                # Default to the suggested field; 0 = "— skip —" if no suggestion
                default_idx = (
                    standard_options.index(suggested_std)
                    if suggested_std in standard_options
                    else 0
                )
                st.selectbox(
                    label=f"Mapping for {raw_col}",
                    options=standard_options,
                    index=default_idx,
                    key=f"map__{raw_col}",   # double underscore avoids collision
                    label_visibility="collapsed",
                )

            with c_how:
                method = preview.suggested.method.get(raw_col, "unmapped")
                st.markdown(_method_badge(method))

        st.divider()

        # Read confirmed mapping from widget state
        # (We build it here inside the form so it's available at submit time)
        confirmed_mapping: dict[str, str] = {
            raw_col: st.session_state[f"map__{raw_col}"]
            for raw_col in preview.suggested.suggested
            if st.session_state.get(f"map__{raw_col}", "")
            != "— skip (don't import this column) —"
            and f"map__{raw_col}" in st.session_state
        }

        # Validate required fields before allowing submit
        mapped_stds = list(confirmed_mapping.values())
        missing_required = [r for r in required_fields if r not in mapped_stds]

        if missing_required:
            st.warning(
                f"⚠️ Please map these required fields before uploading: "
                f"**{', '.join(missing_required)}**"
            )

        submitted = st.form_submit_button(
            label="✅ Confirm Mapping & Upload",
            type="primary",
            use_container_width=True,
            disabled=bool(missing_required),
        )

    # ── Phase B — Execute upload ──────────────────────────────────────────────
    if submitted:
        # Re-build confirmed_mapping from session_state AFTER form submission
        final_mapping: dict[str, str] = {
            raw_col: st.session_state[f"map__{raw_col}"]
            for raw_col in preview.suggested.suggested
            if st.session_state.get(f"map__{raw_col}", "")
            != "— skip (don't import this column) —"
        }

        with st.spinner("Cleaning your data and saving to the database…"):
            result: UploadResult = execute_upload(
                raw_df=preview.raw_df,
                confirmed_mapping=final_mapping,
                file_type=file_type,
                filename=preview.filename,
                tenant_id=TENANT_ID,
            )
            st.session_state["upload_result"] = result

        st.rerun()   # re-render cleanly so Stage 4 appears at the top


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Upload result
# ─────────────────────────────────────────────────────────────────────────────
if "upload_result" in st.session_state:
    result: UploadResult = st.session_state["upload_result"]

    st.divider()
    st.subheader("④ Upload Result")

    if result.success:
        st.success(f"🎉 {result.summary()}")

        st.markdown("### Upload Summary")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("📄 Rows read", result.raw_count)
        r2.metric("✅ Rows saved", result.clean_count)
        r3.metric("⛔ Rows rejected", result.invalid_removed)
        r4.metric("🔁 Duplicates removed", result.duplicates_removed)
        
        diff = result.raw_revenue - result.clean_revenue
        status_text = "✅ Fully reconciled" if abs(diff) < 0.01 else "⚠️ WARNING: Reconciliation mismatch"
        
        st.markdown("---")
        f1, f2, f3 = st.columns(3)
        f1.metric("Source revenue/amount", f"₹{result.raw_revenue:,.2f}")
        f2.metric("Saved revenue/amount", f"₹{result.clean_revenue:,.2f}")
        f3.metric("Difference", f"₹{diff:,.2f}")
        st.markdown(f"**Status:** {status_text}")
        
        if result.invalid_removed > 0:
            st.markdown("---")
            with st.expander(f"⛔ {result.invalid_removed} Rows Rejected — Review Required", expanded=True):
                st.markdown(f"**Rejected rows:** {result.invalid_removed}")
                st.markdown(f"**Rejected rows with revenue:** {result.rejected_rows_with_revenue_count}")
                st.markdown(f"**Rejected revenue excluded:** ₹{result.rejected_revenue_excluded:,.2f}")
                
                # Show dataframe
                import pandas as pd
                rejected_data = []
                for r in result.rejected_rows_detailed:
                    row_dict = r["original_row"]
                    row_dict["Rejection Reason"] = r["reason"]
                    row_dict["Original Row Number"] = r["original_index"]
                    rejected_data.append(row_dict)
                
                if rejected_data:
                    rej_df = pd.DataFrame(rejected_data)
                    st.dataframe(rej_df, use_container_width=True)
                    
                    csv = rej_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Rejected Rows",
                        data=csv,
                        file_name=f"rejected_rows_{result.filename}.csv",
                        mime="text/csv",
                    )

        if result.warnings:
            with st.expander("ℹ️ Other Cleaning notes"):
                for w in result.warnings:
                    st.info(w, icon="ℹ️")

        st.caption(
            f"📌 Upload ID: **{result.upload_log_id}** — "
            "your data is saved and ready to view on the Dashboard."
        )

        st.divider()
        if st.button("📤 Upload Another File", use_container_width=True):
            for k in ["upload_preview", "upload_result", "last_file_key"]:
                st.session_state.pop(k, None)
            st.rerun()

    else:
        st.error(f"❌ {result.error_message}")
        st.caption(
            "Please check your file, make sure the column mapping is correct, "
            "and try again."
        )
        if st.button("🔄 Try Again", use_container_width=True):
            for k in ["upload_preview", "upload_result", "last_file_key"]:
                st.session_state.pop(k, None)
            st.rerun()
