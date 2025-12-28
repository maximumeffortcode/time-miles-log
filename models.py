# models.py
from datetime import datetime

def miles_completed(start_miles, end_miles):
    return round(end_miles - start_miles, 2)

def duration_seconds(start_time, end_time):
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    return int((end - start).total_seconds())

def pace_seconds_per_mile(total_seconds, miles):
    if miles <= 0:
        return 0
    return total_seconds / miles

def fmt_mmss(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"
