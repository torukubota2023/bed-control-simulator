# 院内LAN導入前 最終確認チェックリスト

**作成日**: 2026-05-01
**対象**: ベッドコントロールシミュレーター（v3.5l 系列）
**目的**: 院内SE への導入依頼前に、デモデータから実データ運用への移行を安全に行う

---

## 🎯 「初日から有効 / 補完可能 / 蓄積必要」機能マトリクス

| 機能 | 初日 | 1-2 週 | 8-12 週 | rolling 補完手段 |
|---|:-:|:-:|:-:|---|
| 単月稼働率 / 当日入退院数 | ✅ | | | — |
| 短手3 Day 5 アラート | ✅ | | | — |
| 退院カレンダー（月俯瞰） | ✅ | | | — |
| 結論カード（今日の一手） | ✅ | | | — |
| LOS rolling 90 日 | | | ✅ | **過去月サマリー**（入院件数・退院件数・在院延日数・救急＋下り搬送件数）で 4-5 月補完 |
| **救急15% rolling 3 ヶ月** | | | ✅ | `settings/manual_seed_emergency_ratio.yaml`（手動シード／救急専用） + 過去月サマリー |
| **看護必要度 rolling 3 ヶ月** | | | ✅ | **`settings/manual_seed_nursing_necessity.yaml`（2026-05-01 新設）** |
| 退院曜日分析（過去 1 年） | ✅ | | | `data/past_admissions_2025fy.csv` 統合済 |
| 医師別分析（過去 1 年） | ✅ | | | 同上 |
| 医師別分析（直近、実医師コード）| | ✅ | | 日次入力タブで実医師コード入力開始から |
| 必要度寄与パターン分析 | | | ✅ | 日次データ蓄積後 |
| 救急患者応需係数 | ✅ | | | 過去 1 年実績から自動算出 |

---

## 📋 副院長運用手順（6/1 完全適用までのロードマップ）

### Step 1: 院内LAN導入直後（Day 0）

#### 必須作業
1. **本番初期化**（デモデータ退避）
   - 「⚙️ データ・設定 > 📋 日次データ入力」タブ最上部のバナーで `🔴 デモと実の混在` または `⚠️ デモデータ` 表示を確認
   - 「🛠 本番初期化（デモデータを退避 → 空スキーマを作成）」expander を展開
   - チェックボックスで同意 → 「📦 本番初期化を実行」ボタン
   - 退避ファイル `data/archive/admission_details_demo_YYYYMMDD_HHMMSS.csv` が作成されることを確認

2. **データ純度バナーの確認**
   - バナーが `📭 空（未入力）` または `✅ 実データ` に変わっていれば OK
   - 万が一 `🔴 デモと実の混在` のままなら、`data/admission_details.csv` を手動で確認

#### 推奨作業
3. **過去月シードの入力**（4 月・5 月分の既知データを補完）
   - 救急 15%: 「⚙️ データ・設定 > 設定」または直接 `settings/manual_seed_emergency_ratio.yaml` を編集
   - **看護必要度**: 「📈 過去1年分析 > 看護必要度トレンド」セクションの「🌉 看護必要度 月次シード入力」expander
     - 諸見里さん提供の月次サマリーから 5F/6F の 4 値（I_total, I_pass1, II_total, II_pass1）を入力
     - 保存後、月別出典マトリクスで `🌉 シード` 表示を確認

### Step 2: 1-2 週間目（Week 1-2）

- 日次入力（実医師コードで `KJJ` / `HAYT` / `OKUK` 等）が継続的に入っていることを確認
- 「⚙️ データ・設定 > 👨‍⚕️ 医師別分析」タブで実医師コードのバナーが表示されることを確認
- 退院カレンダー / 短手3 Day 5 アラート / 結論カードが日々有効になることを確認

### Step 3: 8-12 週目（Week 8-12）

- 日次データ蓄積で **rolling 90 日 LOS** が純実データ計算へ自動移行
- **救急 15% rolling 3 ヶ月** がシード卒業（`monthly_summary` から自動切替）
- **看護必要度 rolling 3 ヶ月** も同様に CSV 由来の月次集計が優先される
- 「📈 過去1年分析」の bridge 卒業判定バナーで「🎓 シードは過去 CSV で代替済み → 削除可」表示を確認

---

## 🔐 院内SE への引渡し前 5 項目チェック

### ✅ チェック 1: デモデータ退避が完了している

```bash
# 確認コマンド（Mac/Linux ターミナルで）
ls -la data/admission_details.csv
ls data/archive/admission_details_demo_*.csv 2>/dev/null
```

期待値:
- `data/admission_details.csv` が **空スキーマ**（行数 1 = ヘッダーのみ）
- `data/archive/` に少なくとも 1 つの退避ファイル

### ✅ チェック 2: シード YAML が用意されている

```bash
ls -la settings/manual_seed_emergency_ratio.yaml
ls -la settings/manual_seed_nursing_necessity.yaml
```

両ファイルが存在し、4 月・5 月の `seeds:` キー配下に値が入っていれば OK。

### ✅ チェック 3: pytest が全件 PASS

```bash
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_holiday_calendar.py \
  --ignore=tests/test_conference_material_view.py \
  --ignore=tests/test_generate_demo_data_2026fy.py \
  --ignore=tests/test_past_performance_view.py
```

期待値: `XXXX passed`（環境依存テストを除外）

### ✅ チェック 4: smoke test が PASS

```bash
.venv/bin/python scripts/hooks/smoke_test.py
```

期待値: `✅ SMOKE TEST PASSED`

### ✅ チェック 5: アプリ起動 + バナー表示確認

```bash
# Mac で確認
.venv/bin/streamlit run scripts/bed_control_simulator_app.py --server.port 8501
```

ブラウザで `http://localhost:8501` を開き、サイドバーの「⚙️ データ・設定」セクションに切替えて「📋 日次データ入力」タブの最上部に **データ種類バナー** が表示されていることを確認。

---

## 🛠 トラブル時の対処

### 状況 1: バナーが「🔴 デモと実の混在」のまま消えない

**原因**: `data/admission_details.csv` にデモ行と実行が両方残っている

**対処**:
1. 「📦 本番初期化を実行」ボタンで一旦すべて退避
2. 過去の実データを残したい場合は、退避ファイルから実医師コード行のみを手で抽出して新 CSV にコピー
3. 再度 admission_details.csv に配置

### 状況 2: 看護必要度シードの入力後も「no_data」のまま

**原因**: シード値の一部に null が残っている（4 値すべて埋める必要あり）

**対処**: I_total / I_pass1 / II_total / II_pass1 の **4 つ全部に数値を入れて再保存**。null が 1 つでもあると採用されない仕様。

### 状況 3: エクスポートタブで「読込エラー」表示

**原因**: 一部の関数名が修正されていない（旧: `load_actual_data` / `load_admission_details`）

**対処**: 2026-05-01 のコミット `feat/pre-lan-deployment-safety-2026-05-01` を取り込めば修正済み（`load_daily_records` / `load_details` を呼ぶ実装）。

### 状況 4: 「本番初期化」ボタンを誤って押した

**対処**: 退避ファイル `data/archive/admission_details_demo_YYYYMMDD_HHMMSS.csv` をターミナルで戻す。

```bash
cp data/archive/admission_details_demo_YYYYMMDD_HHMMSS.csv data/admission_details.csv
```

タイムスタンプ部分は最新のものを使う。

---

## 📂 関連ファイル一覧

| ファイル | 役割 |
|---|---|
| `scripts/data_purity_guard.py` | デモ/実/混在判定、本番初期化（2026-05-01 新規）|
| `scripts/nursing_necessity_seeds.py` | 看護必要度月次シード loader（2026-05-01 新規） |
| `scripts/bed_data_manager.py:load_details` | `real_only` パラメータで safeguard（2026-05-01 拡張） |
| `settings/manual_seed_emergency_ratio.yaml` | 救急 15% シード（既存） |
| `settings/manual_seed_nursing_necessity.yaml` | 看護必要度シード（2026-05-01 新規） |
| `data/archive/` | デモデータ退避先（自動作成） |
| `tests/test_data_purity_guard.py` | 25 テスト |
| `tests/test_nursing_necessity_seeds.py` | 21 テスト |

---

## 🌐 院内LAN運用上の追加注意（Codex レビュー 2026-05-01 反映）

### 1. 複数端末同時入力の制約

Streamlit 単体 + CSV / YAML / SQLite 混在運用では、**複数端末から同時に保存すると競合する可能性** があります。
初期運用では以下を厳守：

- **日次入力担当端末を 1 台に限定**（複数の看護師ステーションから同時入力は不可）
- どうしても複数端末が必要な場合は、**入力時間帯を分ける**（午前 = 5F端末、午後 = 6F端末 など）
- 副院長の閲覧端末（読み取り専用利用）は同時に何台でも OK

### 2. バックアップ対象（手動 or cron）

`data/` フォルダだけではなく、以下も必ずバックアップ対象に含めてください：

```bash
# 例: 毎日 22:00 に院内バックアップサーバーへコピー
cp -r data/        /path/to/backup/$(date +%Y%m%d)/
cp -r settings/    /path/to/backup/$(date +%Y%m%d)/    # 手動シード YAML 群を含む
cp -r data/archive/ /path/to/backup/$(date +%Y%m%d)/
```

特に `settings/manual_seed_emergency_ratio.yaml` と `settings/manual_seed_nursing_necessity.yaml` は副院長の手入力データであり、消失すると 1〜2 時間の作業が失われます。

### 3. 「本番初期化」誤操作からの復旧

万が一、誤って「📦 本番初期化を実行」を押した場合の復旧手順：

```bash
# (a) 退避ファイルの確認（最新のもの = いちばん下に出る）
ls -lt data/archive/admission_details_*.csv | head -5

# (b) 最新の退避ファイル名を確認後、admission_details.csv に戻す
cp data/archive/admission_details_demo_YYYYMMDD_HHMMSS.csv data/admission_details.csv

# (c) Streamlit を再起動 or「Rerun」を押してバナーが正しい状態に戻ることを確認
```

退避ファイルは **タイムスタンプ降順で並べる** と最新が上に来ます。`ls -lt` の `-t` オプションが時刻順ソート、`head -5` で上位 5 件のみ表示。

---

## 📊 定期監視（運用開始後）

### 毎週月曜（5 分）

- 「⚙️ データ・設定 > 📋 日次データ入力」のバナーが `✅ 実データ` であることを確認
- バナーが `🚨 デモと実の混在` に変わっていたら即座に対処

### 毎月初（15 分）

- 諸見里さんから前月の看護必要度月次サマリーを受領
- 「📈 過去1年分析 > 看護必要度トレンド > 🌉 月次シード入力」で前月分を入力
- 月別出典マトリクスを確認

### 6/1 当日

- 「経過措置終了まで残 0 日」バナーが「経過措置は終了しました」に切り替わることを確認
- rolling 3 ヶ月の救急 15% / 看護必要度のすべてのバナーが緑（✅ 達成）であることを確認
- 万が一未達バナーがあれば、シード値の見直しまたは運用改善の即時対応

---

**作成者**: Claude Code（副院長指示 2026-05-01 「院内LAN導入直前の本番移行チェックと改善実装」に基づく）
