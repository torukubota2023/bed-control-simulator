# Layer 1-3 rotation_eligible:false ファクト一次文献精密検証レポート

**実施日:** 2026-04-18
**対象:** `data/facts.yaml` の Layer 1-3 かつ `rotation_eligible: false` のファクト
**検証手段:** PubMed MCP `fetch_summary` による原著メタ情報・要旨の突合
**検証対象外（既検証済み）:** ローテーション 12 件（f001, f002, f003, f004, f005, f006, f010, f011, f013, f026, f027, f038）

---

## サマリ

| 判定 | 件数 |
|------|------|
| ✅ OK | 23 |
| ⚠️ MINOR | 2 |
| 🟠 NUMERIC | 0 |
| 🔴 CITATION_ERROR | 0 |
| ❌ HALLUCINATION | 0 |
| 📘 PMID なし（検証対象外・国内資料/施設基準） | 3 |
| **合計** | **28** |

- **facts.yaml 修正:** 2 件（f036, f009 — いずれも数値ラベル微修正）
- **削除:** 0 件
- **CITATION_ERROR / HALLUCINATION:** 0 件（全 PMID が原著に一致、著者・年・ジャーナルも一致）
- **総ファクト件数:** 80 件維持（削除なし） → `test_facts_yaml.py` 36 テスト全通過

---

## 対象ファクト一覧と判定

### Layer 1: 退院時機能の最適化（rotation_eligible:false 11 件中、PMID 付き 10 件）

| id | 著者/年 | PMID | 判定 | コメント |
|---|---|---|---|---|
| f028 | Boyne 2023 | 36822187 | ✅ OK | 12 週 HIIT vs MAT の 6MWD 差 +44m（95% CI 14-74）、n=55 を原著と一致 |
| f029 | Ellis 2017 | 28898390 | ✅ OK | 29 RCTs n=13,766、RR 1.06 自宅在住、RR 0.80 施設入所 ともに原著一致 |
| f030 | Zhang 2019 | 31581205 | ✅ OK | 23 RCTs n=2,308、ICU-AW RR 0.60、自宅退院 RR 1.16 一致 |
| f031 | Warren 2021 | 33517463 | ✅ OK | n=17,546、AUC 0.80（Basic Mobility）/ 0.81（Daily Activity）一致 |
| f032 | Schaller 2016 | 27707496 | ✅ OK | n=200、LOS 7 vs 10 日、mmFIM 8 vs 5（≒+3）一致 |
| f033 | Lambe 2022 | 35689181 | ✅ OK | 12 SR 44 RCTs、early intervention・repeated practice・goal setting の記述一致 |
| f034 | Ishizuka 2025 | 40057664 | ✅ OK | n=4,669、高強度×高頻度群 OR 2.75（1.59-4.76）一致 |
| f035 | Nakaya 2021 | 34291626 | ✅ OK | n=75、SPPB 介入効果サイズ +2.2、p<0.001 一致 |
| f036 | Wang YC 2023 | 37357324 | ⚠️ MINOR → 修正済み | **「90 日再入院 aOR 0.04」は原著では「60 日 aOR 0.04」** — 原著に合わせ修正 |
| f037 | Wang H 2015 | 25569470 | ✅ OK | n=5,224、severely impaired で community discharge OR 1.45 一致 |
| f078 | 厚労省 地域医療構想検討会 | — | 📘 国内資料 | PMID 対象外 |

### Layer 2: 退院タイミング判断（rotation_eligible:false 7 件中、PMID 付き 5 件）

| id | 著者/年 | PMID | 判定 | コメント |
|---|---|---|---|---|
| f007 | Au 2019 | 30129263 | ✅ OK | 金曜・月曜・水曜退院で再入院/死亡に差なし — 原著一致 |
| f008 | Boutera 2026 | 41102596 | ✅ OK | n=35,138、30 日 HRR 1.4（1.3-1.6）、1 年 HRR 1.2（1.2-1.3）一致 |
| f009 | Considine 2018 | 30217155 | ⚠️ MINOR → 修正済み | 原著は「One quarter of patients were discharged on a Friday **or weekend**」と併記。既存「金曜退院」を「金曜〜週末退院」に修正 |
| f056 | Rinne 2015 | 26147865 | ✅ OK | n=25,301、週末在院 +0.59 日、再入院 OR 1.00、30 日死亡 OR 0.80 一致 |
| f057 | Zajic 2017 | 28877753 | ✅ OK | 119 ICU、入室 HR 1.15/1.11、退室 HR 0.63（37% 減）/ 0.56（44% 減）→ 「3-4 割低下」と整合 |
| f076 | 地域包括ケア推進病棟協会 施設基準 | — | 📘 施設基準資料 | PMID 対象外 |
| f077 | 福祉医療機構 | — | 📘 国内調査 | PMID 対象外 |

### Layer 3: リハビリの時間・強度・継続（rotation_eligible:false 9 件、全件 PMID 付き）

| id | 著者/年 | PMID | 判定 | コメント |
|---|---|---|---|---|
| f012 | Takahashi 2024 | 38220172 | ✅ OK | J-Proof HF n=9,403、HAD 発症 37.1% 一致 |
| f039 | de Foubert 2021 | 34240755 | ✅ OK | 18 研究、74%（14 of 18）が主要アウトカム改善を報告 一致 |
| f040 | Casas-Herrero 2022 | 35150086 | ✅ OK | Vivifrail n=188、3 ヶ月 SPPB +1.40（95% CI 0.82-1.98）一致 |
| f041 | Ahmad 2023 | 36026532 | ✅ OK | TARGET-EFT n=135、SPPB +1.52、SARC-F +0.74 一致 |
| f042 | Kuo 2025 | 40335426 | ✅ OK | 18 RCTs n=2,724、QOL・ADL・満足度改善、polypharmacy 減、6 ヶ月死亡低下 一致 |
| f043 | Rezaei-Shahsavarloo 2020 | 33272208 | ✅ OK | 7 研究（3 介入種別）n=1,009、ES 0.35 一致。CGA ユニット介入が最寄与の記述も一致 |
| f044 | Lozano-Vicario 2024 | 38593983 | ✅ OK | n=36 RCT、IQCODE p=.017（1-3 ヶ月認知低下抑制）一致 |
| f045 | Monsees 2023 | 35649531 | ✅ OK | 10 RCTs n=1,291、ICU 在室短縮と機能独立傾向 一致 |
| f046 | Ceylan 2024 | 39331264 | ✅ OK | n=100、2MWT 135.6 vs 123.4（差 +12.2m）、r=-0.768 一致 |

---

## 修正内容詳細

### f036（Wang YC 2023, PMID 37357324）
- **変更前:** 「急性期高齢者への多要素介入で ADL 改善、在院 -5 日、30 日再入院 aOR 0.12、**90 日再入院** aOR 0.04」
- **変更後:** 「急性期高齢者への多要素介入で ADL 改善、在院 -5 日、30 日再入院 aOR 0.12、**60 日再入院** aOR 0.04」
- **根拠:** 原著 abstract 原文「30-day adjusted OR [aOR], 0.12; ... 60-day aOR, 0.04」

### f009（Considine 2018, PMID 30217155）
- **変更前:** 「退院 1 日以内の予期せぬ再入院の 1/4 が**金曜退院**、主因は痛み」
- **変更後:** 「退院 1 日以内の予期せぬ再入院の 1/4 が**金曜〜週末退院**、主因は痛み」
- **根拠:** 原著 abstract「One quarter of patients were discharged on a Friday or weekend」。Friday 単独は 17.3%、Friday + 週末合計で約 1/4 と対応する

---

## テスト結果

```
$ python3 -m pytest tests/test_facts_yaml.py -q
....................................                                     [100%]
36 passed in 0.05s
```

- 総件数 80 件維持（削除なし）
- rotation_eligible=true 件数 12 件維持
- PMID / DOI 形式チェック通過
- レイヤー別件数分布（1:19, 2:8, 3:12, 4:10, 5:8, 6:3, 7:20）維持

---

## 300 字サマリ

Layer 1-3 の rotation_eligible:false 28 件（うち PMID 付き 25 件）を PubMed 原著で精密検証。全 25 件で著者・年・ジャーナル・PMID は原著と一致し、CITATION_ERROR / HALLUCINATION はゼロ。数値ラベルに軽微なずれが 2 件（f036 の「90 日再入院」は原著「60 日」、f009 の「1/4 が金曜退院」は原著「金曜〜週末退院」）あり、いずれも原著表現に合わせて修正。総件数 80 件・ローテーション 12 件は維持し、`test_facts_yaml.py` 36 テスト全通過を確認。Layer 1-3 のエビデンスは副院長方針通り強度が担保されている。
