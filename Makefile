# ベッドコントロールアプリ QA ハーネス
#
# 使い方: make qa
# 台本 ↔ 実アプリ の数値整合性を自動チェックしてレポートを生成

PYTHON := .venv/bin/python3
REPORTS_DIR := reports

.PHONY: help qa qa-claims qa-playwright qa-internal qa-realism qa-report qa-clean

help:
	@echo "ベッドコントロール QA ハーネス"
	@echo ""
	@echo "  make qa             — 全チェック実行（推奨）"
	@echo "  make qa-claims      — 台本から数値主張を抽出"
	@echo "  make qa-playwright  — Playwright で DOM 照合"
	@echo "  make qa-internal    — アプリ内 整合性テスト（pytest）"
	@echo "  make qa-realism     — デモデータ 現実性・教育性テスト（pytest）"
	@echo "  make qa-report      — 統合レポート生成"
	@echo "  make qa-clean       — 生成レポートを削除"

qa: qa-claims qa-playwright qa-internal qa-realism qa-report
	@echo ""
	@echo "✅ QA 完走。レポート: $(REPORTS_DIR)/scenario_qa_report_*.md"

qa-claims:
	@echo "[1/5] 台本から数値主張を抽出中..."
	$(PYTHON) scripts/extract_scenario_claims.py

qa-playwright: qa-claims
	@echo "[2/5] Playwright で DOM 照合中..."
	npx playwright test playwright/test_scenario_qa.spec.ts

qa-internal:
	@echo "[3/5] アプリ内 整合性テスト中..."
	$(PYTHON) -m pytest tests/test_app_internal_consistency.py -v

qa-realism:
	@echo "[4/5] デモデータ 現実性・教育性テスト中..."
	$(PYTHON) -m pytest tests/test_demo_data_quality.py -v

qa-report: qa-playwright qa-internal qa-realism
	@echo "[5/5] 統合レポート生成中..."
	$(PYTHON) scripts/generate_qa_report.py

qa-clean:
	rm -rf $(REPORTS_DIR)
	@echo "🧹 $(REPORTS_DIR)/ を削除しました"
