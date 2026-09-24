# Samay — 10-minute demo script

**Start:** `cd submissions/samay && streamlit run app.py` → opens the sign-in page.

1. **The problem (30 s).** Today's court lists ~60 cases, reaches a third, moves ~9; the rest get a flat 60-day date.
2. **Court master → Files (1 min).** Upload the judge's Excel (`samples/sample_cases.xlsx`, the real 100 cases). Messy headers and dates are cleaned; a wrong file gets a clear message. Set the judge's leave.
3. **Court master → Judges (30 s).** Each bench's numbers: reached, moved, disposed vs today's rules.
4. **Sign in as Justice Sehgal → Today (2 min).** Timeline of the day; each row has time, 1st/2nd/deferred listing, 0–100 score, advocate and *why it is listed*. Bail first, old cases protected in the afternoon. Remove a case, approve, download the causelist.
5. **Cases (1.5 min).** Open ST/1261/2017: score 91.3 = age 35 + readiness 25 + disposal 13.5 + churn 9.8 + urgency 8. Status Eligible/Conditional and flags exactly as the scoring spec (100/100 cases match).
6. **Priority (1 min).** Drag the weights: scores re-rank live; age can never go below 20.
7. **Calendar (30 s).** Holidays and leave are non-sitting days; cases move to the next day with room.
8. **Insight (1 min).** Real 100 cases, 60 days: reached 49% → 97%; moving hearings/day 0.5 → 4.3; 5+ year cases moved 13% → 73%; disposed 5 → 54. At 3,000 cases: 3.2× disposals, wasted trips −87%.
9. **Court master → Run a day (1 min).** Record "A party absent": the next date follows the rule (shorter gap), never 60 days.
10. **Close (30 s).** One command, open source, only the court's own data; per-judge rules in config; L3 advocate agents in the analytics dashboard.

**Likely questions**
- *Why list fewer cases?* Listing what is ready and fits gives more hearings that move cases, and fewer wasted trips.
- *Won't old cases be ignored?* A protected share of each day (guardrail floor 30%), age weight ≥ 20, overdue 30+ days forced in.
- *Where do the numbers come from?* `data/` only; the score is the documented formula, verified case by case.
