# CampusWatt — Campus Energy Load Forecasting and Peak Reduction System

CampusWatt is a full-stack campus energy management and optimization system designed to forecast electricity demand, identify peak load windows, and recommend rule-based peak reduction actions.

## Features

- **Dashboard**: High-level campus KPIs (total kWh, cost, peak demand, current demand, estimated & measured savings), 48-hour demand ribbon, consumption breakdown, and building comparisons.
- **Energy Analytics**: Multi-building filtering, granularity selection (hourly, daily, weekly, monthly), sortable metrics table, and automated $z$-score usage anomaly detection.
- **Load Forecasting**: Additive Holt-Winters triple exponential smoothing with weekly seasonality ($m=168$ for hourly, $m=7$ for daily), automated grid search backtesting minimizing hold-out MAE, and 95% confidence intervals.
- **Peak Reduction & Optimization**: Automated peak window identification against configurable kW thresholds, generating load shifting actions (EV charging shift, laboratory deferral, HVAC pre-cooling & set-point trimming, low-occupancy lighting trims).
- **Campus & Data Management**: Building and energy reading CRUD, CSV bulk import with row-level validation and duplicate detection, and data quality audits.
- **Reports & Settings**: Dynamic Daily, Weekly, and Monthly reports with CSV export and printable formatting, configurable energy tariffs, demand charges, and alert scans.

## Architecture

- **Frontend**: Clean single-page application (`frtnd.html`) with hand-crafted SVG charts, responsive layouts, modals, and toasts.
- **Backend**: Python FastAPI REST API with structured service, analytics, forecasting, and reporting layers.
- **Database**: Relational database via SQLAlchemy ORM (SQLite for initial deployment with WAL mode enabled; PostgreSQL migration ready).

## Setup & Running

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Seed Database (Optional)
To populate the database with a 90-day demonstration dataset across 6 campus buildings:
```bash
python seed.py
```

### 3. Start Application
```bash
python run.py
```
Or with Uvicorn:
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Web App**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) or [http://127.0.0.1:8000/frtnd.html](http://127.0.0.1:8000/frtnd.html)
- **API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Testing
Run the backend automated test suite:
```bash
python test_backend.py
```
