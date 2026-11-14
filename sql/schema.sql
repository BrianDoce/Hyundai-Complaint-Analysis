-- Recall Radar schema (SQLite). Join keys across tables: make, model, year, component.
-- Complaints are one row per (complaint, component), matching the NHTSA grain:
-- count complaints with COUNT(DISTINCT odino), not rows.

CREATE TABLE IF NOT EXISTS complaints (
    odino        TEXT NOT NULL,
    make         TEXT NOT NULL,
    model        TEXT NOT NULL,
    model_year   INTEGER,
    received     DATE,          -- LDATE: date NHTSA received it (use for spike detection)
    fail_date    DATE,
    component    TEXT,          -- raw COMPDESC, may list several "A:B:C" levels
    crash        TEXT,
    fire         TEXT,
    injured      INTEGER,
    deaths       INTEGER,
    miles        INTEGER,
    description  TEXT,          -- CDESCR, input to NLP topics/sentiment
    source_file  TEXT
);
CREATE INDEX IF NOT EXISTS ix_complaints_key ON complaints (make, model, model_year, component);
CREATE INDEX IF NOT EXISTS ix_complaints_received ON complaints (received);

-- TODO: load from RCL.txt
CREATE TABLE IF NOT EXISTS recalls (
    campno       TEXT NOT NULL,   -- e.g. 24V200000
    make         TEXT NOT NULL,
    model        TEXT NOT NULL,
    model_year   INTEGER,
    component    TEXT,
    report_date  DATE,            -- announcement date used for recall latency
    summary      TEXT
);

-- Loaded from FLAT_INV.txt by src/ingest_investigations.py
CREATE TABLE IF NOT EXISTS investigations (
    nhtsa_id     TEXT NOT NULL,   -- e.g. PE24012
    make         TEXT NOT NULL,
    model        TEXT NOT NULL,
    model_year   INTEGER,
    component    TEXT,
    open_date    DATE,
    close_date   DATE,
    campno       TEXT,            -- recall campaign this investigation led to, if any (joins recalls.campno)
    subject      TEXT
);


-- US calendar-year unit sales by model, loaded from data/sales/us_sales.csv by src/ingest_sales.py.
-- Hand-collected: every row needs a source_url. Tesla does not report by model, so its rows are estimates
-- and must have is_estimate = 1.
CREATE TABLE IF NOT EXISTS sales (
    make TEXT NOT NULL, model TEXT NOT NULL, calendar_year INTEGER NOT NULL,
    units_sold INTEGER NOT NULL, source_url TEXT NOT NULL, is_estimate INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (make, model, calendar_year)
);

-- One row per recall campaign, from src/latency.py. lead_weeks = spike-detector warning before the
-- announcement (NULL = no warning); inv_latency_wk = linked investigation open date -> announcement.
CREATE TABLE IF NOT EXISTS recall_latency (
    campno           TEXT NOT NULL,
    make             TEXT NOT NULL,
    report_date      DATE NOT NULL,
    component_group  TEXT NOT NULL,
    eligible         INTEGER NOT NULL,  -- 1 if the detector could have fired (enough complaints/history)
    flagged          INTEGER NOT NULL,
    lead_weeks       REAL,
    inv_latency_wk   REAL,
    PRIMARY KEY (campno, make)
);

-- Text-mined features per complaint (one row per distinct odino), from src/mine_text.py.
-- Topics are keyword-tagged from the free-text description (multi-label), independent of NHTSA's
-- component codes, so e.g. infotainment faults filed under ELECTRICAL SYSTEM are still found.
CREATE TABLE IF NOT EXISTS complaint_text (
    odino              TEXT PRIMARY KEY,
    powertrain         INTEGER NOT NULL,
    electrical         INTEGER NOT NULL,
    infotainment       INTEGER NOT NULL,
    driver_assistance  INTEGER NOT NULL,
    sentiment          REAL,        -- VADER compound on lowercased text, -1 (negative) to 1
    n_chars            INTEGER NOT NULL
);

-- Same topic tags for recalls, from the defect description, one row per campaign.
CREATE TABLE IF NOT EXISTS recall_text (
    campno             TEXT PRIMARY KEY,
    powertrain         INTEGER NOT NULL,
    electrical         INTEGER NOT NULL,
    infotainment       INTEGER NOT NULL,
    driver_assistance  INTEGER NOT NULL
);

-- Maps every distinct raw component string in complaints/recalls/investigations (exact text, as stored)
-- to a normalized `system` (level-1 name made consistent across tables) and one of 5 topic buckets.
-- Built by src/build_component_map.py. NHTSA has no infotainment category: that bucket is a rough
-- proxy (instrument cluster, rear-camera display, communication); text mining refines it later.
CREATE TABLE IF NOT EXISTS component_map (
    raw_component   TEXT PRIMARY KEY,
    system          TEXT NOT NULL,  -- e.g. ENGINE, SERVICE BRAKES, FUEL SYSTEM, OTHER
    subsystem       TEXT NOT NULL,  -- system plus NHTSA's second level, e.g. ELECTRICAL SYSTEM:SOFTWARE
    component_group TEXT NOT NULL   -- powertrain | electrical | infotainment | driver_assistance | other
);
