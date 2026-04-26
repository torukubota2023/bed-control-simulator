"""看護必要度 疾患別マニュアル — 医師担当部分の判断・処置リファレンス.

副院長要望 (2026-04-26):
    看護必要度ミニレクチャー (概念整理) と並列に、疾患入口型の
    実臨床リファレンスを提供する。「この患者を見たらどう判断するか」を
    17 疾患について網羅。

色分け (レクチャーと統一):
    🟠 A 項目 (オレンジ #F59E0B) — 入院中の処置・薬剤
    🔵 B 項目 (青 #2563EB)       — 患者の状況等 (新基準では評価不要)
    🟢 C 項目 (緑 #10B981)       — 手術・侵襲的処置 (4-5 日カウント)

Single source of truth:
    DISEASE_DATA (構造化リスト) を起点に、
    - DISEASE_MANUAL_MARKDOWN (Streamlit 表示用)
    - generate_docx() (院内 LAN 配布用 DOCX、Word で開いて PDF 化可能)
    の両方を自動生成する。

CLI:
    .venv/bin/python scripts/nursing_necessity_disease_manual.py
        → docs/admin/nursing_necessity_disease_manual.md を再生成
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 色トークン (markdown 内で span style として使用)
# ---------------------------------------------------------------------------

COLOR_A = "#F59E0B"  # オレンジ
COLOR_B = "#2563EB"  # 青
COLOR_C = "#10B981"  # 緑

A_TAG = f'<span style="color:{COLOR_A};font-weight:bold">'
C_TAG = f'<span style="color:{COLOR_C};font-weight:bold">'
END_TAG = "</span>"


def _a(text: str) -> str:
    """A 項目用のオレンジ強調."""
    return f"{A_TAG}🟠 {text}{END_TAG}"


def _c(text: str) -> str:
    """C 項目用の緑強調."""
    return f"{C_TAG}🟢 {text}{END_TAG}"


# ---------------------------------------------------------------------------
# DISEASE_DATA: single source of truth
# ---------------------------------------------------------------------------

# 構造:
# [
#   ("疾患群名 (絵文字付き)", [
#       {
#           "id": int,
#           "name": "疾患名",
#           "icon": "絵文字",
#           "entry": [str, ...],            # 入口 (こんな患者を見たら)
#           "options": [                    # 第一選択 vs 看護必要度貢献選択肢
#               {"scene": "...", "conventional": "...", "necessity": "..."}
#           ],
#           "contributions": [str, ...],    # 看護必要度寄与
#           "evidence": [                   # エビデンス
#               {"strength": "強/中/弱", "ref": "PMID xxx or 日循 GL", "summary": "..."}
#           ],
#           "guardrails": [str, ...],       # 倫理ガードレール
#           "orders": [str, ...],           # オーダー例
#       },
#       ...
#   ]),
#   ...
# ]

DISEASE_DATA: list[tuple[str, list[dict[str, Any]]]] = [
    # ========================================================================
    # 🍽️ 消化器 (6 疾患)
    # ========================================================================
    ("🍽️ 消化器系疾患", [
        {
            "id": 1,
            "name": "急性膵炎（重症）",
            "icon": "🍽️",
            "entry": [
                "上腹部激痛 + アミラーゼ・リパーゼ高値、CT 重症度スコア高",
                "BISAP ≥ 3 / Ranson 高 / 持続性 SIRS",
                "経口摂取困難で 3 日以上の絶食 + 持続点滴が必要",
            ],
            "options": [
                {
                    "scene": "鎮痛",
                    "conventional": "アセトアミノフェン IV / NSAIDs (腎機能注意)",
                    "necessity": _a("A6③ モルヒネ持続点滴") + " — 入院当日開始安全",
                },
                {
                    "scene": "持続点滴のルート",
                    "conventional": "末梢繰り返し穿刺",
                    "necessity": _c("C23 CV 挿入") + " — A 項目ハブ・C 項目両取り",
                },
            ],
            "contributions": [
                _a("A6③ 麻薬注射") + ": **3 点 / 日 × 3-5 日**",
                _a("A4 シリンジポンプ") + ": 1 点（同時計上可）",
                _c("C23 CV 挿入実施日") + ": 4 日カウント (該当患者扱い)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "[PMID 38439202](https://pubmed.ncbi.nlm.nih.gov/38439202/)",
                    "summary": "Pandanaboyana et al. UEG Journal 2024 (118 施設、27 国、1768 例) — 入院当日のオピオイド開始は安全、6 日以上で重症化リスク↑",
                },
            ],
            "guardrails": [
                "重症度評価に基づく適応判断（軽症膵炎では不要）",
                "6 日以上の継続は重症化リスクあり、48 時間ごとに継続要否を再評価",
                "経口移行可能になり次第切替（疼痛コントロール十分後）",
            ],
            "orders": [
                "「モルヒネ持続点滴 3 日間予定、症状次第で延長」(A6③ 3 点/日)",
                "「アミラーゼ・リパーゼ・CRP 1 日 1 回モニター」",
                "CV 挿入オーダー（持続点滴・栄養管理目的）",
            ],
        },
        {
            "id": 2,
            "name": "急性胆管炎・閉塞性黄疸",
            "icon": "🍽️",
            "entry": [
                "Charcot 三徴 (発熱・黄疸・右上腹部痛)",
                "胆道酵素上昇 + 画像で胆道拡張・結石・腫瘍",
                "東京ガイドライン Grade II/III の中等症〜重症",
            ],
            "options": [
                {
                    "scene": "胆道ドレナージ",
                    "conventional": "保存的管理 + 抗菌薬のみで経過観察",
                    "necessity": _c("C21③ ERCP + 胆管ステント / EBD") + " — Grade II 以上で 24-48 時間以内に",
                },
                {
                    "scene": "経乳頭的アプローチ困難例",
                    "conventional": "手術的胆道ドレナージを検討",
                    "necessity": _c("C21③ PTCD（経皮経肝胆道ドレナージ）") + " — 術後は " + _a("A6⑩ ドレナージ管理"),
                },
            ],
            "contributions": [
                _c("C21③ 侵襲的消化器治療") + ": **4 日カウント** / 各処置",
                _a("A6⑩ ドレナージ管理") + ": 2 点 / 留置中毎日 (PTCD 後)",
                _a("A4 シリンジポンプ") + " + " + _a("A3 注射薬剤 3 種類以上") + ": 2 点 (β-ラクタム持続併用時)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "東京ガイドライン (TG18)",
                    "summary": "Grade II 以上の急性胆管炎は早期胆道ドレナージ推奨、Grade III は緊急 (24h 以内)",
                },
            ],
            "guardrails": [
                "Grade I (軽症) では保存的治療優先、不必要な ERCP は行わない",
                "出血傾向・抗血栓薬使用例では PTCD 優先",
                "ERCP は消化器内科コンサルト、適応の医学的妥当性を確認",
            ],
            "orders": [
                "「ERCP + 胆管ステント留置依頼 (Grade II 急性胆管炎)」",
                "「PIPC/TAZ 4.5g IV q8h or 持続点滴で開始」",
                "「PTCD 留置後は排液量・性状を 6h ごと記録」",
            ],
        },
        {
            "id": 3,
            "name": "消化管出血",
            "icon": "🍽️",
            "entry": [
                "吐血・下血・タール便、Hb 低下 (≥ 2g/dL)",
                "ショック傾向 / 起立性低血圧 / 頻脈",
                "PPI 内服歴・NSAIDs・抗血栓薬使用歴",
            ],
            "options": [
                {
                    "scene": "出血源同定と止血",
                    "conventional": "保存的 (PPI IV) + 様子観察",
                    "necessity": _c("C21③ 内視鏡的止血術") + " — 上部・下部消化管出血で 24h 以内に",
                },
                {
                    "scene": "Hb 低下例",
                    "conventional": "経過観察 + 鉄剤",
                    "necessity": _a("A5 輸血や血液製剤の管理") + " — RBC 輸血実施で 2 点",
                },
            ],
            "contributions": [
                _c("C21③ 内視鏡的止血") + ": **4 日カウント**",
                _a("A5 輸血管理") + ": 2 点 / 輸血実施日 (該当患者扱い)",
                _a("A6⑨ 抗血栓持続") + " (UFH への切替時): 3 点 / 日",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "ACG ガイドライン 2021 (Laine et al.)",
                    "summary": "高リスク出血潰瘍は早期内視鏡 (24h 以内) + 内視鏡的止血で再出血率減少",
                },
            ],
            "guardrails": [
                "輸血は適応基準 (Hb < 7 g/dL or 症状あり) に基づく、過剰輸血を避ける",
                "抗血栓薬は出血リスクと血栓リスクを天秤にかけ、安易な再開は避ける",
                "内視鏡は消化器内科判断、緊急度に応じて時間設定",
            ],
            "orders": [
                "「緊急上部消化管内視鏡 (吐血、Hb 8.5)」",
                "「RBC 2 単位輸血、輸血前後 Hb 測定」",
                "「PPI (オメプラゾール) 80mg ボーラス → 8mg/h 持続」",
            ],
        },
        {
            "id": 4,
            "name": "早期消化管腫瘍（食道・胃・大腸）",
            "icon": "🍽️",
            "entry": [
                "内視鏡で発見された早期癌 (T1a/cT1b)",
                "脈管侵襲なし、リンパ節転移リスク低",
                "ESD/EMR 適応 (絶対適応 / 拡大適応)",
            ],
            "options": [
                {
                    "scene": "早期癌の治療選択",
                    "conventional": "手術 (外科紹介) を即決",
                    "necessity": _c("C21③ ESD / EMR") + " — 適応症例で内視鏡的切除を積極化",
                },
            ],
            "contributions": [
                _c("C21③ 侵襲的消化器治療") + ": **4 日カウント**",
                _a("A1 創傷処置") + ": 1 点 / 日 (穿孔・出血合併時のドレナージ管理)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "胃癌治療ガイドライン (日本胃癌学会)",
                    "summary": "ESD 絶対適応病変は 5 年生存率が外科手術と同等、QOL 維持に優位",
                },
            ],
            "guardrails": [
                "ESD/EMR の適応病変か慎重に判断（消化器内科・病理コンサルト）",
                "穿孔・後出血リスクの説明と同意",
                "拡大適応病変は症例検討で慎重に",
            ],
            "orders": [
                "「ESD 予定 (早期胃癌、絶対適応)」",
                "「術後 24 時間絶食、ドレーン留置・排液モニター」",
                "「術後出血モニター (Hb 6h ごと、12 時間)」",
            ],
        },
        {
            "id": 5,
            "name": "嚥下障害（経口摂取困難）",
            "icon": "🍽️",
            "entry": [
                "脳卒中後・神経変性疾患・頭頸部癌術後の嚥下機能低下",
                "VF / VE で誤嚥確認、経口摂取で誤嚥性肺炎反復",
                "経鼻胃管 (NG) 長期化 (4 週間以上) で QOL 低下",
            ],
            "options": [
                {
                    "scene": "長期栄養経路",
                    "conventional": "NG 継続 / TPN（CV 経由）",
                    "necessity": _c("C23 PEG 造設") + " — 長期見込みで 4 週後を目処に",
                },
            ],
            "contributions": [
                _c("C23 別に定める手術・処置 (PEG)") + ": **5 日カウント** (該当患者扱い)",
                _a("A1 創傷処置") + ": 1 点 / 日 (PEG 創部管理)",
            ],
            "evidence": [
                {
                    "strength": "中",
                    "ref": "Lancet 2005 FOOD trial",
                    "summary": "脳卒中後の早期 PEG vs NG 継続は転帰差なし、しかし長期 (>4 週) は PEG が QOL 優位",
                },
            ],
            "guardrails": [
                "予後 4 週以上を見込む症例で適応 (短期見込みは NG で対応)",
                "本人・家族との十分な説明と同意 (terminal care 例では適応外)",
                "PEG 後の経口訓練継続を放棄しない",
            ],
            "orders": [
                "「PEG 造設依頼 (脳梗塞後嚥下障害、4 週経過)」",
                "「PEG 後 24 時間絶食、創部消毒 1 日 1 回」",
                "「PEG 経管栄養 開始 (200 kcal × 3 → 漸増)」",
            ],
        },
        {
            "id": 6,
            "name": "複雑性腹腔内感染 (cIAI)",
            "icon": "🍽️",
            "entry": [
                "穿孔性虫垂炎・憩室炎穿孔・術後腹腔内膿瘍",
                "発熱 + 腹膜刺激症状 + CT で膿瘍・遊離ガス",
                "重症度評価 (qSOFA、APACHE II)",
            ],
            "options": [
                {
                    "scene": "抗菌薬投与",
                    "conventional": "セフメタゾール / セフトリアキソン IV (間欠)",
                    "necessity": _a("A4 + A3 ペア") + " — PIPC/TAZ・MEPM 持続点滴 + 多剤併用",
                },
                {
                    "scene": "膿瘍ドレナージ",
                    "conventional": "保存的に抗菌薬のみで経過観察",
                    "necessity": _a("A6⑩ ドレナージ (PCD)") + " — IR ガイド下に経皮的に",
                },
            ],
            "contributions": [
                _a("A4 シリンジポンプ") + " + " + _a("A3 注射薬剤 3 種類以上") + ": **2 点** (該当患者)",
                _a("A6⑩ ドレナージ管理") + ": 2 点 / 留置中毎日",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "IDSA cIAI ガイドライン 2010",
                    "summary": "5cm 以上の膿瘍はドレナージ必須、抗菌薬は適切なスペクトラムで 4-7 日",
                },
                {
                    "strength": "中",
                    "ref": "[PMID 38864155](https://pubmed.ncbi.nlm.nih.gov/38864155/)",
                    "summary": "BLING-III RCT — β-ラクタム持続点滴は 90 日死亡で有意差なしだがメタ解析では有意 (重症で合理的)",
                },
            ],
            "guardrails": [
                "ドレナージ可能な膿瘍は積極的に IR コンサルト",
                "抗菌薬持続点滴は重症例 (qSOFA ≥ 2) に限定、軽症は間欠投与",
                "培養結果で 48-72h 後に de-escalation",
            ],
            "orders": [
                "「PIPC/TAZ 4.5g 負荷 → 13.5g/24h 持続点滴」",
                "「腹腔内膿瘍 PCD 留置依頼 (IR)」",
                "「血液培養 2 セット + 膿瘍液培養」",
            ],
        },
    ]),
    # ========================================================================
    # 🫁 呼吸器 (3 疾患)
    # ========================================================================
    ("🫁 呼吸器系疾患", [
        {
            "id": 7,
            "name": "重症肺炎（CURB-65 高、ICU 候補・ショックなし）",
            "icon": "🫁",
            "entry": [
                "CURB-65 ≥ 3、A-DROP ≥ 3、PSI Class IV/V",
                "SpO2 < 90% (room air)、呼吸数 ≥ 30",
                "意識障害なし、血圧維持できているがハイリスク",
            ],
            "options": [
                {
                    "scene": "抗菌薬選択",
                    "conventional": "セフトリアキソン + アジスロマイシン (間欠)",
                    "necessity": _a("A4 + A3 ペア") + " — PIPC/TAZ 持続点滴 + シリンジポンプ",
                },
                {
                    "scene": "酸素管理",
                    "conventional": "鼻カニュラで様子観察",
                    "necessity": _a("A2 呼吸ケア (酸素 A2)") + " — 高流量鼻カニュラで確実に確保",
                },
            ],
            "contributions": [
                _a("A4 + A3") + ": **2 点** (該当患者)",
                _a("A2 呼吸ケア (酸素 A2)") + ": 1 点 / 日 (酸素必要日)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "ATS/IDSA CAP ガイドライン 2019",
                    "summary": "重症 CAP は β-ラクタム + マクロライド or キノロン併用、ICU 適応評価必須",
                },
                {
                    "strength": "中",
                    "ref": "[PMID 38864155](https://pubmed.ncbi.nlm.nih.gov/38864155/)",
                    "summary": "BLING-III: β-ラクタム持続点滴は重症感染症で合理的、メタ解析では NNT 26",
                },
            ],
            "guardrails": [
                "持続点滴は CURB-65 ≥ 3 の重症例に限定",
                "経口移行・de-escalation は培養結果と臨床経過で判断",
                "ICU 適応の見極め (呼吸不全進行・ショック移行) を逃さない",
            ],
            "orders": [
                "「PIPC/TAZ 4.5g 負荷 → 13.5g/24h 持続」",
                "「アジスロマイシン 500mg IV q24h」",
                "「血液培養 2 セット + 喀痰培養 + 尿中肺炎球菌・レジオネラ抗原」",
            ],
        },
        {
            "id": 8,
            "name": "気胸・膿胸・血胸",
            "icon": "🫁",
            "entry": [
                "突然の胸痛・呼吸困難、画像で気胸・胸水・血腫確認",
                "緊張性気胸 (緊急)、大量胸水 (>1L)",
                "外傷後の血胸、膿胸 (CT で液貯留 + 胸壁肥厚)",
            ],
            "options": [
                {
                    "scene": "胸腔ドレナージ",
                    "conventional": "保存的に経過観察 (小さい気胸)",
                    "necessity": _a("A6⑩ 胸腔ドレナージ") + " — 中等度以上で挿入閾値を下げる",
                },
            ],
            "contributions": [
                _a("A6⑩ ドレナージの管理") + ": **2 点 / 留置中毎日** (該当患者)",
                _a("A1 創傷処置") + ": 1 点 / 日 (ドレーン創部管理)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "BTS ガイドライン 2010",
                    "summary": "症候性気胸 (≥ 2cm) は胸腔ドレナージ推奨、膿胸は早期外科介入も検討",
                },
            ],
            "guardrails": [
                "小気胸 (< 2cm、無症状) は経過観察が原則",
                "ドレーン抜去は持続的な脱気・排液停止 + 画像改善で判断",
                "膿胸は線維素性で胸膜癒着あり、外科コンサルトを早期に",
            ],
            "orders": [
                "「胸腔ドレーン挿入 (24Fr、第 5 肋間中腋窩線)」",
                "「ドレナージ排液量・性状 6h ごと記録」",
                "「胸部 X 線 翌朝 + ドレーン抜去前」",
            ],
        },
        {
            "id": 9,
            "name": "高リスク PE / CrCl<30 DVT",
            "icon": "🫁",
            "entry": [
                "造影 CT で肺動脈本幹〜葉動脈の血栓 (高リスク PE)",
                "右心負荷所見 (RV/LV ≥ 1.0、TAPSE 低下、トロポニン上昇)",
                "腎不全 (CrCl < 30) で DOAC・LMWH が使用しにくい",
            ],
            "options": [
                {
                    "scene": "抗凝固",
                    "conventional": "DOAC (アピキサバン・リバーロキサバン)",
                    "necessity": _a("A6⑨ UFH 持続点滴") + " — 高リスク PE / CrCl<30 で第一選択",
                },
            ],
            "contributions": [
                _a("A6⑨ 抗血栓塞栓薬の持続点滴") + ": **3 点 / 日 × 3-7 日**",
                _a("A4 シリンジポンプ") + ": 1 点 (UFH 持続併用)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "[日循 2025 GL](docs/admin/references/pdf/jcs2025_pte_dvt_guideline.pdf)",
                    "summary": "DOAC 第一選択だが、高リスク PE / CrCl<30 では UFH 持続が推奨",
                },
            ],
            "guardrails": [
                "出血リスク (HAS-BLED スコア等) を必ず評価",
                "APTT モニタリング (1.5-2.5 倍) で用量調整",
                "臨床的安定後 (24-48h) に DOAC 切替を検討",
            ],
            "orders": [
                "「UFH 80 単位/kg 負荷 → 18 単位/kg/h 持続」",
                "「APTT 6 時間ごと、目標 1.5-2.5 倍」",
                "「血小板数 3 日後 (HIT スクリーニング)」",
            ],
        },
    ]),
    # ========================================================================
    # ❤️ 循環器 (2 疾患)
    # ========================================================================
    ("❤️ 循環器系疾患", [
        {
            "id": 10,
            "name": "重症 Af / 心房粗動（血行動態不安定）",
            "icon": "❤️",
            "entry": [
                "心房細動・粗動 + 頻脈 (HR > 130) + 血圧低下",
                "胸痛・心不全症状の合併",
                "経口β遮断薬・Ca 拮抗薬で コントロール不十分",
            ],
            "options": [
                {
                    "scene": "心拍コントロール",
                    "conventional": "経口メトプロロール・ビソプロロール",
                    "necessity": _a("A6⑧ IV アミオダロン") + " — 血行動態不安定で第一選択",
                },
            ],
            "contributions": [
                _a("A6⑧ 抗不整脈剤の使用") + ": **3 点 / 日 × 1-3 日**",
                _a("A4 シリンジポンプ") + ": 1 点 (アミオダロン持続併用)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "[PMID 39210723](https://pubmed.ncbi.nlm.nih.gov/39210723/)",
                    "summary": "2024 ESC AF GL — 血行動態不安定例で IV アミオダロン推奨",
                },
            ],
            "guardrails": [
                "甲状腺機能・肝機能・QT 評価必須 (アミオダロン使用前)",
                "電気的除細動の適応 (重度血行動態不安定) も考慮",
                "心拍コントロール後は経口移行を 24-48h で判断",
            ],
            "orders": [
                "「アミオダロン 150mg ローディング → 1mg/min × 6h → 0.5mg/min」",
                "「心電図モニター継続、QT 8 時間ごと」",
                "「TSH・FT4・AST/ALT 投与前」",
            ],
        },
        {
            "id": 11,
            "name": "心不全急性増悪（hot/wet 型）",
            "icon": "❤️",
            "entry": [
                "急性肺水腫 + 起座呼吸 + SpO2 低下",
                "末梢冷感・血圧不安定 (cardiogenic shock 移行リスク)",
                "BNP 高値、CXR で肺うっ血",
            ],
            "options": [
                {
                    "scene": "血行動態維持",
                    "conventional": "利尿剤のみで経過観察",
                    "necessity": _a("A6⑦ NE/DOA/DOB 持続点滴") + " — 低血圧合併で必要十分な期間維持",
                },
            ],
            "contributions": [
                _a("A6⑦ 昇圧剤の使用") + ": **3 点 / 日 × 1-3 日**",
                _a("A4 シリンジポンプ") + ": 1 点 (昇圧剤持続)",
                _a("A2 呼吸ケア (酸素 A2)") + ": 1 点 / 日 (酸素必要日)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "[PMID 34599691](https://pubmed.ncbi.nlm.nih.gov/34599691/)",
                    "summary": "Surviving Sepsis 2021 — NE 第一選択 (cardiogenic shock も準用)、心機能低下時は ± dobutamine",
                },
            ],
            "guardrails": [
                "cardiogenic shock の早期認識 (lactate、SvO2)",
                "早すぎる昇圧剤離脱を避ける（必要十分な期間維持）",
                "利尿剤過剰で腎前性 AKI を起こさない",
            ],
            "orders": [
                "「ノルアドレナリン 0.05 μg/kg/min 開始、MAP > 65 維持」",
                "「ドブタミン 5 μg/kg/min 併用 (心機能低下例)」",
                "「Aライン留置、CVP モニター」",
            ],
        },
    ]),
    # ========================================================================
    # 🦠 感染症 (3 疾患)
    # ========================================================================
    ("🦠 感染症（昇圧剤適応・非適応）", [
        {
            "id": 12,
            "name": "敗血症・敗血症性ショック",
            "icon": "🦠",
            "entry": [
                "感染巣同定 + qSOFA ≥ 2 / SOFA score 上昇",
                "MAP < 65 (輸液後も)、lactate > 2 mmol/L",
                "意識障害・乏尿・末梢冷感",
            ],
            "options": [
                {
                    "scene": "昇圧剤",
                    "conventional": "輸液のみで経過観察",
                    "necessity": _a("A6⑦ NE 持続点滴") + " — Surviving Sepsis 2021 第一選択",
                },
                {
                    "scene": "抗菌薬",
                    "conventional": "セフトリアキソン IV (間欠)",
                    "necessity": _a("A4 + A3 ペア") + " — PIPC/TAZ・MEPM 持続点滴 (重症で合理的)",
                },
            ],
            "contributions": [
                _a("A6⑦ 昇圧剤") + ": **3 点 / 日**",
                _a("A4 + A3") + ": 2 点 (β-ラクタム持続併用時、該当患者ダブル達成)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "[PMID 34599691](https://pubmed.ncbi.nlm.nih.gov/34599691/)",
                    "summary": "Surviving Sepsis Campaign 2021 — NE 第一選択、心機能低下時は ± dobutamine",
                },
            ],
            "guardrails": [
                "感染源コントロール (drainage、source control) を最優先",
                "1 時間バンドル (培養 → 広域抗菌薬 → 輸液 → 昇圧剤) 遵守",
                "lactate clearance + SvO2 で輸液・昇圧剤調整",
            ],
            "orders": [
                "「NE 0.05 μg/kg/min 開始、MAP > 65 維持」",
                "「PIPC/TAZ 4.5g 負荷 → 13.5g/24h 持続」",
                "「血液培養 2 セット (抗菌薬投与前)」",
            ],
        },
        {
            "id": 13,
            "name": "発熱性好中球減少症 (FN)",
            "icon": "🦠",
            "entry": [
                "化学療法後 7-10 日 (好中球最低期)",
                "好中球数 < 500 /μL + 発熱 (38.3℃以上 or 38.0℃以上 1h 持続)",
                "MASCC スコアで高リスク (< 21)",
            ],
            "options": [
                {
                    "scene": "経験的抗菌薬",
                    "conventional": "セフェピム IV (間欠)",
                    "necessity": _a("A4 + A3 ペア") + " — PIPC/TAZ・MEPM 持続点滴 (免疫不全で trough 重要)",
                },
            ],
            "contributions": [
                _a("A4 + A3") + ": **2 点** (該当患者)",
                _a("A2 呼吸ケア (酸素 A2)") + ": 1 点 (呼吸器症状あれば)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "IDSA FN ガイドライン 2010",
                    "summary": "高リスク FN は早期広域抗菌薬 IV (1h 以内)、低リスクは経口切替検討",
                },
                {
                    "strength": "中",
                    "ref": "[PMID 38864155](https://pubmed.ncbi.nlm.nih.gov/38864155/)",
                    "summary": "BLING-III: 免疫不全例での持続点滴は trough 維持に有利",
                },
            ],
            "guardrails": [
                "MASCC スコアで高/低リスク層別、低リスクは外来管理も検討",
                "G-CSF 投与の適応評価 (高リスク・遷延)",
                "培養結果で 48-72h 以内に de-escalation",
            ],
            "orders": [
                "「PIPC/TAZ 4.5g 負荷 → 13.5g/24h 持続」",
                "「血液培養 2 セット (末梢 + CV)」",
                "「G-CSF (フィルグラスチム 75μg/日 SC) 適応評価」",
            ],
        },
        {
            "id": 14,
            "name": "重症腎盂腎炎（ESBL 等高 MIC）",
            "icon": "🦠",
            "entry": [
                "発熱・腰背部痛・CVA tenderness + 尿沈渣 WBC ≥ 10/HPF",
                "尿培養で ESBL 産生大腸菌・KP 検出 (or 既往あり)",
                "qSOFA ≥ 1、SIRS 合併",
            ],
            "options": [
                {
                    "scene": "抗菌薬",
                    "conventional": "セフトリアキソン IV (ESBL では無効)",
                    "necessity": _a("A4 + A3 ペア") + " — MEPM 持続点滴 + 多剤併用 (高 MIC で %T>MIC 重要)",
                },
            ],
            "contributions": [
                _a("A4 + A3") + ": **2 点** (該当患者)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "IDSA UTI ガイドライン",
                    "summary": "ESBL 産生菌による複雑性 UTI はカルバペネム第一選択",
                },
                {
                    "strength": "中",
                    "ref": "[PMID 38864155](https://pubmed.ncbi.nlm.nih.gov/38864155/)",
                    "summary": "高 MIC 菌では持続点滴で %T>MIC を確保するメリットあり",
                },
            ],
            "guardrails": [
                "閉塞性腎盂腎炎 (結石・腫瘍) は緊急ドレナージ (尿管ステント・PCN) 検討",
                "ESBL 既往 + 重症で empiric MEPM、培養結果で見直し",
                "腎機能評価で用量調整",
            ],
            "orders": [
                "「MEPM 1g 負荷 → 3g/24h 持続 (CrCl 80 想定)」",
                "「腹部 CT (閉塞・膿瘍評価)」",
                "「尿培養 + 血液培養 2 セット」",
            ],
        },
    ]),
    # ========================================================================
    # 🩹 創傷 (2 疾患)
    # ========================================================================
    ("🩹 創傷・皮膚軟部組織感染症", [
        {
            "id": 15,
            "name": "蜂窩織炎",
            "icon": "🩹",
            "entry": [
                "発赤・腫脹・熱感・圧痛 + 発熱",
                "境界不明瞭な紅斑、リンパ管炎所見あり",
                "重症化・壊死性筋膜炎との鑑別 (LRINEC スコア)",
            ],
            "options": [
                {
                    "scene": "創傷処置",
                    "conventional": "観察のみ、抗菌薬内服のみ",
                    "necessity": _a("A1 創傷処置 (褥瘡を除く)") + " + " + _a("A3 注射薬剤 3 種類") + " — 洗浄・被覆 + IV 抗菌薬 + 補液 + 鎮痛",
                },
            ],
            "contributions": [
                _a("A1 + A3") + ": **2 点** (該当患者)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "IDSA SSTI ガイドライン 2014",
                    "summary": "中等症以上の蜂窩織炎は IV β-ラクタム、外来治療失敗例は入院",
                },
            ],
            "guardrails": [
                "壊死性筋膜炎の見逃しに注意 (緊急外科コンサルト)",
                "MRSA リスク評価 (院内、ホームレス、IVDU)",
                "下肢・糖尿病例では深部感染・骨髄炎評価",
            ],
            "orders": [
                "「セファゾリン 1g IV q8h」",
                "「創部洗浄 1 日 1 回 + 滅菌ガーゼ被覆」",
                "「下肢挙上、安静」",
            ],
        },
        {
            "id": 16,
            "name": "糖尿病性足病変（感染合併）",
            "icon": "🩹",
            "entry": [
                "DM 患者の足部潰瘍・蜂窩織炎・壊疽",
                "Wagner 分類 / IWGDF 分類で評価",
                "X 線・MRI で骨髄炎の有無確認",
            ],
            "options": [
                {
                    "scene": "創傷処置",
                    "conventional": "外来管理を継続",
                    "necessity": _a("A1 創傷処置") + " + " + _a("A3 注射薬剤 3 種類") + " — 入院でデブリードマン + IV 抗菌薬 + 血糖管理 + 補液",
                },
            ],
            "contributions": [
                _a("A1 + A3") + ": **2 点** (該当患者)",
                _a("A6⑩ ドレナージ管理") + ": 2 点 (深部膿瘍・壊死組織のドレナージ後)",
            ],
            "evidence": [
                {
                    "strength": "強",
                    "ref": "IWGDF ガイドライン 2023",
                    "summary": "糖尿病性足感染症は早期評価 + 適切なデブリ + 多分野連携 (整形・形成・血管)",
                },
            ],
            "guardrails": [
                "血糖コントロール改善必須 (HbA1c、入院中血糖プロファイル)",
                "末梢動脈疾患 (PAD) 評価で血行再建も検討",
                "切断回避を最優先 (mortality 上昇の主因)",
            ],
            "orders": [
                "「足部 X 線 + MRI (骨髄炎評価)」",
                "「ABPC/SBT 3g IV q6h」",
                "「創傷洗浄 + デブリードマン (毎日)」",
                "「血糖プロファイル 4 検 (毎食前 + 寝る前)」",
            ],
        },
    ]),
    # ========================================================================
    # 💊 ペイン (1 疾患)
    # ========================================================================
    ("💊 ペイン領域（神経障害性疼痛）", [
        {
            "id": 17,
            "name": "PHN / CRPS / 難治性神経障害性疼痛",
            "icon": "💊",
            "entry": [
                "帯状疱疹後神経痛 (PHN) で経口薬無効 (3 種類以上で改善せず)",
                "CRPS Type I/II の急性期 (灼熱痛、アロディニア)",
                "他治療抵抗性の難治性神経障害性疼痛",
            ],
            "options": [
                {
                    "scene": "難治性神経痛のレスキュー",
                    "conventional": "プレガバリン・トラマドール継続 (経口)",
                    "necessity": _a("A6⑧ IV リドカイン") + " — ペイン科判断で症例選択（**弱エビデンス**）",
                },
            ],
            "contributions": [
                _a("A6⑧ 抗不整脈剤の使用") + ": **3 点 / 日 × 1-7 日**",
                _a("A4 シリンジポンプ") + ": 1 点 (リドカイン持続)",
            ],
            "evidence": [
                {
                    "strength": "弱",
                    "ref": "[PMID 16013891](https://pubmed.ncbi.nlm.nih.gov/16013891/)",
                    "summary": "Hempenstall et al. PLoS Med 2005 — PHN への IV リドカインは効果なしと結論",
                },
                {
                    "strength": "弱",
                    "ref": "[PMID 36288104](https://pubmed.ncbi.nlm.nih.gov/36288104/)",
                    "summary": "Lee et al. Clin J Pain 2022 — IV リドカイン慢性神経障害性疼痛のエビデンス不十分",
                },
            ],
            "guardrails": [
                "**エビデンスは弱い**ことを認識した上でペイン科判断で症例選択",
                "看護必要度のために適応外で投与することは **絶対にやらない**",
                "心電図モニター必須 (QT 延長・不整脈リスク)",
                "効果判定 24-48h で継続要否判断、無効なら速やかに中止",
            ],
            "orders": [
                "「リドカイン 1 mg/kg/h 開始、効果と副作用見て調整 (max 5 mg/kg/h)」",
                "「心電図モニター継続、リドカイン血中濃度 (利用可能なら)」",
                "「ペイン科コンサルト」",
            ],
        },
    ]),
]


# ---------------------------------------------------------------------------
# Markdown 生成 (DISEASE_DATA → DISEASE_MANUAL_MARKDOWN)
# ---------------------------------------------------------------------------

_HEADER = """# 看護必要度 疾患別マニュアル — 医師担当部分

**作成**: おもろまちメディカルセンター 副院長 久保田 徹
**対象**: 地域包括医療病棟入院料1（5F・6F）担当医
**基準日**: 2026-06-01 新基準対応
**位置づけ**: ミニレクチャー（行動変容の概念整理）に対する**疾患入口型 実臨床リファレンス**

---

## 🛡️ 倫理ガードレール（全疾患共通、最上段）

1. **適応外の処置は絶対に行わない**
2. **医学的判断は変わらない** — 適応判断・治療方針は従来通り、ガイドライン準拠
3. **「選び方」の問題として捉える** — 複数の選択肢がある中での選択を意識化する

→ 看護必要度のための過剰治療・適応外投与は医療倫理違反、施設基準取消・診療報酬遡及返還のリスク。

## 🎨 色分け凡例

| 区分 | 色 | 内容 |
|---|---|---|
| 🟠 A 項目 | オレンジ | 入院中の処置・薬剤（毎日評価） |
| 🔵 B 項目 | 青 | 患者の状況等（**新基準では評価不要**） |
| 🟢 C 項目 | 緑 | 手術・侵襲的処置（4-5 日カウント） |

---

## 📚 目次（17 疾患）

"""


def _render_disease_md(d: dict[str, Any]) -> str:
    """1 疾患の dict を markdown ブロックに変換."""
    lines: list[str] = []
    lines.append(f"### {d['id']}. {d['icon']} {d['name']}")
    lines.append("")

    # 入口
    lines.append("#### 🩺 入口（こんな患者を見たら）")
    for e in d["entry"]:
        lines.append(f"- {e}")
    lines.append("")

    # 選択肢比較テーブル
    lines.append("#### 💊 第一選択 vs 看護必要度貢献選択肢（医学的に同等以上）")
    lines.append("")
    lines.append("| 場面 | 従来の選択肢 | 看護必要度に貢献する選択肢 |")
    lines.append("|---|---|---|")
    for opt in d["options"]:
        lines.append(f"| {opt['scene']} | {opt['conventional']} | {opt['necessity']} |")
    lines.append("")

    # 看護必要度寄与
    lines.append("#### 📋 看護必要度寄与")
    for c in d["contributions"]:
        lines.append(f"- {c}")
    lines.append("")

    # エビデンス
    lines.append("#### 📚 エビデンス")
    for ev in d["evidence"]:
        lines.append(f"- **{ev['strength']}**: {ev['ref']} — {ev['summary']}")
    lines.append("")

    # 倫理ガードレール
    lines.append("#### 🛡️ 倫理ガードレール（疾患特異）")
    for g in d["guardrails"]:
        lines.append(f"- {g}")
    lines.append("")

    # オーダー例
    lines.append("#### 📝 オーダー例")
    for o in d["orders"]:
        lines.append(f"- {o}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _build_markdown() -> str:
    """DISEASE_DATA から完全な markdown 文字列を生成."""
    out: list[str] = [_HEADER]

    # 目次
    for group_name, diseases in DISEASE_DATA:
        out.append(f"### {group_name}")
        out.append("")
        for d in diseases:
            out.append(f"- [{d['id']}. {d['icon']} {d['name']}](#{d['id']}-{d['icon']}-{d['name']})")
        out.append("")
    out.append("---")
    out.append("")

    # 本文 (疾患群ごと)
    for group_name, diseases in DISEASE_DATA:
        out.append(f"## {group_name}")
        out.append("")
        for d in diseases:
            out.append(_render_disease_md(d))

    out.append("")
    out.append("---")
    out.append("")
    out.append("*このマニュアルは医師の臨床判断を支援する目的で作成。")
    out.append("医療倫理・診療報酬制度の最新情報は厚労省通知を必ず参照すること。*")

    return "\n".join(out)


DISEASE_MANUAL_MARKDOWN: str = _build_markdown()


# ---------------------------------------------------------------------------
# DOCX 生成 (院内 LAN 配布用、Word で開いて PDF 化可能)
# ---------------------------------------------------------------------------

# 簡易 markdown 除去 (DOCX には HTML span を入れない、絵文字 prefix のみ残す)
def _strip_html(s: str) -> str:
    """span タグを除去して絵文字 + 太字記法を残す."""
    import re
    # <span ...>X</span> → X
    s = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', s, flags=re.DOTALL)
    return s


def generate_docx() -> bytes:
    """疾患別マニュアル DOCX を生成して bytes で返す.

    Streamlit の st.download_button に渡す用途。
    Word で開いて PDF 化することを想定 (高度な書式は使わない)。
    """
    from docx import Document
    from docx.shared import Pt, Cm

    doc = Document()

    # 既定スタイル (日本語フォント)
    style = doc.styles["Normal"]
    style.font.name = "Yu Gothic"
    style.font.size = Pt(11)

    # ページ余白 (A4 縦)
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # タイトル
    doc.add_heading("看護必要度 疾患別マニュアル — 医師担当部分", level=0)
    doc.add_paragraph("作成: おもろまちメディカルセンター 副院長 久保田 徹")
    doc.add_paragraph("対象: 地域包括医療病棟入院料1（5F・6F）担当医")
    doc.add_paragraph("基準日: 2026-06-01 新基準対応")
    doc.add_paragraph("位置づけ: ミニレクチャー（行動変容の概念整理）に対する疾患入口型 実臨床リファレンス")

    # 倫理ガードレール
    doc.add_heading("🛡️ 倫理ガードレール（全疾患共通、最上段）", level=1)
    for line in [
        "1. 適応外の処置は絶対に行わない",
        "2. 医学的判断は変わらない — 適応判断・治療方針は従来通り、ガイドライン準拠",
        "3. 「選び方」の問題として捉える — 複数の選択肢がある中での選択を意識化する",
    ]:
        doc.add_paragraph(line)
    doc.add_paragraph(
        "→ 看護必要度のための過剰治療・適応外投与は医療倫理違反、"
        "施設基準取消・診療報酬遡及返還のリスク。"
    )

    # 色分け凡例
    doc.add_heading("🎨 色分け凡例", level=1)
    legend_table = doc.add_table(rows=4, cols=3)
    legend_table.style = "Light Grid"
    cells = legend_table.rows[0].cells
    cells[0].text = "区分"
    cells[1].text = "色"
    cells[2].text = "内容"
    legend_data = [
        ("🟠 A 項目", "オレンジ", "入院中の処置・薬剤（毎日評価）"),
        ("🔵 B 項目", "青", "患者の状況等（新基準では評価不要）"),
        ("🟢 C 項目", "緑", "手術・侵襲的処置（4-5 日カウント）"),
    ]
    for i, row_data in enumerate(legend_data, start=1):
        for j, val in enumerate(row_data):
            legend_table.rows[i].cells[j].text = val

    doc.add_page_break()

    # 17 疾患を疾患群ごとに章立て
    for group_name, diseases in DISEASE_DATA:
        doc.add_heading(group_name, level=1)
        for d in diseases:
            doc.add_heading(f"{d['id']}. {d['icon']} {d['name']}", level=2)

            # 入口
            doc.add_heading("🩺 入口（こんな患者を見たら）", level=3)
            for e in d["entry"]:
                doc.add_paragraph(_strip_html(e), style="List Bullet")

            # 選択肢比較テーブル
            doc.add_heading("💊 第一選択 vs 看護必要度貢献選択肢", level=3)
            opt_table = doc.add_table(rows=1 + len(d["options"]), cols=3)
            opt_table.style = "Light Grid"
            opt_table.rows[0].cells[0].text = "場面"
            opt_table.rows[0].cells[1].text = "従来の選択肢"
            opt_table.rows[0].cells[2].text = "看護必要度に貢献する選択肢"
            for i, opt in enumerate(d["options"], start=1):
                opt_table.rows[i].cells[0].text = _strip_html(opt["scene"])
                opt_table.rows[i].cells[1].text = _strip_html(opt["conventional"])
                opt_table.rows[i].cells[2].text = _strip_html(opt["necessity"])

            # 看護必要度寄与
            doc.add_heading("📋 看護必要度寄与", level=3)
            for c in d["contributions"]:
                doc.add_paragraph(_strip_html(c), style="List Bullet")

            # エビデンス
            doc.add_heading("📚 エビデンス", level=3)
            for ev in d["evidence"]:
                doc.add_paragraph(
                    f"[{ev['strength']}] {_strip_html(ev['ref'])} — {_strip_html(ev['summary'])}",
                    style="List Bullet",
                )

            # 倫理ガードレール
            doc.add_heading("🛡️ 倫理ガードレール（疾患特異）", level=3)
            for g in d["guardrails"]:
                doc.add_paragraph(_strip_html(g), style="List Bullet")

            # オーダー例
            doc.add_heading("📝 オーダー例", level=3)
            for o in d["orders"]:
                doc.add_paragraph(_strip_html(o), style="List Bullet")

            doc.add_paragraph("")  # 疾患間スペース

    # 締め
    doc.add_page_break()
    doc.add_paragraph(
        "このマニュアルは医師の臨床判断を支援する目的で作成。"
        "医療倫理・診療報酬制度の最新情報は厚労省通知を必ず参照すること。"
    )

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit 描画ヘルパー
# ---------------------------------------------------------------------------

def render_in_streamlit(streamlit_module) -> None:
    """Streamlit でマニュアルを描画 + DOCX ダウンロードボタンを提供.

    Args:
        streamlit_module: ``streamlit`` モジュール
    """
    st = streamlit_module
    st.markdown(DISEASE_MANUAL_MARKDOWN, unsafe_allow_html=True)
    st.markdown("---")
    try:
        docx_bytes = generate_docx()
        st.download_button(
            "📥 疾患別マニュアル DOCX をダウンロード（Word で開いて印刷・PDF 化可）",
            data=docx_bytes,
            file_name="看護必要度_疾患別マニュアル.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="nn_disease_manual_docx",
        )
    except Exception as e:
        st.warning(f"⚠️ DOCX 生成中にエラー: {e}（python-docx の依存関係を確認してください）")


# ---------------------------------------------------------------------------
# CLI: docs/admin/nursing_necessity_disease_manual.md を再生成
# ---------------------------------------------------------------------------

def _regenerate_md_file() -> Path:
    """git 管理用の md ファイルを docs/admin/ に書き出す."""
    out_path = Path(__file__).resolve().parent.parent / "docs" / "admin" / "nursing_necessity_disease_manual.md"
    out_path.write_text(DISEASE_MANUAL_MARKDOWN, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = _regenerate_md_file()
    print(f"✅ Regenerated: {p}")
    print(f"   Total characters: {len(DISEASE_MANUAL_MARKDOWN):,}")
    n_diseases = sum(len(group_diseases) for _, group_diseases in DISEASE_DATA)
    print(f"   Total diseases: {n_diseases}")
