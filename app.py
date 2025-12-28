# app.py
import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from db import init_db, insert_log, fetch_logs, delete_log
from pdf_report import build_pdf_report

st.set_page_config(page_title="Time & Miles Log", layout="centered")
init_db()


# -----------------------
# Auth
# -----------------------
def require_login() -> bool:
    """
    Simple password gate for personal/internal use.
    Looks for APP_PASSWORD in:
    1) Streamlit secrets (if present)
    2) Environment variables
    If neither exists, allow local dev.
    """
    app_pw = None
    try:
        app_pw = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        app_pw = None

    if not app_pw:
        app_pw = os.environ.get("APP_PASSWORD")

    if not app_pw:
        st.warning("APP_PASSWORD not set (secrets/env). Login disabled for local dev.")
        return True

    if st.session_state.get("authed"):
        return True

    st.title("🔒 Login")
    pw = st.text_input("Password", type="password")
    if st.button("Sign in"):
        if pw == app_pw:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False


# -----------------------
# Time helpers
# -----------------------
def duration_minutes(start_hhmm: str, end_hhmm: str) -> int:
    """
    Duration in WHOLE minutes (rounded) from start to end times stored as HH:MM.
    If end is earlier than start, assumes it crossed midnight.
    """
    start = datetime.strptime(start_hhmm, "%H:%M")
    end = datetime.strptime(end_hhmm, "%H:%M")
    if end < start:
        end += timedelta(days=1)

    seconds = (end - start).total_seconds()
    return int(round(seconds / 60))


def fmt_12hr(hhmm: str) -> str:
    """Convert HH:MM -> h:mm AM/PM (display only)"""
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def safe_float(s: str) -> float | None:
    """Convert typed input to float, returning None if invalid."""
    try:
        return float(s)
    except Exception:
        return None


# -----------------------
# Start app
# -----------------------
if not require_login():
    st.stop()

st.title("⏱️ Time & Miles Log")

# -----------------------
# Add Log Form
# -----------------------
with st.form("log_form", clear_on_submit=True):
    log_date = st.date_input("Date", value=date.today())

    c1, c2 = st.columns(2)
    with c1:
        start_miles_raw = st.text_input("Start Miles", placeholder="e.g. 1234.5")
        start_time_val = st.time_input("Start Time")  # UI may show 24h depending on system/locale
    with c2:
        end_miles_raw = st.text_input("End Miles", placeholder="e.g. 1240.2")
        end_time_val = st.time_input("End Time")

    notes = st.text_input("Notes (optional)")
    submitted = st.form_submit_button("Add log")

    if submitted:
        start_miles = safe_float(start_miles_raw)
        end_miles = safe_float(end_miles_raw)

        if start_miles is None or end_miles is None:
            st.error("Start Miles and End Miles must be valid numbers (example: 1234.5).")
            st.stop()

        if start_miles < 0 or end_miles < 0:
            st.error("Miles cannot be negative.")
            st.stop()

        if end_miles <= start_miles:
            st.error("End Miles must be greater than Start Miles.")
            st.stop()

        insert_log(
            str(log_date),
            float(start_miles),
            float(end_miles),
            start_time_val.strftime("%H:%M"),  # store as HH:MM
            end_time_val.strftime("%H:%M"),
            notes.strip(),
        )
        st.success("Log saved!")

# -----------------------
# Load logs
# -----------------------
rows = fetch_logs()
if not rows:
    st.info("No logs yet. Add your first entry above.")
    st.stop()

# Expected DB row order:
# id, date, start_miles, end_miles, start_time, end_time, notes
df = pd.DataFrame(
    rows,
    columns=["id", "date", "start_miles", "end_miles", "start_time", "end_time", "notes"],
)

# Normalize types
df["date"] = pd.to_datetime(df["date"]).dt.date
df["start_miles"] = df["start_miles"].astype(float)
df["end_miles"] = df["end_miles"].astype(float)

# Derived fields (NO seconds, NO floats for time/pace)
df["miles"] = (df["end_miles"] - df["start_miles"]).round(2)
df["time_min"] = df.apply(lambda r: duration_minutes(r["start_time"], r["end_time"]), axis=1)
df["pace_min"] = df.apply(lambda r: int(round(r["time_min"] / r["miles"])) if r["miles"] > 0 else 0, axis=1)

# Display-only (12 hour)
df["start_time_display"] = df["start_time"].apply(fmt_12hr)
df["end_time_display"] = df["end_time"].apply(fmt_12hr)

# -----------------------
# Filters
# -----------------------
st.subheader("Filters")
min_d = df["date"].min()
max_d = df["date"].max()

start_date, end_date = st.date_input(
    "Date range",
    value=(min_d, max_d),
    min_value=min_d,
    max_value=max_d,
)

filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()

# -----------------------
# Display logs
# -----------------------
st.subheader("Your logs")

display_df = filtered[
    [
        "id",
        "date",
        "start_miles",
        "end_miles",
        "start_time_display",
        "end_time_display",
        "miles",
        "time_min",
        "pace_min",
        "notes",
    ]
].rename(
    columns={
        "start_time_display": "Start Time",
        "end_time_display": "End Time",
        "time_min": "Time (min)",
        "pace_min": "Pace (min/mi)",
    }
)

st.dataframe(display_df, use_container_width=True, hide_index=True)

# -----------------------
# Summary (filtered)
# -----------------------
st.subheader("Summary (filtered)")

total_miles = float(filtered["miles"].sum())
total_time_min = int(filtered["time_min"].sum())
avg_pace_min = int(round(total_time_min / total_miles)) if total_miles > 0 else 0

c1, c2, c3 = st.columns(3)
c1.metric("Total Miles", f"{total_miles:.2f}")
c2.metric("Total Time (min)", f"{total_time_min}")
c3.metric("Avg Pace (min/mi)", f"{avg_pace_min}")

# -----------------------
# -----------------------
# -----------------------
# PDF Export (with quick dropdown + date selector)
# -----------------------
st.divider()
st.subheader("Export PDF")

all_min_d = df["date"].min()
all_max_d = df["date"].max()
today = date.today()

# Quick range options
quick = st.selectbox(
    "Quick range",
    [
        "Custom",
        "Today",
        "Yesterday",
        "Last 7 days",
        "Last 14 days",
        "This week (Mon–Sun)",
        "Last week (Mon–Sun)",
        "This month",
        "Last month",
        "All time",
    ],
    index=0,
    key="pdf_quick_range",
)

def clamp(d: date) -> date:
    if d < all_min_d:
        return all_min_d
    if d > all_max_d:
        return all_max_d
    return d

def week_start(d: date) -> date:
    # Monday as start of week
    return d - timedelta(days=d.weekday())

def month_start(d: date) -> date:
    return d.replace(day=1)

def last_month_range(d: date) -> tuple[date, date]:
    first_this_month = d.replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    first_prev_month = last_prev_month.replace(day=1)
    return first_prev_month, last_prev_month

# Determine default start/end based on quick selection
if quick == "Today":
    default_start, default_end = today, today
elif quick == "Yesterday":
    y = today - timedelta(days=1)
    default_start, default_end = y, y
elif quick == "Last 7 days":
    default_start, default_end = today - timedelta(days=6), today
elif quick == "Last 14 days":
    default_start, default_end = today - timedelta(days=13), today
elif quick == "This week (Mon–Sun)":
    ws = week_start(today)
    default_start, default_end = ws, ws + timedelta(days=6)
elif quick == "Last week (Mon–Sun)":
    ws = week_start(today) - timedelta(days=7)
    default_start, default_end = ws, ws + timedelta(days=6)
elif quick == "This month":
    ms = month_start(today)
    # end = today (more useful than end-of-month for "so far")
    default_start, default_end = ms, today
elif quick == "Last month":
    default_start, default_end = last_month_range(today)
elif quick == "All time":
    default_start, default_end = all_min_d, all_max_d
else:  # Custom
    default_start, default_end = all_min_d, all_max_d

# Clamp to data range so date_input doesn't complain
default_start = clamp(default_start)
default_end = clamp(default_end)
if default_end < default_start:
    default_end = default_start

pdf_start_date, pdf_end_date = st.date_input(
    "PDF date range",
    value=(default_start, default_end),
    min_value=all_min_d,
    max_value=all_max_d,
    key="pdf_date_range",
)

report_title = st.text_input(
    "Report title",
    value=f"Time & Miles Report ({pdf_start_date} to {pdf_end_date})",
    key="pdf_title",
)

pdf_filtered = df[(df["date"] >= pdf_start_date) & (df["date"] <= pdf_end_date)].copy()

if pdf_filtered.empty:
    st.warning("No logs found in that PDF date range.")
else:
    pdf_rows = []
    for _, r in pdf_filtered.iterrows():
        pdf_rows.append(
            {
                "date": str(r["date"]),
                "start_miles": float(r["start_miles"]),
                "end_miles": float(r["end_miles"]),
                "start_time": r["start_time_display"],  # 12-hour display
                "end_time": r["end_time_display"],      # 12-hour display
                "notes": r["notes"] or "",
            }
        )

    pdf_bytes = build_pdf_report(
        title=report_title,
        rows=pdf_rows,
    )

    filename = f"time_miles_report_{pdf_start_date}_to_{pdf_end_date}.pdf"
    st.download_button(
        "⬇️ Download PDF",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
    )


# -----------------------
# Delete log
# -----------------------
st.divider()
st.subheader("Delete a log")
delete_id = st.number_input("Enter log ID to delete", min_value=0, step=1)

if st.button("Delete"):
    if delete_id > 0:
        delete_log(int(delete_id))
        st.success("Deleted.")
        st.rerun()
    else:
        st.warning("Enter a valid ID.")

