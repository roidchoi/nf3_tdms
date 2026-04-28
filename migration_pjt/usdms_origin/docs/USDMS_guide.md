# Reference : AI Assistant Guide for USDMS

**Last Updated:** 2025-12-18
**Version:** 5.0 (Phase 5 - Codebase Cleanup & Document Synchronization)
**Project:** USDMS (US Data Management System)

---

## 1. Project Overview

**USDMS** is a high-performance, institutional-grade US stock market data platform. It is designed to be autonomous, strictly Point-in-Time (PIT) compliant, and capable of generating deep quantitative factors from raw SEC XBRL filings.

### Core Philosophy
1.  **SEC Direct**: No reliance on 3rd party financial vendors. Sourced directly from SEC EDGAR.
2.  **PIT Compliance**: All financial data and derived metrics are indexed by `filed_dt` (filing date) to prevent look-ahead bias.
3.  **Raw & Re-calculation**: We store Raw Prices and actively calculate Adjustment Factors (Split/Dividend) to verify data integrity (KDMS Logic).
4.  **CIK Centric**: The `CIK` is the only immutable identifier. Tickers are treated as temporal attributes.

---

## 2. Directory Structure (As-Built)

The project structure is organized for modularity, separating **Collection** (I/O), **Processing** (Engines), and **Verification** (Auditors).

```
/home/roid2/pjt/ag/01_usdms/
│
├── backend/                          # Core Application Logic
│   ├── backend.Dockerfile            # Container definition
│   │
│   ├── collectors/                   # Data Acquisition & IO Layer
│   │   ├── master_sync.py            # [Core] SEC Ticker Sync & Noise Deletion
│   │   ├── financial_parser.py       # [Core] XBRL Parsing & Standardization
│   │   ├── market_data_loader.py     # OHLCV Collection (Iterative Adj Logic)
│   │   ├── sec_client.py             # SEC EDGAR API Wrapper
│   │   ├── db_manager.py             # Database Connection & Query Manager
│   │   ├── xbrl_mapper.py            # US-GAAP to Standard Field Mapping
│   │   ├── master_enricher.py        # Metadata enrichment (Sector, Industry)
│   │   └── kis_*.py                  # (Legacy) KIS API Wrappers
│   │
│   ├── engines/                      # Calculation Layer
│   │   ├── valuation_calculator.py   # [Core] Metric (PER/PBR) & PIT Calculator
│   │   └── price_engine.py           # Price Adjustment Factor Calculator
│   │
│   ├── auditors/                     # [New] Data Integrity & Verification
│   │   ├── financial_auditor.py      # Checks Accounting Identities (Assets=L+E)
│   │   ├── metric_auditor.py         # Reverse-calculates metrics to verify logic
│   │   └── price_auditor.py          # Verifies Price Reproduction
│   │
│   └── init/                         # Database Initialization
│       └── init.sql                  # Source of Truth Schema (v5.0)
│
├── ops/                              # Operational Entry Points (Scripts)
│   ├── run_daily_routine.py          # [Main] Daily Orchestrator (Steps 1-6)
│   ├── run_diagnostics.py            # On-demand System Health Check
│   ├── run_db_checkpoint.py          # DB Backup Utility
│   ├── kill_db_locks.py              # Emergency Lock Clearance
│   └── maintenance/                  # Ad-hoc Maintenance Tools
│       └── recollect_targets.py      # Manual re-collection utility
│
├── tests/                            # System Tests
│   ├── test_master_logic.py          # Ticker lifecycle logic tests
│   ├── sec_content_verifier.py       # SEC Content validation
│   └── ...
│
├── archive/                          # Deprecated / One-off Scripts
│   ├── legacy/                       # Old runners and backfill scripts
│   └── temp_trash/                   # POC code
│
├── docs/                             # Project Documentation
├── logs/                             # Execution Logs
├── .env                              # Credentials
└── docker-compose.yml                # Service Orchestration
```

---

## 3. Database Schema (Schema v5.0)

The database consists of **9 Core Tables** managed by TimescaleDB (PostgreSQL).

### A. Meta & History
| Table | PK | Description |
| :--- | :--- | :--- |
| **`us_ticker_master`** | `cik` | **Central Registry.** Stores constant metadata (Sector, Country) and current status (`active`, `collect_target`). |
| **`us_ticker_history`** | `cik`,`ticker`,`start` | **SCD Type 2.** Tracks ticker changes over time. Includes logic to delete intraday noise. |
| **`us_collection_blacklist`** | `cik` | **Exception Management.** Tracks 403 Forbidden, Parsing Failures, or Permanent Exclusions. |

### B. Market Data (KDMS Style)
| Table | PK | Description |
| :--- | :--- | :--- |
| **`us_daily_price`** | `dt`,`cik` | **Raw OHLCV.** Only stores raw prices. Use factors to adjust. (Hypertable) |
| **`us_price_adjustment_factors`** | `cik`,`event_dt` | **Factor Storage.** Splits and Dividends. `Adj Price = Raw * Factor`. |

### C. Financials (Deep Fundamental)
| Table | PK | Description |
| :--- | :--- | :--- |
| **`us_financial_facts`** | `fact_id` | **Raw XBRL Store.** EAV Model. Stores every single tag parsed from SEC filings. |
| **`us_standard_financials`** | `cik`,`period`,`filed` | **Analysis Ready.** Normalized into Standard columns (Revenue, EBITDA, FCF). Grouped by Fiscal Period. |
| **`us_share_history`** | `cik`,`filed_dt` | **PIT Shares.** Exact share count derived from 'Dei' tags for precise Market Cap calculation. |

### D. Derived Analytics
| Table | PK | Description |
| :--- | :--- | :--- |
| **`us_daily_valuation`** | `dt`,`cik` | **Daily Metrics.** PER, PBR, PSR, EV/EBITDA calculated daily using PIT financials. (Hypertable) |
| **`us_financial_metrics`** | `cik`,`period`,`filed` | **Quality Ratios.** ROE, ROA, Debt Ratio, GP/A. Stored per filing. |

---

## 4. Key Components & Logic

### 1. MasterSync (`backend/collectors/master_sync.py`)
*   **Role**: Keeps the Ticker Master up-to-date with SEC.
*   **Smart Resolution**: Handles "Ticker Flip-Flop" noise. If a ticker changes and reverts (or closes) on the same day (`start_dt > yesterday`), it is considered **Noise** and DELETED to keep the history clean.
*   **Enrichment**: Fetches Sector, Industry, and Market Cap from `yfinance` to determine `is_collect_target`.

### 2. MarketDataLoader (`backend/collectors/market_data_loader.py`)
*   **Iterative Adjustment**: Does not trust API "Adjusted Close". It fetches Split history, sorts by date, and iteratively applies ratios to previous data to "Reverse Engineer" the True Raw Price.
*   **Factor Generation**: Automatically detects discrepancies between Raw and Adjusted prices to generate entries in `us_price_adjustment_factors`.

### 3. FinancialParser (`backend/collectors/financial_parser.py`)
*   **Gap Processor**: Identify gaps in `us_financial_facts` since the last `MAX(filed_dt)`.
*   **Fiscal Grouping**: Groups scattered XBRL facts into logical `(Fiscal Year, Fiscal Period)` buckets.
*   **Period Logic**:
    *   **Balance Sheet**: Takes values from the "Instant" context at period end.
    *   **Income Statement**: Takes "Duration" values. For Q2/Q3, it calculates `Discrete = YTD_Current - YTD_Previous`.

### 4. ValuationCalculator (`backend/engines/valuation_calculator.py`)
*   **PIT Matching**: Uses `pandas.merge_asof(direction='backward')` to align:
    *   Price at `T`
    *   Financials known at `T` (based on `filed_dt`, NOT `report_period`)
*   **Metrics**: Calculates Market Cap, EV, and Valuation Ratios (PE, PB, PCR).

---

## 5. Operational Workflows

### Primary Routine (Automated)
The entire system is orchestrated by a single entry point.

```bash
# Activate Environment
conda activate usdms_env

# Run Daily Routine
# Includes: Master Sync -> Market Data -> Financials -> Valuation -> Health Check
python ops/run_daily_routine.py
```

### System Health Check (Manual/Weekly)
Run deep diagnostics to verify accounting identities and price reproduction.

```bash
# Run Auditors
python ops/run_diagnostics.py
```

### DB Maintenance
```bash
# Kill Blocking Locks
python ops/kill_db_locks.py

# Create Checkpoint (Backup)
python ops/run_db_checkpoint.py phase5
```

---

## 6. Development Conventions

1.  **Strict Typing**: All new Python code must use `Type Hints`.
2.  **AbsolutePath**: Always use absolute paths or `sys.path.append` relative to project root in scripts.
3.  **Environment**: Secrets must be loaded from `.env` using `dotenv`.
4.  **Logging**: All modules must log to `logs/` directory with `logging.basicConfig`.
5.  **Docs First**: Update `Task.md` and `Implementation Plan` BEFORE writing code.
