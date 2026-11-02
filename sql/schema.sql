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

-- TODO: load from investigations flat file
CREATE TABLE IF NOT EXISTS investigations (
    nhtsa_id     TEXT NOT NULL,   -- e.g. PE24012
    make         TEXT NOT NULL,
    model        TEXT NOT NULL,
    model_year   INTEGER,
    component    TEXT,
    open_date    DATE,
    subject      TEXT
);

-- TODO: hand-collected from automaker press releases (Tesla does not report by model: document estimates)
CREATE TABLE IF NOT EXISTS sales (
    make TEXT NOT NULL, model TEXT NOT NULL, calendar_year INTEGER NOT NULL,
    units_sold INTEGER NOT NULL, source_url TEXT,
    PRIMARY KEY (make, model, calendar_year)
);

-- Maps NHTSA's free-text component strings to a small stable set, plus the NLP topic buckets.
CREATE TABLE IF NOT EXISTS component_map (
    raw_component TEXT PRIMARY KEY,
    component_group TEXT NOT NULL  -- powertrain | electrical | infotainment | driver_assistance | other
);
