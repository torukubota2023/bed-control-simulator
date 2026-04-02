#!/bin/bash
PORT=${PORT:-8504}
exec /tmp/bed_control_env/bin/streamlit run "$(dirname "$0")/bed_control_simulator_app.py" \
  --server.headless true \
  --server.port "$PORT"
