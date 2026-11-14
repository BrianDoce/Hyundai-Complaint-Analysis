# Recall Radar: recommendation

Draft, built on NHTSA data as of 2026-11-01. Exploratory: thresholds are untuned since topics were added, and nothing is adjusted for fleet size yet.

## The question

Can public NHTSA complaints flag an emerging defect before it becomes a recall, and how long does each brand take to get from first warning signs to a recall? (Hyundai incl. Genesis, Kia, Toyota, Honda, Tesla.)

## Short answer

**Partly, and only for some defects.** Complaint spikes are a useful triage signal, not a predictor. They catch roughly one recall in ten, usually the high-volume, driver-visible kind, and when they do they fire about 7 to 9 months early. Most alerts do not end in a recall. We cannot say any brand is faster than another.

## Evidence

- **Coverage.** The detector warned on 162 of 1,127 recall campaigns where it could fire at all (14%), a median of 35 weeks before announcement. Another 449 campaigns sat on parts with too few complaints to test. Hit rate rises with complaint volume (event level, 2,239 testable events): 3% with under 5 complaints in the prior year, 4% at 5 to 14, 16% at 15 to 49, 22% at 50 or more.
- **Precision beats chance, modestly.** Of clean spike episodes (not triggered by an earlier recall), 14% on component series and 25% on text-topic series were followed by a recall in the same series within 12 months. A randomly chosen month does that 6% and 14% of the time. So alerts are 2 to 2.5 times better than chance, yet roughly 75 to 86% of alerts are not followed by a recall in that series.
- **Text mining added signal.** Topic series (powertrain, electrical, infotainment, driver assistance, tagged from complaint text) caught 45 recalls the component codes missed. NHTSA has no infotainment category; that topic only exists in the text.
- **Brands.** Warned share 12 to 19% and median lead 28 to 39 weeks, with overlapping ranges and 14 to 44 warned campaigns per brand. No reliable ranking. On the official path, a linked NHTSA investigation takes a median 22 weeks to become a recall (Hyundai 20, Toyota 23, Honda 24, Kia 31; Tesla has one case).
- **Worked example.** Ioniq 5 electrical/ICCU complaints were flagged in June 2023, 37 weeks before the March 2024 recall (24V204000). Later Ioniq 5 recalls in the same area were mostly not warned early (one in 2026 was flagged 22 weeks ahead; the Nov 2024 and 2025 ones were not flagged, possibly because the earlier episode never ended or a prior recall set off the surge).

## Recommendation

1. **Use it as a weekly watch list, not a forecast.** About 1 alert a week across all six makes (system + topic series, 2025-26). Review them with an engineer; expect about 1 in 4 to 1 in 7 to be followed by a recall.
2. **Start with high-volume alerts.** Hit rate rises with complaint volume (22% at 50+ prior-year complaints vs 3% under 5). Whether alerts where a component series and a text-topic series both fire are more reliable is a reasonable guess but untested.
3. **Pair it with NHTSA investigations.** Once an investigation opens on a model, plan for roughly 5 months to a recall.
4. **Do not publish a brand speed ranking** from this analysis.
5. **Do not rely on it for low-volume or non-driver-visible defects** (manufacturing escapes, small populations). Complaints cannot see them.

## Before anyone acts on this

- Re-tune thresholds on component + topic series only, with each level scored against its own chance rate.
- Normalize by sales (complaints per vehicle sold) so growth in a new model stops looking like a spike. Tesla figures will be estimates.
- Split series by model year, and validate the topic keyword list further (about half of sampled infotainment tags were clearly right).
- Backtest result lines are on pooled data; a clean held-out period is only 2021 onward.
