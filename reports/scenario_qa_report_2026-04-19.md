# シナリオ QA レポート

**生成日:** 2026-04-19T11:37:22
**対象台本:** 4 本 (59 クレーム抽出)
**対象アプリ:** ベッドコントロール（commit `f9c2a0d`）
**総合判定:** **OK**

## 判定理由

- すべての QA チェックをパス

## 1. 台本 ↔ 実アプリ 数値一致（Playwright）

- 実行時刻: 2026-04-19T02:37:21.032Z
- 対象クレーム数: 59（PASS 16 / FAIL 0 / SKIPPED 41 / MISSING_TESTID 0 / MISSING_DOM 2）

### 重大不一致（0 件）
なし。

### 軽微ズレ（0 件）
なし。

### Playwright 側で照合できなかった項目（2 件）
- DOM 値パース不可: 2 件
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
| `docs/admin/carnf_scenario_v4.md` | 9 |
| `docs/admin/demo_scenario_v4.md` | 31 |
| `docs/admin/presentation_script_bedcontrol_v4.md` | 15 |
| `docs/admin/slides/weekend_holiday_kpi/script.md` | 4 |

### 指標別クレーム数

| 指標 | 件数 |
|----|----|
| holiday_banner_threshold_days | 22 |
| emergency_pct | 13 |
| emergency_threshold_pct | 9 |
| patient_count_rows | 3 |
| alos_limit_days | 2 |
| status_count_normal | 2 |
| revenue_per_1pct_manyen | 2 |
| occupancy_target_pct | 2 |
| c_group_contribution_yen | 2 |
| alos_days | 1 |
| occupancy_pct | 1 |

## 総評

すべての QA 層（台本一致・アプリ内整合・現実性・教育性）をパス。副院長がカンファ中に台本を読み上げる際、実アプリの数値と齟齬なく進められる状態です。

---

_このレポートは `scripts/generate_qa_report.py` が自動生成したものです。台本を更新した際は `npm run qa:claims` で抽出を更新してください。_
