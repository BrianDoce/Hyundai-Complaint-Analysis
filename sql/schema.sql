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


-- TODO: hand-collected from automaker press releases (Tesla does not report by model: document estimates)
CREATE TABLE IF NOT EXISTS sales (
    make TEXT NOT NULL, model TEXT NOT NULL, calendar_year INTEGER NOT NULL,
    units_sold INTEGER NOT NULL, source_url TEXT,
    PRIMARY KEY (make, model, calendar_year)
);

-- Months flagged by src/detect_spikes.py, at two resolutions (`level`: 'system' or 'subsystem').
-- One row per (make, model, series, month) whose trailing complaint count is far above that series' own
-- baseline. `series` is component_map.system or component_map.subsystem depending on level. Rebuilt every run.
CREATE TABLE IF NOT EXISTS spikes (
    level       TEXT NOT NULL,
    make        TEXT NOT NULL,
    model       TEXT NOT NULL,
    series      TEXT NOT NULL,
    month       TEXT NOT NULL,  -- YYYY-MM, last month of the window
    window_n    INTEGER NOT NULL, -- distinct complaints in the window
    expected    REAL NOT NULL,    -- window count expected from the baseline
    ratio       REAL NOT NULL,    -- window_n / expected
    p_value     REAL NOT NULL,    -- Poisson upper tail P(X >= window_n)
    onset       INTEGER NOT NULL, -- 1 if the previous month was not flagged (start of an episode)
    PRIMARY KEY (level, make, model, series, month)
);

-- One row per recall event (campaign x make x model x subsystem), scored by src/backtest.py:
-- did the spike detector flag that series before the recall, and how early?
CREATE TABLE IF NOT EXISTS backtest (
    campno          TEXT NOT NULL,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    system          TEXT NOT NULL,
    subsystem       TEXT NOT NULL,
    report_date     DATE NOT NULL,
    eligible        INTEGER NOT NULL, -- 1 if the detector could have fired at either level
    level           TEXT,             -- level of the flag used (NULL if none)
    first_flag      TEXT,             -- YYYY-MM of the qualifying flag in the lookback
    lead_weeks      REAL,             -- weeks from the end of that month to report_date
    clean           INTEGER,          -- 1 if no other recall hit that series in the 6 months before the flag
    PRIMARY KEY (campno, make, model, subsystem)
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
