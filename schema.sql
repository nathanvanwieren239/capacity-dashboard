-- Launch tracker schema.
--
-- SQLite has no date type; dates are stored as ISO-8601 TEXT (YYYY-MM-DD),
-- which sorts and compares correctly as text. Empty dates are NULL.
--
-- Column names match the CSV contract exactly, so the model layer above is
-- unchanged by the move from files to a database.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id            TEXT PRIMARY KEY,
    project_name          TEXT NOT NULL DEFAULT '',
    customer_part_number  TEXT NOT NULL DEFAULT '',
    description           TEXT NOT NULL DEFAULT '',
    project_type          TEXT NOT NULL DEFAULT 'Launch',
    launch_type           TEXT NOT NULL DEFAULT 'Full',
    family                TEXT NOT NULL DEFAULT '',
    plant                 TEXT NOT NULL DEFAULT '',
    div                   TEXT NOT NULL DEFAULT '',
    customer              TEXT NOT NULL DEFAULT '',
    sales_person          TEXT NOT NULL DEFAULT '',
    gate_zero_corp        TEXT NOT NULL DEFAULT '',
    program_manager       TEXT NOT NULL DEFAULT '',
    job_number            TEXT NOT NULL DEFAULT '',
    qmsi_number           TEXT NOT NULL DEFAULT '',
    qmsi_revision         TEXT NOT NULL DEFAULT '',
    opportunity_number    TEXT NOT NULL DEFAULT '',
    rpn                   INTEGER NOT NULL DEFAULT 0,
    peak_annual_sales     REAL NOT NULL DEFAULT 0,
    launch_process        TEXT NOT NULL DEFAULT '',
    support_required      TEXT NOT NULL DEFAULT '',
    launch_risk           TEXT NOT NULL DEFAULT '',
    qmsi_capex            REAL NOT NULL DEFAULT 0,
    cer_amount            REAL NOT NULL DEFAULT 0,
    cer_status            TEXT NOT NULL DEFAULT '',
    cer_number            TEXT NOT NULL DEFAULT '',
    gate_zero_date        TEXT,
    ppap_target_date      TEXT,
    sop_target_date       TEXT,
    project_status        TEXT NOT NULL DEFAULT 'Green',
    project_phase         TEXT NOT NULL DEFAULT 'In-Process',
    prr_count             INTEGER NOT NULL DEFAULT 0,
    prr_amount_first_year REAL NOT NULL DEFAULT 0,
    prr_start_date        TEXT,
    prr_end_date          TEXT,
    main_risk_comments    TEXT NOT NULL DEFAULT '',
    notes                 TEXT NOT NULL DEFAULT ''
);

-- A gate belongs to exactly one project. Deleting a project takes its gates
-- with it, which is a class of orphaned-row bug that CSVs could not prevent.
CREATE TABLE IF NOT EXISTS gates (
    project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    gate_no         INTEGER NOT NULL,
    gate_code       TEXT NOT NULL,
    gate_name       TEXT NOT NULL DEFAULT '',
    plan_date       TEXT,
    adjusted_date   TEXT,
    actual_date     TEXT,
    qa_lab_hours    REAL NOT NULL DEFAULT 0,
    status_override TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, gate_no)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT '',
    action     TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    field      TEXT NOT NULL DEFAULT '',
    old_value  TEXT NOT NULL DEFAULT '',
    new_value  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_gates_project ON gates(project_id);
CREATE INDEX IF NOT EXISTS idx_gates_code    ON gates(gate_code);
CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_time    ON audit_log(timestamp);
