"""Keyword lexicon for the four project topics, shared by complaints and recalls.

Each topic is a list of regexes applied to lowercased text; a document gets the
topic if any regex matches (multi-label). Keep terms specific: a term that
fires on unrelated complaints ("screen", "sensor", "power") drowns the signal.
src/mine_text.py --audit prints how often each term fires so the list can be reviewed.
Dropped after the first audit as too generic: "check engine", "warning light", "software update".
A topic tag means the complaint talks about that area, not that the area is the defect ("engine"
appears in 19% of complaints).
"""
import re

TOPICS = {
    "powertrain": [
        r"\bengine\b", r"\btransmission\b", r"\bcvt\b", r"\bdct\b", r"\bclutch\b",
        r"\b(lost|loss of|losing|reduced|no) (drive )?power\b", r"\blimp mode\b",
        r"\bstall(ed|ing|s)?\b", r"\bhesitat\w*", r"\bmisfir\w*",
        r"\bshift(ing|ed|s)? (hard|rough|erratic)\w*",
        r"\bunintended acceleration\b", r"\bsudden(ly)? accelerat\w*", r"\bdrive ?(train|shaft)\b",
        r"\baxle\b", r"\bturbo\w*", r"\bcatalytic\b", r"\bexhaust\b", r"\bfuel pump\b",
        r"\bfuel (leak|line|injector)\w*",
        r"\boil (leak|consumption|pressure|pump)\w*", r"\bcoolant\b", r"\boverheat\w*", r"\btiming chain\b",
        r"\b(connecting )?rod bearing\b", r"\bcrankshaft\b", r"\bpiston\b",
        r"\b(traction|drive) motor\b",
    ],
    "electrical": [
        r"\b12[ -]?v(olt)?\b", r"\bbattery\b", r"\biccu\b", r"\bintegrated charging control unit\b",
        r"\balternator\b", r"\bwiring\b", r"\bharness\b", r"\bfuse\b", r"\bshort circuit\w*", r"\belectrical\b",
        r"\b(would|will|did|does|could)(n't| not) start\b", r"\bno[- ]start\b", r"\bdead battery\b",
        r"\bparasitic\b", r"\binverter\b", r"\bbody control module\b", r"\bbcm\b", r"\bstarter\b",
        r"\bignition (switch|coil)\w*", r"\bcharging (system|port|issue|problem)\w*", r"\bheadlight\w*",
        r"\b(tail|brake|turn signal) ?lights?\b", r"\bpower window\w*",
    ],
    "infotainment": [
        r"\binfotainment\b", r"\bhead unit\b", r"\bradio\b", r"\btouch ?screen\b",
        r"\b(center|centre|navigation|nav|instrument|cluster|dash|display) (screen|display)\b",
        r"\bcar ?play\b", r"\bandroid auto\b", r"\bbluetooth\b", r"\bnavigation\b", r"\bgps\b",
        r"\b(back ?up|rear ?view|rear) camera\b", r"\bspeakers?\b", r"\bsound system\b", r"\baudio\b",
        r"\bblue ?link\b", r"\bentune\b", r"\bhonda ?link\b", r"\bsync\b",
        r"\bgauge cluster\b", r"\binstrument (cluster|panel)\b",
        r"\bover[- ]the[- ]air\b",
    ],
    "driver_assistance": [
        r"\badaptive cruise\b", r"\bsmart cruise\b", r"\bradar cruise\b",
        r"\blane (keep\w*|assist|departure|centering|centring)\b",
        r"\bcollision (avoidance|warning|mitigation)\b", r"\bforward collision\b",
        r"\bautomatic emergency brak\w*", r"\baeb\b", r"\bphantom brak\w*", r"\bblind[- ]spot\b",
        r"\bautopilot\b", r"\bfull self[- ]driving\b", r"\bfsd\b", r"\badas\b",
        r"\bparking (assist|sensor)\w*", r"\bhighway driving assist\b", r"\bpre[- ]collision\b",
        r"\bbraking (on its own|by itself|for no reason)\b",
        r"\bsafety sense\b", r"\bhonda sensing\b",
    ],
}

COMPILED = {t: [re.compile(p) for p in pats] for t, pats in TOPICS.items()}
COMBINED = {t: re.compile("|".join(f"(?:{p})" for p in pats)) for t, pats in TOPICS.items()}
