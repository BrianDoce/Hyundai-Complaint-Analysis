# Recall Radar: recommendation

Draft, built on NHTSA data as of 2026-11-01. Exploratory: thresholds were tuned on pre-2021 recalls and the gain on 2021+ data is within noise; nothing is adjusted for fleet size yet.

## The question

Can public NHTSA complaints flag an emerging defect before it becomes a recall, and how long does each brand take to get from first warning signs to a recall? (Hyundai incl. Genesis, Kia, Toyota, Honda, Tesla.)

## Short answer

**Partly, and only for some defects.** Complaint spikes are a useful triage signal, not a predictor. They catch roughly one recall in ten, usually the high-volume, driver-visible kind, and when they do they fire about 7 to 9 months early. Most alerts do not end in a recall. We cannot say any brand is faster than another.

## Evidence

- **Coverage.** The detector warned on 158 of 1,129 recall campaigns where it could fire at all (14%), a median of 35 weeks before announcement. Another 447 campaigns sat on parts with too few complaints to test. Hit rate rises with complaint volume (earlier cut, 2,239 testable events: 3% with under 5 complaints in the prior year, 4% at 5 to 14, 16% at 15 to 49, 22% at 50 or more).
- **Precision beats chance.** Of clean spike episodes (not triggered by an earlier recall), 16% on component series and 39% on text-topic series were followed by a recall in the same series within 12 months. A randomly chosen month does that 6% and 14% of the time. So alerts are 3 and 2.7 times better than chance (2021 onward: 16% vs 7% and 40% vs 19%, topic on only 50 episodes), yet roughly 6 in 10 topic alerts and 5 in 6 component alerts are not followed by a recall in that series.
- **Text mining added signal.** Topic series (powertrain, electrical, infotainment, driver assistance, tagged from complaint text) caught 57 recalls the component codes missed. NHTSA has no infotainment category; that topic only exists in the text.
- **Brands.** Median lead is 32 to 39 weeks and overlaps across brands. The share of recalls warned varies (Tesla 24%, Kia 9%) but that mostly reflects how many complaints a model draws. No reliable speed ranking. On the official path, a linked NHTSA investigation takes a median 22 weeks to become a recall (Hyundai 20, Toyota 23, Honda 24, Kia 31; Tesla has one case).
- **Worked example.** Ioniq 5 electrical/ICCU complaints were flagged in May 2023, 41 weeks before the March 2024 recall (24V204000). Later Ioniq 5 recalls in the same area were mostly not warned early, possibly because the earlier episode never ended or a prior recall set off the surge.

## Recommendation

1. **Use it as a weekly watch list, not a forecast.** About 1 alert a week across all six makes (system + topic series, 2025-26). Review them with an engineer; expect roughly 1 in 6 component alerts and 2 in 5 topic alerts to be followed by a recall.
2. **Start with high-volume alerts.** Hit rate rises with complaint volume (22% at 50+ prior-year complaints vs 3% under 5). Whether alerts where a component series and a text-topic series both fire are more reliable is a reasonable guess but untested.
3. **Pair it with NHTSA investigations.** Once an investigation opens on a model, plan for roughly 5 months to a recall.
4. **Do not publish a brand speed ranking** from this analysis.
5. **Do not rely on it for low-volume or non-driver-visible defects** (manufacturing escapes, small populations). Complaints cannot see them.

## Before anyone acts on this

- Re-tuning is done (component + topic series, each scored against its own chance rate) but the held-out gain was small; revisit after sales normalization.
- Normalize by sales (complaints per vehicle sold) so growth in a new model stops looking like a spike. Tesla figures will be estimates.
- Split series by model year, and validate the topic keyword list further (about half of sampled infotainment tags were clearly right).
- Backtest result lines are on pooled data; a clean held-out period is only 2021 onward.
