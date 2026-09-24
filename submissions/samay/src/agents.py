"""L3-lite: advocate agents. Owner: Dev 2 (upside, after 3:15).

Each advocate decides, per listed hearing, how likely they are to turn up.
Returns a multiplier on the observed attendance-failure rate (1.0 = data as observed).
TODO(Dev 2): give advocates a personality (diligent / overloaded / dilatory) and let
them respond to incentives (adjournment cost, reminders, slot certainty).
"""
from __future__ import annotations

import numpy as np

CLASH_P = 0.25          # chance an advocate also has a matter in another courtroom today


def attendance_multiplier(rng: np.random.Generator, has_slot: bool, same_advocate_today: int,
                          clustered: bool) -> float:
    clash = rng.random() < CLASH_P
    m = 1.0
    if clash:
        # a real slot lets them plan around the other court; clustering means one trip
        m *= 1.1 if (has_slot and clustered) else 1.6
    if has_slot:
        m *= 0.85           # knows when to show up -> fewer no-shows
    if same_advocate_today > 1 and clustered:
        m *= 0.9            # already in the room for the previous matter
    return m
