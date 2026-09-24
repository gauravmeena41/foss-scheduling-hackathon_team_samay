"""Set D: Next-date recommendation. Owner: Dev 1 (after C).

Replaces the flat 60-day default with a gap matched to the work the next step needs.
"""
from __future__ import annotations

import pandas as pd

# multiplier on the reference gap, by today's outcome
OUTCOME_GAP = {
    "substantive": 1.0,   # moved forward -> ideal gap for the NEW purpose
    "preparation": 1.0,   # heard, unprepared -> same purpose, standard gap (+ summary nudge)
    "attendance": 0.5,    # someone absent -> sooner, don't let it drift
    "other": 0.5,
    "unreached": 0.0,     # not reached -> next working day (carry forward)
}


class Calendar:
    def __init__(self, calendar_csv, leave_dates=()):
        cal = pd.read_csv(calendar_csv, parse_dates=["date"])
        leave = {pd.Timestamp(d) for d in leave_dates}
        self.days = [d for d, ok in zip(cal["date"], cal["is_working_day"] == "Yes") if ok and d not in leave]
        self._set = set(self.days)
        self.last = self.days[-1]

    def on_or_after(self, day: pd.Timestamp) -> pd.Timestamp:
        for d in self.days:
            if d >= day:
                return d
        # past the calendar: next weekday, so the model keeps working
        while day.weekday() >= 5:
            day += pd.Timedelta(days=1)
        return day

    def after(self, day: pd.Timestamp, days: int) -> pd.Timestamp:
        return self.on_or_after(day + pd.Timedelta(days=max(1, int(round(days)))))


def next_date(purpose: str, outcome: str, day: pd.Timestamp, cal: Calendar, ref: pd.DataFrame,
              cfg: dict, ready_date: pd.Timestamp | None = None) -> pd.Timestamp:
    """Recommended next hearing date for a case whose NEXT purpose is `purpose`."""
    if outcome == "unreached":
        if cfg.get("carry_forward_weekly"):
            return cal.after(day, 7)            # Sehgal: same weekday next week
        return cal.after(day, 1)
    if outcome == "process":
        # nothing useful can happen until the process returns
        base = ready_date if ready_date is not None and ready_date > day else day + pd.Timedelta(days=7)
        return cal.on_or_after(base)
    gap = ref.at[purpose, "gap_days"] if purpose in ref.index else 14
    # TODO(Dev 1): load-aware — skip days already over expected capacity
    return cal.after(day, gap * OUTCOME_GAP.get(outcome, 1.0))
