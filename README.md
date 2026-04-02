# SRA Tracker

A lightweight vendor Security Risk Assessment tracker built with Flask + SQLite.

## Setup (one time)

1. Open a terminal and navigate to this folder:
   ```
   cd sra_tracker
   ```

2. Install Flask:
   ```
   pip install flask
   ```

3. Run the app:
   ```
   python app.py
   ```

4. Open your browser and go to:
   ```
   http://localhost:5000
   ```

## Features

- Create a new SRA for any vendor
- Track which documents have been received (SOC2, HIPAA Risk Assessment, Data Flow Diagram, Vuln Assessment, MDS2)
- Copy pre-written outreach email with one click
- Auto-generates follow-up email based on missing documents
- Notes section per vendor (copy into ServiceNow)
- Dashboard shows all active SRAs with status and doc progress
- Status auto-updates as documents are marked received

## To stop the app
Press Ctrl+C in the terminal.
