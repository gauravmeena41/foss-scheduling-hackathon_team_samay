"""L3: advocate agents that decide, and learn from how the court treats them.

Each advocate has a personality. Before and on the hearing day they decide whether to
turn up, whether they are prepared, and - at the 2-day readiness check - whether to own up
to not being ready. The court's policy changes those decisions (a real time slot,
clustering their matters, reminders, a cost for adjourning on the day), and every outcome
feeds back into how they behave next time.

Calibration: multipliers are relative to the population average, so with no policy levers
the court-wide no-show and unpreparedness rates stay at the observed data.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

PERSONALITIES = {
    #             share  prepared  shows_up  honest_at_check  other-court clash
    "diligent":  (0.30,  0.90,     0.95,     0.90,            0.15),
    "overloaded": (0.50, 0.65,     0.80,     0.70,            0.40),
    "dilatory":  (0.20,  0.45,     0.70,     0.35,            0.25),
}


@dataclass
class AdvocateAgent:
    advocate_id: str
    personality: str
    prep: float
    show: float
    honesty: float
    clash_p: float
    adjourned_free: int = 0     # times they got away with an on-the-day adjournment

    def day_probs(self, rng, cfg: dict, has_slot: bool, clustered: bool, n_today: int) -> tuple[float, float]:
        """(P shows up, P prepared) for one listed matter today, under the court's policy."""
        show, prep = self.show, self.prep
        if rng.random() < self.clash_p:                       # also listed in another courtroom
            show *= 0.92 if (has_slot and clustered) else 0.7  # a slot lets them plan; clustering = one trip
        if has_slot:
            show = min(0.99, show + 0.05)
        if clustered and n_today > 1:
            show = min(0.99, show + 0.03)
        if cfg.get("reminders"):
            prep = min(0.98, prep + 0.08)
        if cfg.get("adjournment_cost"):
            prep = min(0.98, prep + 0.10 * (self.personality != "diligent"))
        return show, prep

    def honest_now(self, cfg: dict) -> float:
        """P they admit 'need time' at the 2-day check instead of asking on the day."""
        h = self.honesty
        if cfg.get("adjournment_cost"):
            h = min(0.95, h + 0.35)   # admitting early is free, asking on the day costs
        return h

    def learn(self, outcome: str, cfg: dict) -> None:
        """Feedback: how the court responded changes next time's behaviour."""
        if outcome == "preparation":
            if cfg.get("adjournment_cost"):
                self.prep = min(0.98, self.prep + 0.08)        # it cost them -> prepare better next time
            else:
                self.adjourned_free += 1
                if self.personality != "diligent":
                    self.prep = max(0.25, self.prep - 0.03)    # it was free -> less reason to prepare
        elif outcome == "substantive":
            self.show = min(0.99, self.show + 0.01)            # the date meant something -> trust dates more
            if cfg.get("reminders"):
                self.prep = min(0.98, self.prep + 0.01)        # reminders build the habit


class AgentPool:
    def __init__(self, advocate_ids, seed: int = 0):
        self.agents = {}
        names = list(PERSONALITIES)
        shares = [PERSONALITIES[n][0] for n in names]
        for a in sorted(set(advocate_ids)):
            rng = np.random.default_rng(zlib.crc32(f"{a}:{seed}".encode()))
            kind = rng.choice(names, p=shares)
            _, prep, show, honest, clash = PERSONALITIES[kind]
            self.agents[a] = AdvocateAgent(a, kind, prep, show, honest, clash)
        self.mean_prep = float(np.mean([g.prep for g in self.agents.values()]))
        self.mean_show = float(np.mean([g.show * (1 - g.clash_p * 0.3) for g in self.agents.values()]))

    def get(self, advocate_id) -> AdvocateAgent:
        return self.agents[advocate_id]

    def multipliers(self, advocate_id, rng, cfg, has_slot, clustered, n_today) -> tuple[float, float]:
        """(attendance-failure multiplier, preparation-failure multiplier) relative to the population."""
        show, prep = self.get(advocate_id).day_probs(rng, cfg, has_slot, clustered, n_today)
        return (1 - show) / (1 - self.mean_show), (1 - prep) / (1 - self.mean_prep)

    def mix(self) -> dict:
        out = {}
        for g in self.agents.values():
            out[str(g.personality)] = out.get(str(g.personality), 0) + 1
        return out


# Backwards-compatible helper (v0 API)
def attendance_multiplier(rng, has_slot: bool, same_advocate_today: int, clustered: bool) -> float:
    m = 1.0
    if rng.random() < 0.25:
        m *= 1.1 if (has_slot and clustered) else 1.6
    if has_slot:
        m *= 0.85
    if same_advocate_today > 1 and clustered:
        m *= 0.9
    return m
