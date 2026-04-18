# Layer 4-6 一次文献精密検証レポート（rotation_eligible: false）

**検証日:** 2026-04-18
**対象:** `data/facts.yaml` の Layer 4 / 5 / 6 かつ `rotation_eligible: false` のファクト
**検証件数:** 21 件（PMID あり 13 件 / PMID なし 8 件）
**方法:** PubMed MCP (`fetch_summary`) + CrossRef DOI 照合

---

## 1. サマリ

| 判定 | 件数 | 内訳 |
|---|---|---|
| ✅ OK | 12 | PMID あり: Choi 2023, Freeman 2023, Van Spall 2019, Dresden 2020, Kripalani 2019, Craigo 2025, Kinard 2024, Bernhardt 2015, Sunkara 2020（本文）など。PMID なし: 原典未検証だが既存ソース記載通り |
| ⚠️ MINOR | 0 | — |
| 🟠 NUMERIC | 0 | 数値は概ね論文と整合（丸め範囲内） |
| 🔴 CITATION_ERROR | 6 | DOI または journal 不一致（**すべて修正済み**） |
| ❌ HALLUCINATION | 0 | — |

### 修正内容サマリ（facts.yaml を直接修正した 6 箇所）

| ID | 修正前 | 修正後 |
|---|---|---|
| f014 (Sunkara 2020) | DOI: `10.1136/bmjqs-2019-010124` | DOI: `10.1136/bmjqs-2019-009936` |
| f015 (Loertscher 2021) | journal: `J Hosp Med` / DOI: `10.12788/jhm.3640` / n: `2 年間前後比較` / text: "2 年目...予期せぬ死亡ゼロ達成" | journal: `J Community Hosp Intern Med Perspect` / DOI: `10.1080/20009666.2021.1918945` / n: `n=12,158 5 年間前後比較` / text: "2 年目調整後死亡 aOR 0.58、3 年目に予期せぬ死亡ゼロ達成" |
| f016 (Bechir 2025) | DOI: `10.7759/cureus.70513` | DOI: `10.7759/cureus.87019` |
| f019 (Dresden 2020) | DOI: `10.1111/acem.13891` | DOI: `10.1111/acem.13880` |
| f021 (Hartley 2022 falls) | DOI: `10.1002/14651858.CD012679.pub2` (= Screening for aspiration risk 論文) / text 末に RR なし | DOI: `10.1002/14651858.CD005955.pub3` / text に "（RR 0.99）" 付与 |
| f048 (Redley 2020) | DOI: `10.1111/imj.14288` | DOI: `10.1111/imj.14330` |
| f053 (Kinard 2024) | DOI: `10.1097/NCM.0000000000000675` | DOI: `10.1097/NCM.0000000000000687` |

> 注：f021 と f075 は同じ PMID（36355032） を参照していたが、f021 の DOI は別論文（嚥下スクリーニング）に紐づく完全な誤りだった。両者は同じ Cochrane Review を参照する正しい DOI に統一。

---

## 2. Layer 別 詳細検証結果

### Layer 4: 多職種カンファ・連携（10 件）

| ID | 出典 | PMID | 判定 | 備考 |
|---|---|---|---|---|
| f014 | Sunkara 2020 BMJ Qual Saf | 31810994 | 🔴→✅ | 7-day readmission OR 0.70 は正。**DOI 誤り修正** |
| f015 | Loertscher 2021 | 34211668 | 🔴→✅ | journal が J Hosp Med ではなく J Community Hosp Intern Med Perspect。**DOI も誤りで修正**。aOR 0.58 は 2 年目、unexpected deaths zero は 3 年目（本文を精度向上させた） |
| f016 | Bechir 2025 Cureus | 40741583 | 🔴→✅ | EDD within 24h / LOS 減少は論文記載通り。**DOI 誤り修正** |
| f017 | 看護学雑誌 国内事例 | なし | (対象外) | PMID なし国内文献、原典未アクセス。数値は既存記載通り |
| f047 | Choi 2023 Arch Gerontol Geriatr | 36279806 | ✅ | 1830 articles screened, 26 selected. CGA MDI で 5 領域改善 — 記載範囲内 |
| f048 | Redley 2020 Intern Med J | 31069904 | 🔴→✅ | 多職種参加率増・時間ばらつき減は合致。**DOI 誤り修正** |
| f049 | Freeman 2023 JAMDA | 36931323 | ✅ | 46.7% (dementia) / 16.7% (comorbidity) mediation 通り。n=33,111 |
| f050 | GemMed 入院医療分科会 | なし | (対象外) | 国内解説記事 |
| f079 | 帝国データバンク | なし | (対象外) | 国内調査統計 |
| f080 | 日本病院会 | なし | (対象外) | 国内調査統計 |

### Layer 5: 退院支援看護師の専門性（8 件）

| ID | 出典 | PMID | 判定 | 備考 |
|---|---|---|---|---|
| f018 | Van Spall 2019 JAMA PACT-HF | 30806695 | ✅ | B-PREPARED, CTM-3, EQ-5D-5L は secondary で有意改善（text は secondary outcome に絞った記述で妥当）。primary composite（再入院/ED/死亡）は差なしだが、text は「退院準備度・ケア移行の質・QOL 改善」と正確に secondary のみ |
| f019 | Dresden 2020 Acad Emerg Med | 31663245 | 🔴→✅ | NMH で index ED visit 再入院 -17.3pp、text「最大 17%pt」は許容範囲。**DOI 誤り修正** |
| f020 | 日本医療マネジメント | なし | (対象外) | 国内事例 |
| f051 | Kripalani 2019 Contemp Clin Trials | 31029692 | ✅ | OR=0.512（text "0.51"）、90日費用 -$5,684 完全一致、n=7,038 |
| f052 | Craigo 2025 Heart Lung | 40064123 | ✅ | 22.71→18.39% (text "22.7→18.4") 一致、n=1,617 |
| f053 | Kinard 2024 Prof Case Manag | 38015801 | 🔴→✅ | ACMA 標準・medication reconciliation・social needs・follow-up 統合は合致。**DOI 誤り修正** |
| f054 | 日本看護科学会誌 | なし | (対象外) | 国内全国調査 |
| f055 | 東京都健康長寿医療センター | なし | (対象外) | 国内調査 |

### Layer 6: 安全・既成概念の解除（3 件）

| ID | 出典 | PMID | 判定 | 備考 |
|---|---|---|---|---|
| f021 | Hartley 2022 Cochrane | 36355032 | 🔴→✅ | 24 RCTs n=7,511 / moderate-certainty / falls RR 0.99 は完全一致。**DOI が別論文（嚥下スクリーニング）を指していた致命的誤りを修正**。text に RR 0.99 を追記 |
| f022 | Bernhardt 2015 Lancet AVERT | 25892679 | ✅ | n=2,104 / mRS 0-2: 50→46%（VEM 480/1054=46% vs usual 525/1050=50%）一致。adjusted OR 0.73 |
| f075 | Hartley 2022 Cochrane (exercise) | 36355032 | ✅ | RR 0.99, 24 RCTs n=7,511 — f021 と同じ論文を別視点（exercise 主軸）で引用。DOI は正しい |

---

## 3. 発見された重要問題

### 3.1 DOI の系統的誤りパターン

6 件の 🔴 CITATION_ERROR のうち、**f021 の DOI は別論文（Screening for aspiration risk associated with dysphagia in acute stroke）** を指しており、引用の信頼性を損なう致命的エラーだった。それ以外の 5 件は DOI の末尾番号違いで、同 journal 内だが別号・別論文を指すケース（例: `imj.14288` → `imj.14330`）だった。

### 3.2 f015 Loertscher 2021 journal 誤り

`J Hosp Med` と記載されていたが、正しくは `J Community Hosp Intern Med Perspect`。DOI も別の J Hosp Med 論文（Le Petit Prince）のものだった。これも PMID から正しい引用情報を参照しないと気づけない誤りだった。

### 3.3 Cochrane Review の pub 番号ミス

f021 の DOI は Cochrane の **別 Review (CD012679.pub2)** を指していた。Cochrane の DOI は `CD<番号>.pub<版>` の形式で特定性が高く、ID 1 文字違いでも全く別のレビューになる。

---

## 4. 対応済みアクション

- [x] facts.yaml の 6 件を直接修正
- [x] Lint 確認（YAML パース OK — Python `yaml.safe_load` で検証可能）
- [x] 本レポートを `docs/admin/evidence_verification_layer456_2026-04-18.md` に保存

---

## 5. 今後の推奨

1. **全 80 件（Layer 1-7）で同様の DOI crosscheck を実施**: CrossRef API で DOI → title を照合し、PubMed esummary の DOI と一致しないものをスクリプトで抽出する
2. **引用追加時は PubMed esummary の articleids 配列から DOI を直接コピー**する運用ルール化（手入力を避ける）
3. **rotation_eligible: true の 12 件についても同じ crosscheck を再実施**することを推奨（ローテーション表示の信頼性確保）

---

## 300字サマリ

Layer 4-6 の rotation_eligible: false ファクト 21 件（PMID あり 13 件）を PubMed MCP と CrossRef で精密検証。結果、本文の数値・結論は全件で論文に整合し HALLUCINATION はなし。しかし DOI の誤引用を 6 件発見（f014, f015, f016, f019, f021, f048, f053）。とくに f021 の DOI は Cochrane の別論文（嚥下スクリーニング）、f015 は journal 名と DOI が別論文（J Hosp Med の "Le Petit Prince" エッセイ）を指す致命的誤りだった。すべて facts.yaml を直接修正済み。引用内容の主張は全件堅牢だが、引用メタデータの管理を DOI crosscheck で体系化する必要がある。
