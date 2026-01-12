# app.py
import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from db import init_db, insert_start_log, complete_log, fetch_open_logs, fetch_completed_logs, delete_log


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

st.header("Start / Finish a Log")

# -----------------------
# START LOG (beginning of day)
# -----------------------
with st.form("start_log_form", clear_on_submit=True):
    st.subheader("Start Log (beginning of day)")
    log_date = st.date_input("Date", value=date.today(), key="start_date")

    c1, c2 = st.columns(2)
    with c1:
        start_miles_raw = st.text_input("Start Miles", placeholder="e.g. 76000", key="start_miles")
    with c2:
        start_time_val = st.time_input("Start Time", key="start_time")

    notes = st.text_input("Notes (optional)", key="start_notes")
    start_submit = st.form_submit_button("Start log")

    if start_submit:
        try:
            start_miles = float(start_miles_raw)
        except ValueError:
            st.error("Start Miles must be a number.")
            st.stop()

        if start_miles < 0:
            st.error("Miles cannot be negative.")
            st.stop()

        insert_start_log(
            date_str=str(log_date),
            start_miles=start_miles,
            start_time=start_time_val.strftime("%H:%M"),
            notes=notes.strip(),
        )
        st.success("Started log! Come back later to finish it.")


# -----------------------
# FINISH LOG (end of day)
# -----------------------
open_rows = fetch_open_logs()

st.subheader("Finish Log (end of day)")

if not open_rows:
    st.info("No open logs right now. Start a log above.")
else:
    # build a friendly dropdown label
    options = {
        r[0]: f"ID {r[0]} — {r[1]} — start {r[4]} — {r[2]:.2f} mi"
        for r in open_rows
    }
    selected_id = st.selectbox(
        "Choose an open log to finish",
        options=list(options.keys()),
        format_func=lambda k: options[k],
    )

    with st.form("finish_log_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            end_miles_raw = st.text_input("End Miles", placeholder="e.g. 76225", key="end_miles")
        with c2:
            end_time_val = st.time_input("End Time", key="end_time")

        finish_submit = st.form_submit_button("Finish log")

        if finish_submit:
            try:
                end_miles = float(end_miles_raw)
            except ValueError:
                st.error("End Miles must be a number.")
                st.stop()

            if end_miles < 0:
                st.error("Miles cannot be negative.")
                st.stop()

            # Validate end_miles > start_miles for the selected open log
            start_miles_for_selected = [r[2] for r in open_rows if r[0] == selected_id][0]
            if end_miles <= float(start_miles_for_selected):
                st.error("End Miles must be greater than Start Miles for this log.")
                st.stop()

            complete_log(
                log_id=int(selected_id),
                end_miles=end_miles,
                end_time=end_time_val.strftime("%H:%M"),
            )
            st.success("Log finished!")
            st.rerun()

# -----------------------
# Load logs
# -----------------------
rows = fetch_completed_logs()
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
# -----------------------
# CSV Export (primary)
# -----------------------
st.divider()
st.subheader("Export CSV")

all_min_d = df["date"].min()
all_max_d = df["date"].max()
today = date.today()

quick = st.selectbox(
    "Quick range",
    [
        "Custom",
        "Today",
        "Yesterday",
        "Last 7 days",
        "Last 14 days",
        "This week",
        "Last week",
        "This month",
        "Last month",
        "All time",
    ],
    index=0,
    key="csv_quick_range",
)

def week_start(d):
    return d - timedelta(days=d.weekday())

def last_month_range(d):
    first_this_month = d.replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    return last_prev_month.replace(day=1), last_prev_month

if quick == "Today":
    default_start = default_end = today
elif quick == "Yesterday":
    d = today - timedelta(days=1)
    default_start = default_end = d
elif quick == "Last 7 days":
    default_start, default_end = today - timedelta(days=6), today
elif quick == "Last 14 days":
    default_start, default_end = today - timedelta(days=13), today
elif quick == "This week":
    ws = week_start(today)
    default_start, default_end = ws, today
elif quick == "Last week":
    ws = week_start(today) - timedelta(days=7)
    default_start, default_end = ws, ws + timedelta(days=6)
elif quick == "This month":
    default_start, default_end = today.replace(day=1), today
elif quick == "Last month":
    default_start, default_end = last_month_range(today)
else:  # Custom / All time
    default_start, default_end = all_min_d, all_max_d

csv_start, csv_end = st.date_input(
    "CSV date range",
    value=(default_start, default_end),
    min_value=all_min_d,
    max_value=all_max_d,
    key="csv_date_range",
)

csv_df = df[
    (df["date"] >= csv_start) & (df["date"] <= csv_end)
][
    [
        "date",
        "start_miles",
        "end_miles",
        "start_time_display",
        "end_time_display",
        "notes",
    ]
].rename(
    columns={
        "date": "Date",
        "start_miles": "Start Miles",
        "end_miles": "End Miles",
        "start_time_display": "Start Time",
        "end_time_display": "End Time",
        "notes": "Notes",
    }
)

csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
csv_filename = f"time_miles_{csv_start}_to_{csv_end}.csv"

st.download_button(
    "⬇️ Download CSV",
    data=csv_bytes,
    file_name=csv_filename,
    mime="text/csv",
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

