"""看護必要度ミニレクチャー — 医師の行動変容に焦点を当てた実践型コンテンツ.

当院（おもろまちメディカルセンター、地域包括医療病棟入院料1）に特化した内容。
2026-06-01 新基準対応のため、医師が「いつ・どんな患者に・何をすればよいか」を
シーン別・判断ポイント別に明示する。

このファイルは markdown 文字列のみを提供する。Streamlit に依存しない。
"""

# ---------------------------------------------------------------------------
# 本文
# ---------------------------------------------------------------------------

LECTURE_MARKDOWN: str = """
### ⏱️ 30 秒で要点

新基準（2026-06-01〜）で **6F は 必要度Ⅰ -1.46pt、Ⅱ -3.38pt 未達のリスク**。
クリアに必要な追加該当患者は **1 日たった 0.77 人**。
**医師の判断 1 つで救える数字**です。

---

### 🚨 医師の 5 つの行動変容（これだけ覚える）

#### ① 入院時 30 秒の自問
> **「この患者、A6 該当処置の必要性はないか？」**

| こんな患者を見たら | 検討すべき処置 | 該当 (3点) |
|---|---|---|
| 急性膵炎 重症 / 胆石症発作 | モルヒネ持続点滴 | A6③ 麻薬注射 |
| 高リスク PE / CrCl<30 DVT | ヘパリン持続点滴 | A6⑨ 抗血栓持続 |
| 重症 Af / 心房粗動 | アミオダロン点滴 | A6⑧ 抗不整脈剤 |
| PHN / CRPS / 難治性神経障害性疼痛 | リドカイン点滴 | A6⑧ 抗不整脈剤 |
| 敗血症 / 心不全急性増悪 / ショック | 昇圧剤持続点滴 | A6⑦ 昇圧剤注射 |

**ポイント**: 適応の正当性が前提。点数稼ぎではなく、
**今までも適応があったがオーダーを迷っていた症例の閾値を下げる**運用。

---

#### ② 早期切替を急がない
> 適応のある間は、**必要十分な期間続ける**。

- DOAC への移行は **臨床的安定後**（24-48 時間以上ヘパリン継続が標準）
- 経口モルヒネへの移行は **疼痛コントロール十分後**
- 「経口で行ける」と即断せず、**翌日朝の評価まで持続継続**
- 重症例（hemodynamic instability、CrCl<30、出血リスク高）は UFH 持続を継続

---

#### ③ 入院時オーダーに「予定継続日数」を書く
> 看護師が看護必要度評価を予測でき、**病棟全体の予測精度**が上がる。

例:
- 「ヘパリン持続点滴 5 日間予定」
- 「モルヒネ持続点滴 3 日間、症状次第で延長」
- 「アミオダロン点滴 24-48 時間、心拍コントロール後に経口移行」

---

#### ④ 看護師の確認・提案には *即日* 応答
> **翌日では遅い**（その日の評価が確定してしまう）。

- 「この処置、今日も継続ですか？」 → 即答
- 「A項目に該当する処置の追加余地は？」 → 即答
- 朝のラウンド or PHS 即応で対応
- 看護師の提案を歓迎する文化が成功の前提

---

#### ⑤ 退院前 1 分の振り返り
> **「内視鏡治療・侵襲的処置・追加適応の漏れはないか？」**

- C21 該当（内視鏡的胆管ステント、ESD/EMR、内視鏡止血等）の余地はないか
- A1 創傷処置（蜂窩織炎、糖尿病性足病変、術後縫合創）の評価記録は適切か
- 抗菌薬の途中切替で **A3 注射薬剤 3 種類同時管理**の機会を逃していないか

---

### 🆕 2026-06-01 から内科でも C 項目で稼げる

C項目に内科的治療が追加され、**内科医師でも C 項目で看護必要度を取れる**ようになった:

| 当院で実施可能な処置 | 該当項目 | 期間 |
|---|---|---|
| **内視鏡的止血術** | C21③ 侵襲的消化器治療 | **4 日間** |
| **ESD / EMR**（粘膜下層剥離 / 切除） | 同上 | **4 日間** |
| **ERCP 関連処置**（胆管ステント、EST） | 同上 | **4 日間** |
| **PTCD**（経皮的胆管ドレナージ） | 同上 | **4 日間** |
| **PEG**（内視鏡的胃瘻造設） | C23 別に定める手術 | **5 日間** |

**今すぐ意識する**:
- 嚥下障害患者を見たら → PEG 検討
- 消化管出血患者を見たら → 内視鏡止血を遅らせない
- 胆道閉塞患者を見たら → ERCP/PTCD 早期実施

---

### 🏥 シーン別 行動チェックリスト

#### 🌅 入院時（病棟到着 30 分以内）
- [ ] 主訴・既往・検査値から A6 該当処置の必要性を判定
- [ ] オーダー入力時に「予定継続日数」を記載
- [ ] 看護師に「予測される A 項目」を口頭伝達

#### ☀️ 朝のラウンド
- [ ] 持続点滴・注射の継続/中止を **当日中に判断**
- [ ] 看護師の「この患者の評価で迷っています」に即答
- [ ] 急変・状態悪化なら A6 追加処置（昇圧剤・抗不整脈剤）の閾値を下げる

#### 🍵 木曜カンファ
- [ ] 翌週退院予定者の最終処置スケジュールを確認
- [ ] 重症患者の入退院バランス（5F / 6F 構成）をチェック

#### 🌙 退院前
- [ ] 内視鏡治療・侵襲的処置の **追加適応がないか自問**
- [ ] 創傷処置・呼吸ケアの **評価記録漏れ**がないか確認
- [ ] 退院サマリで治療経過の取りこぼしを再確認

---

### 🤝 看護師との協力 — 成功の前提

医師と看護師は **両輪**:

| フェーズ | 医師 | 看護師 |
|---|---|---|
| 入院時 | 適応評価 → オーダー、継続日数記載 | 予測 A 項目を入院アセスメントに記録 |
| 日々 | 継続/中止判断、新規併用検討 | 当日 A 項目評価表を確実に記入、医師に意見具申 |
| 退院前 | 早期退院 vs 治療完遂のバランス判断 | 取りこぼし項目の有無をレビュー |

**重要**: 看護師は「評価する人」だけでなく **「医師に治療継続/追加を提案する人」**。
医師が忙しくて見落とした適応症例を、看護師が拾い上げて確認するのが理想形。

---

### ⚠️ 絶対にやらないこと

1. **適応外の処置・薬剤投与**（医療倫理違反）
2. **評価表の虚偽記載**（施設基準取消・診療報酬遡及返還）
3. **看護必要度のためだけの過剰治療**（組織信頼の失墜）
4. **病棟間の患者操作**（5F の重症患者を意図的に 6F に移す等）

正解は: **「適応のある患者の取りこぼしを減らす」のみ**。

---

### 📊 当院の現状（参考）

12 ヶ月平均（救急患者応需係数 +1.48% 加算後）:

| 病棟 | 必要度Ⅰ | 新基準19% | 必要度Ⅱ | 新基準18% |
|---|---|---|---|---|
| 5F | 19.70% | ✅ 達成 | 17.85% | ⚠️ -0.15pt |
| **6F** | **17.54%** | **🔴 -1.46pt** | **14.62%** | **🔴 -3.38pt** |

**達成可能な数字**:
- 6F 月間延べ患者数 ≒ 1,575
- 必要追加該当患者日 = **23 患者日/月** = 1 日あたり **0.77 人**
- 上記の行動変容 1 つでクリア可能

例えば:
- キシロカイン点滴 (PHN) 月 5-10 件 × 5日 = **25-50 患者日**
- ヘパリン持続点滴 (PE) 月 3-5 件 × 3日 = **9-15 患者日**
- モルヒネ持続点滴 月 3-5 件 × 3-5日 = **9-25 患者日**

---

### 📅 経過措置終了 = 2026-05-31

新基準の主な変更:

| 項目 | 旧（〜2026-05-31） | 新（2026-06-01〜） |
|---|---|---|
| 該当患者の定義 | A3点以上 / A2+B3点以上 / C1点以上 | **A2点以上 or C1点以上** |
| 必要度Ⅰ 基準値 | 16% | **19%** (+3pt) |
| 必要度Ⅱ 基準値 | 14% | **18%** (+4pt) |
| A7 救急搬送後の入院 | 5 日間 | **2 日間に短縮** |
| A1 創傷処置 | 褥瘡含む | **褥瘡を除く** |
| A3 | 点滴ライン同時 3 本以上 | **注射薬剤 3 種類以上の管理（最大 7 日間）** |

→ B 項目評価が不要になる代わりに、**A6 で 3点取れる処置を 1 つでも漏れなく評価**するのが鍵。

---

*参考エビデンス・出典（公式 PDF・要約 markdown・評価項目表画像）は本セクションの下のエキスパンダーから閲覧可能。
院内 LAN 環境でも参照できます。*

---

*このレクチャーは医師と看護師とによる運用判断を支援する目的で作成。
医療倫理・診療報酬制度の最新情報は厚労省通知を必ず参照すること。*
"""


# ---------------------------------------------------------------------------
# 参考エビデンス・出典（オフライン対応版）
# ---------------------------------------------------------------------------

# 参考資料の構造定義 — pdf 型 / excerpt 型 / image 型をサポート
# 院内 LAN 環境でも全資料を参照できるよう、PDF と markdown 要約を
# docs/admin/references/ 配下に配置。
REFERENCES: list[dict] = [
    {
        "title": "厚生労働省 令和6年度診療報酬改定 全体概要 (PDF)",
        "kind": "pdf",
        "local_path": "docs/admin/references/pdf/mhlw_r6_kaitei_overview.pdf",
        "original_url": "https://www.mhlw.go.jp/content/12400000/001224803.pdf",
        "size_kb": 944,
        "description": (
            "令和6改定（2024年度）の全体概要。看護必要度・地域包括医療病棟入院料の"
            "基礎情報を含む。令和8改定の差分は別途参照のこと。"
        ),
    },
    {
        "title": "日本循環器学会 PTE/DVT および肺高血圧症ガイドライン 2025年改訂版 (PDF)",
        "kind": "pdf",
        "local_path": "docs/admin/references/pdf/jcs2025_pte_dvt_guideline.pdf",
        "original_url": "https://www.j-circ.or.jp/cms/wp-content/uploads/2025/03/JCS2025_Tamura.pdf",
        "size_kb": 9162,
        "description": (
            "肺血栓塞栓症 (PE)・深部静脈血栓症 (DVT) の最新ガイドライン（2025年改訂）。"
            "DOAC が第一選択、UFH 持続点滴の適応症（高リスク PE、腎不全、出血リスク等）を確認可能。"
            "※ Ghostscript /screen 設定で圧縮済（原本 22.4MB → 9.2MB、テキストは完全判読可）。"
        ),
    },
    {
        "title": "GemMed: 2026年度改定 地域包括医療病棟の見直し（要約 markdown）",
        "kind": "excerpt",
        "local_path": "docs/admin/references/excerpts/gemmed_chiiki_houkatsu_2026.md",
        "original_url": "https://gemmed.ghc-j.com/?p=72897",
        "description": (
            "入院料 1/2 × イ/ロ/ハ の 6 区分細分化、看護必要度基準値変更、"
            "平均在院日数の柔軟化、救急応需係数の概要を要約。"
        ),
    },
    {
        "title": "GemMed: 救急患者応需加算 計算方法（疑義解釈4）（要約 markdown）",
        "kind": "excerpt",
        "local_path": "docs/admin/references/excerpts/gemmed_emergency_response_coefficient.md",
        "original_url": "https://gemmed.ghc-j.com/?p=74085",
        "description": (
            "救急患者応需係数の計算式詳細。当院での試算（279件/年÷94床×0.005=1.48%）"
            "と救急受入増の効果シミュレーション付き。"
        ),
    },
    {
        "title": "レジリエントメディカル: 看護必要度 A項目 詳細解説（要約 markdown）",
        "kind": "excerpt",
        "local_path": "docs/admin/references/excerpts/resilient_medical_a_items.md",
        "original_url": "https://resilient-medical.com/nursing-necessary-degree-of/a-item-severity",
        "description": (
            "A1〜A7 各項目の判定基準、対象/対象外の境界、"
            "令和8改定での変更点（A1 褥瘡除外、A3 注射薬剤 3 種類、A7 2 日間 等）を網羅。"
        ),
    },
    {
        "title": "公式 看護必要度 評価項目表（A・B・C 項目、令和8改定）(画像)",
        "kind": "image",
        "local_path": "docs/admin/references/nursing_necessity_evaluation_2026.png",
        "original_url": "https://www.imimed.co.jp/int/spot/medical-fee_2026_1/",
        "description": "厚労省公開資料を IMI が見やすく整理した評価項目一覧表。判定に迷ったときの正典。",
    },
    {
        "title": "公式 地域包括医療病棟入院料 1/2 施設基準まとめ（令和8改定）(画像)",
        "kind": "image",
        "local_path": "docs/admin/references/regional_inpatient_2026_criteria.png",
        "original_url": "https://www.imimed.co.jp/int/spot/medical-fee_2026_1/",
        "description": "入院料 1/2 の点数、看護配置、平均在院日数、救急、リハビリ、在宅復帰率の総覧。",
    },
]


def render_references(streamlit_module, project_root: str) -> None:
    """参考エビデンス・出典を Streamlit で描画する.

    各参考資料はエキスパンダーで開閉可能、PDF はダウンロードボタン、
    要約 markdown はインライン表示、画像は st.image で表示。

    Args:
        streamlit_module: ``streamlit`` モジュール（``import streamlit as st`` で渡す）
        project_root: プロジェクトルートの絶対パス（CSV/PDF 解決の起点）
    """
    import os

    st = streamlit_module
    st.markdown("#### 📚 参考エビデンス・出典(オフライン対応)")
    st.caption(
        "院内 LAN 環境でも全資料を参照可能。各エキスパンダーをクリックで展開。"
        "原典 URL はネット接続時の検証用。"
    )

    for ref in REFERENCES:
        title = ref.get("title", "(無題)")
        kind = ref.get("kind", "url")
        local_path_rel = ref.get("local_path", "")
        original_url = ref.get("original_url", "")
        description = ref.get("description", "")

        local_path_abs = os.path.join(project_root, local_path_rel) if local_path_rel else ""
        exists = os.path.exists(local_path_abs) if local_path_abs else False

        # アイコン
        icon_map = {"pdf": "📄", "excerpt": "📝", "image": "🖼️"}
        icon = icon_map.get(kind, "🔗")

        # エキスパンダーラベル
        label = f"{icon} {title}"
        if not exists:
            label = f"{label}  ⚠️ ローカル未配置"

        with st.expander(label, expanded=False):
            if description:
                st.markdown(f"**説明**: {description}")

            if kind == "pdf" and exists:
                size_kb = ref.get("size_kb")
                size_label = f" ({size_kb:,} KB)" if size_kb else ""
                with open(local_path_abs, "rb") as f:
                    st.download_button(
                        f"📥 PDF をダウンロード{size_label}",
                        data=f.read(),
                        file_name=os.path.basename(local_path_abs),
                        mime="application/pdf",
                        key=f"nn_dl_{os.path.basename(local_path_abs)}",
                    )
                st.caption(
                    f"📍 ローカル: `{local_path_rel}`／"
                    f"原典: {original_url}（ネット接続時に確認）"
                )

            elif kind == "excerpt" and exists:
                with open(local_path_abs, "r", encoding="utf-8") as f:
                    excerpt_md = f.read()
                st.markdown(excerpt_md)
                st.caption(f"📍 ローカル: `{local_path_rel}`")

            elif kind == "image" and exists:
                st.image(local_path_abs, use_container_width=True)
                st.caption(
                    f"📍 ローカル: `{local_path_rel}`／"
                    f"原典: {original_url}（ネット接続時に確認）"
                )

            else:
                st.warning(
                    f"⚠️ ローカルファイルが見つかりません: `{local_path_rel}`\n\n"
                    f"原典 URL: {original_url}（ネット接続時に確認）"
                )
