"""Text-mine complaint and recall descriptions into `complaint_text` / `recall_text`.

Per distinct complaint (odino): keyword topic tags (src/topics.py, multi-label)
and a VADER sentiment score. Per recall campaign: the same topic tags on the
defect description. Re-running replaces both tables.

Notes: pre-2020 complaints are ALL CAPS, so text is lowercased first for both
the lexicon and VADER (VADER treats caps as emphasis, which would make old
complaints look angrier than new ones). Sentiment in complaints is almost
uniformly negative; treat it as an intensity signal, not a classifier.
`--audit` prints how often each lexicon term fires instead of writing tables.

Usage:
    python src/mine_text.py data/recall_radar.db [--audit]
"""
import re
import sqlite3
import warnings
import sys
from pathlib import Path

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from topics import COMBINED, COMPILED, TOPICS

warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")

REDACTED = re.compile(r"\bxxx+\b", re.I)


def clean(s):
    return REDACTED.sub(" ", (s or "").lower())


def tag(texts):
    return pd.DataFrame({t: texts.str.contains(rx).astype(int) for t, rx in COMBINED.items()})


def audit(texts):
    n = len(texts)
    for topic, rxs in COMPILED.items():
        print(f"\n{topic}: {int(texts.str.contains(COMBINED[topic]).sum()):,} of {n:,}")
        counts = sorted(((int(texts.str.contains(rx).sum()), rx.pattern) for rx in rxs), reverse=True)
        for c, pat in counts:
            print(f"   {c:7,}  {pat}")


def main(db_path, do_audit):
    con = sqlite3.connect(db_path)
    d = pd.read_sql_query("SELECT odino, MIN(description) AS description FROM complaints GROUP BY odino", con)
    d["text"] = d["description"].map(clean)
    if do_audit:
        audit(d["text"])
        return
    tags = tag(d["text"])
    sia = SentimentIntensityAnalyzer()
    sent = [sia.polarity_scores(t)["compound"] if t.strip() else None for t in d["text"]]
    out = pd.concat([d[["odino"]], tags], axis=1)
    out["sentiment"] = sent
    out["n_chars"] = d["text"].str.len()

    r = pd.read_sql_query("SELECT campno, MIN(summary) AS summary FROM recalls GROUP BY campno", con)
    rt = pd.concat([r[["campno"]], tag(r["summary"].map(clean))], axis=1)

    con.execute("DROP TABLE IF EXISTS complaint_text")
    con.execute("DROP TABLE IF EXISTS recall_text")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO complaint_text VALUES (?,?,?,?,?,?,?)",
                    [tuple(None if pd.isna(v) else v for v in row) for row in out.itertuples(index=False)])
    con.executemany("INSERT INTO recall_text VALUES (?,?,?,?,?)", rt.itertuples(index=False))
    con.commit()
    print(f"{len(out):,} complaints, {len(rt):,} recall campaigns tagged -> {db_path}")
    print(out[list(TOPICS)].mean().round(3).to_string())
    print(f"any topic: {(out[list(TOPICS)].sum(axis=1) > 0).mean():.1%}; mean sentiment {out['sentiment'].mean():.2f}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], "--audit" in sys.argv)
