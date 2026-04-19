# シナリオ QA レポート

**生成日:** 2026-04-19T08:57:25
**対象台本:** 4 本 (61 クレーム抽出)
**対象アプリ:** ベッドコントロール（commit `79d47a6`）
**総合判定:** **NG**

## 判定理由

- 台本と実アプリの重大ズレ 1 件

## 1. 台本 ↔ 実アプリ 数値一致（Playwright）

- 実行時刻: 2026-04-18T23:57:23.559Z
- 対象クレーム数: 61（PASS 20 / FAIL 1 / SKIPPED 37 / MISSING_TESTID 0 / MISSING_DOM 3）

### 重大不一致（0 件）
なし。

### 軽微ズレ（1 件）
1. `docs/admin/demo_scenario_v3.6.md:L366` occupancy_pct — 実 85 vs 台本 88.8（ズレ -3.80、許容 ±1.5）

### Playwright 側で照合できなかった項目（3 件）
- DOM 値パース不可: 3 件
_これらは pytest 側の `tests/test_app_internal_consistency.py` で補完的に検証しています。_


## 2. アプリ内 整合性（pytest）

- pytest 結果: **OK** — 16 pass, 0 fail, 0 error, 0 skip

## 3. デモデータ 現実性

| 指標 | 実測 | 期待 | 判定 |
|------|------|------|------|
| 5F 稼働率 | 85.9% | 70-95%, σ=9.2 | ✓ |
| 6F 稼働率 | 97.1% | 80-100%, σ=7.1 | ✓ |
| 5F ALOS | 13.2日 | 10-25 日 | ✓ |
| 6F ALOS | 20.5日 | 10-30 日 | ✓ |
| 救急比率 | 19.1% | 5-40% | ✓ |
| 短手3 比率 | 14.2% | 10-22% | ✓ |
| 稼働率変動 (5F σ) | 9.2% | ≥3% | ✓ |

pytest 総合: **OK**（23/23 pass, 0 fail）

## 4. デモデータ 教育性（推奨調整）

- 稼働率の日次変動: 5F σ=9.2%, 6F σ=7.1%
  - 変動幅は判断材料として十分 (±σ が稼働率の 5% 以上を推奨)
- 稼働率レンジ: 5F=55.3〜110.6%, 6F=72.3〜110.6%

## 5. 抽出クレーム内訳（参考）

### ファイル別クレーム数

| ファイル | 件数 |
|----|----|
| `docs/admin/carnf_scenario_v1.md` | 15 |
| `docs/admin/demo_scenario_v3.6.md` | 28 |
| `docs/admin/presentation_script_bedcontrol.md` | 14 |
| `docs/admin/slides/weekend_holiday_kpi/script.md` | 4 |

### 指標別クレーム数

| 指標 | 件数 |
|----|----|
| holiday_banner_threshold_days | 20 |
| emergency_pct | 14 |
| occupancy_pct | 5 |
| alos_limit_days | 4 |
| occupancy_target_pct | 3 |
| patient_count_rows | 3 |
| revenue_per_1pct_manyen | 3 |
| alos_days | 2 |
| status_count_normal | 2 |
| c_group_contribution_yen | 2 |
| revenue_per_empty_bed_day_yen | 1 |
| friday_discharge_pct | 1 |
| emergency_threshold_pct | 1 |

## 総評

以下の項目を優先して修正してください。
- 台本と実アプリの重大ズレ 1 件

修正後、再度 `npm run qa` を実行してください。

---

_このレポートは `scripts/generate_qa_report.py` が自動生成したものです。台本を更新した際は `npm run qa:claims` で抽出を更新してください。_
