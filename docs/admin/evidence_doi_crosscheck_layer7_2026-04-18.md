# Layer 7 エビデンス DOI クロスチェックレポート

**検証日:** 2026-04-18
**対象:** `/Users/torukubota/ai-management/data/facts.yaml` Layer 7 の PMID 付き 5 件
**検証手段:** PubMed MCP (`mcp__72c19240-...__get_article_metadata`) による公式メタデータ取得
**背景:** 先行検証（rotation+Layer 1-3: 18/36、Layer 4-6: 6/13）で DOI 誤記が相次いで発覚。Layer 7 PMID 付きファクトにも同パターンがないか精査する。

## 対象ファクト（5 件）

| ID | 著者・年 | ジャーナル | PMID |
|----|---------|-----------|------|
| f023 | Howlett 2026 | EMJ | 41672875 |
| f058 | Boulain 2020 | Intern Emerg Med | 31728759 |
| f059 | Ahmed 2026 | Cureus | 41625046 |
| f060 | Jones 2024 | Int J Environ Res Public Health | 39200645 |
| f061 | Shih 2020 | Am J Phys Med Rehabil | 31335342 |

## 検証結果（DOI 照合）

| ID | facts.yaml DOI | PubMed 公式 DOI | 判定 |
|----|---------------|----------------|------|
| f023 | `10.1136/emermed-2025-215012` | `10.1136/emermed-2025-214983` | **不一致 → 修正** |
| f058 | `10.1007/s11739-019-02231-z` | `10.1007/s11739-019-02231-z` | 一致 |
| f059 | `10.7759/cureus.100560` | `10.7759/cureus.100560` | 一致 |
| f060 | `10.3390/ijerph21081035` | `10.3390/ijerph21081035` | 一致 |
| f061 | `10.1097/PHM.0000000000001266` | `10.1097/PHM.0000000000001266` | 一致 |

## 修正内容

### f023 Howlett 2026 EMJ
- **誤:** `10.1136/emermed-2025-215012`
- **正:** `10.1136/emermed-2025-214983`
- **根拠:** PubMed efetch の `<ArticleId IdType="doi">` および PII `emermed-2025-214983`
- **本文内容との整合:** アブストラクト記載の「each additional 4 hours of boarding time was associated with an extra 8.6 hours of inpatient length of stay and an 8.4% increase in the odds of 30-day mortality」と f023 の text 記述（"ED 待機 4 時間超で 30 日死亡オッズ +8.4%"）は完全一致。PMID も正しい。DOI 末尾数字のみの誤記

## タイトル・ジャーナル一致確認（参考）

| ID | タイトル（PubMed） | 一致 |
|----|---------------------|------|
| f023 | Medical patient boarding in the emergency department... | OK |
| f058 | Association between long boarding time in the emergency department and hospital mortality... | OK |
| f059 | Clinical and Operational Effects of Emergency Department Crowding: A Systematic Review | OK |
| f060 | A New Approach for Understanding International Hospital Bed Numbers... | OK |
| f061 | Weekend Admission to Inpatient Rehabilitation Facilities Is Associated With Transfer to Acute Care... | OK |

## サマリ

- **検証件数:** 5 件
- **DOI 不一致件数:** 1 件（f023 Howlett 2026 EMJ）→ 修正済
- **不一致率:** 20%（先行検証の ~50%, 46% より大幅改善）
- **考察:** Layer 7 の PMID 付きファクトはタイトル・ジャーナル・PMID はすべて正確で、DOI も 5 件中 4 件が正しかった。誤記は Howlett 2026 の DOI 末尾 4 桁（`215012` vs `214983`）の 1 箇所のみ。先行レイヤー群よりも精度が高い傾向が確認された
- **今後:** facts.yaml の残存 PMID 付きファクトはこれで全件クロスチェック完了。非 PMID ファクト（厚労省・GemMed・四病協・第一生命経済研究所等）は一次出典 URL の別検証が必要だが、PubMed MCP の射程外

## 出典
- PubMed: https://pubmed.ncbi.nlm.nih.gov/
- Howlett 2026: [DOI](https://doi.org/10.1136/emermed-2025-214983)
- Boulain 2020: [DOI](https://doi.org/10.1007/s11739-019-02231-z)
- Ahmed 2026: [DOI](https://doi.org/10.7759/cureus.100560)
- Jones 2024: [DOI](https://doi.org/10.3390/ijerph21081035)
- Shih 2020: [DOI](https://doi.org/10.1097/PHM.0000000000001266)
