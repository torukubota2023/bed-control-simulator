import { defineConfig } from '@playwright/test';
import { config } from 'dotenv';

config({ override: true });

export default defineConfig({
  testDir: './playwright',
  timeout: 120000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:8501',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: '[ -x .venv/bin/streamlit ] && .venv/bin/streamlit run scripts/bed_control_simulator_app.py --server.port 8501 --server.headless true || streamlit run scripts/bed_control_simulator_app.py --server.port 8501 --server.headless true',
    port: 8501,
    timeout: 120000,
    reuseExistingServer: true,
  },
});
