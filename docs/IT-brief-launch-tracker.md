# Launch Tracker — technical brief

**For:** Mike Chambers, IT
**From:** Nathan Van Wieren, Technical Business Development Engineer
**Date:** 23 August 2026
**Status:** Working prototype on synthetic data. Seeking guidance on internal hosting.

---

## 1. What it is

A small internal web application that replaces the reporting layer of the
**Gate Zero / Project Launch Tracker** Excel workbook — the one currently used
for the monthly launch reviews.

The workbook has grown to the point where cross-sheet formulas and conditional
formatting make it lock up during the meetings it supports. The application
reads the same data, shows launch gate status on a timeline, calculates the
on-time and PRR metrics, and lets a small number of authorised people record
gate dates directly.

Intended scope is the three Michigan plants, with roughly **six editors** and
**twenty to thirty viewers**.

---

## 2. Technical profile

| | |
|---|---|
| **Language / runtime** | Python 3.10+ |
| **Framework** | Streamlit (web UI served over HTTP) |
| **Dependencies** | streamlit, pandas, numpy, plotly, openpyxl — all standard PyPI packages, pinned in `requirements.txt`. No compiled or unusual dependencies. |
| **Process model** | Single process, single port (default 8501) |
| **Database** | SQLite — one file on disk. **No database server required.** |
| **Current data size** | 60 KB. Expected to remain under 10 MB with several years of history. |
| **Codebase** | ~5,200 lines across 16 files |
| **Outbound network** | None at runtime. Streamlit usage telemetry is disabled in config. |
| **Inbound** | HTTP from the internal network only |
| **Licensing** | None. All components are open source and free. Nothing to purchase. |
| **Data classification** | Internal — customer names, part numbers, launch schedules, peak annual sales |

---

## 3. What I'm asking for

| # | Request | Notes |
|---|---|---|
| 1 | **Somewhere internal to run it** | Small VM or a container on existing infrastructure. Sizing is not a concern — 1 vCPU / 2 GB is ample. |
| 2 | **Persistent storage for the `data/` directory** | See the note below — this is the one I'd most like to get right. |
| 3 | **A backup destination away from the host** | Either include the `data/` directory in the existing backup regime, or provide a network path I can mirror snapshots to. Either works. |
| 4 | **Identity for six editors** *(nice to have)* | Is registering an app in Entra ID (or equivalent) straightforward here? Viewers can remain on a shared read-only credential. Not a blocker — see section 6. |
| 5 | **A named IT contact** | Someone who knows how it's deployed and could restart or restore it if I'm unavailable. |

### ⚠️ The one technical detail I'd flag

**If this is containerised, the `data/` directory must be on a mounted volume,
not inside the container image.**

Containers are rebuilt on each deployment, so anything written inside one is
lost on redeploy. The application would appear to work normally and then
silently lose all data entered since the previous deployment. Flagging it
early because the failure is quiet and delayed rather than obvious.

---

## 4. What it does *not* need

- No database server (SQL Server, Postgres, etc.)
- No licences or purchases
- No integration with other systems (at this stage)
- No inbound access from outside the network
- No shared drives, service accounts, or scheduled jobs beyond one optional
  backup task
- No specialised hardware or high availability

---

## 5. What's already handled

Listed so you know what you would and wouldn't be inheriting.

**Storage integrity.** All writes run inside SQLite transactions. Concurrent
editors are serialised correctly — verified under 20 simultaneous writes with
the full change history intact. Foreign keys are enforced.

**Backups.** The application snapshots itself on a configurable interval
(hourly recommended), storing both a database copy and CSV exports of every
table. Each snapshot runs a SQLite integrity check on write. Retention is 30
recent snapshots plus first-of-month for 24 months.

**Restore.** Tested end to end — the database and all working files were
deleted and the system rebuilt from a snapshot's CSVs alone, with every record
and the full audit history recovered identically. There's a restore function
in the UI and a command-line equivalent.

**Audit trail.** Every change is recorded with timestamp, user role, field,
and both old and new values. Append-only.

**Access control.** Two roles today — read-only and editor — behind separate
passwords, on the internal network only. Editors get the data entry and
editing functions; viewers cannot modify anything. The perimeter handles
external access; what the shared passwords do not give is per-person
attribution in the audit log, which is the reason for request #4 rather than
any exposure concern.

**Data handling during development.** The version currently running on
Streamlit's public cloud contains **entirely synthetic data**. All real part
numbers, customer names and figures were replaced before anything was hosted
externally. Real data has never left the building.

**Documentation.** Architecture, data model, deployment and recovery
procedures are written up. Data exports to plain CSV, readable independently
of this application. The storage layer is isolated to a single module, so
moving to a corporate database later would be a substitution rather than a
rewrite.

---

## 6. Risks, and how they're addressed

| Risk | Mitigation |
|---|---|
| Data loss from hardware or host failure | Hourly snapshots; needs an off-host destination — request #3 |
| Data loss from user error or bad import | Snapshot before every write; tested restore |
| Silent data loss via container redeploy | Mounted volume — the flag in section 3 |
| Backup silently failing | Every snapshot self-verifies; backup health is displayed in the app |
| Unauthorised edits from outside | Internal network only; remote access already requires VPN with corporate credentials |
| Unauthorised edits from inside | Role separation and a full audit trail. The residual gap is that a shared editor password can be passed around, and the audit log then records the role rather than the person. SSO would close it — request #4 |
| Access after a role change | More likely than a departure: the account stays active and VPN still works, but the person should no longer be editing. Named identity is the only real fix |
| Sole maintainer / continuity | Documented, CSV-exportable, isolated storage layer. Request #5 helps further |
| Sensitive data exposure | Internal hosting only; synthetic data used for all external testing |

---

## 7. Questions for you

1. What's the standard way an internal web application gets hosted here — is
   there a VM platform or container environment I should be targeting?
2. How does backup work for that platform? Can an application's data directory
   be included, or should I write snapshots to a share that's already covered?
3. Is single sign-on for an internal web app straightforward here?
4. What's the expectation on patching — do you handle the OS and I handle the
   application, or would you prefer a different split?
5. **If this ended up being used across all three plants, what would you want
   to see from me before you'd be comfortable with that?**

---

## 8. Support expectations

I maintain it. It is business-useful rather than business-critical: if it were
unavailable for a day, the plants would work from the most recent export and
re-enter afterwards. There's no expectation of out-of-hours support or a
formal SLA.

The continuity question is a fair one, so to be direct about it: the data
exports to CSV and is readable without this application, the deployment and
recovery procedures are documented, and the storage layer is deliberately
isolated so it could be repointed at a corporate database without rewriting
anything else.

---

## 9. Where it stands and what happens next

The application is functionally complete and running on synthetic data. Before
it carries real information it needs internal hosting, and before it replaces
the spreadsheet it needs one full monthly review cycle run in parallel at each
plant.

I'm not asking for a commitment today — I'd like to understand what's
realistic so I don't propose something the infrastructure can't support. Happy
to demonstrate it whenever convenient; it runs on my laptop.

**Nathan Van Wieren** · Technical Business Development Engineer
