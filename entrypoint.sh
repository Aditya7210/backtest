#!/bin/sh
set -e

echo "Starting instrument update..."
python Dashboard/Backtesting_page/Features/instrument_mapper_updater.py || true

echo "Starting Streamlit..."
exec streamlit run Dashboard/dashboard.py --server.port=8501 --server.address=0.0.0.0
