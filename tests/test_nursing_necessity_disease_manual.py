"""看護必要度 疾患別マニュアルの制度分類・倫理表現テスト."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nursing_necessity_disease_manual import DISEASE_MANUAL_MARKDOWN  # noqa: E402


def test_cv_and_ptcd_c_item_classification_is_current_2026():
    """CVはC21、PTCDはC23として表示し、旧分類を混在させない."""
    md = DISEASE_MANUAL_MARKDOWN

    assert "C21 CV 挿入" in md
    assert "C21 CV 挿入実施日" in md
    assert "C23 PTCD" in md
    assert "C23 PTCD（経皮的胆管ドレナージ）</span>: **5 日カウント**" in md

    assert "C23 CV 挿入" not in md
    assert "C21③ PTCD" not in md
    assert "PTCD</span> 4 日カウント" not in md


def test_manual_uses_ethically_safe_action_framing():
    """点数目的に見える見出し・強い誘導語を避ける."""
    md = DISEASE_MANUAL_MARKDOWN

    assert "適応時に確認する項目" in md
    assert "評価・記録上の確認点" in md
    assert "制度コード照合メモ" in md
    assert "C項目候補: 尿管ステント / PCN（術式コード要照合）" in md
    assert "C項目候補: 緊急デブリードマン（術式コード要照合）" in md

    unsafe_terms = [
        "看護必要度貢献選択肢",
        "看護必要度に貢献する選択肢",
        "圧倒的な該当患者",
        "挿入閾値を下げる",
        "適応症例で内視鏡的切除を積極化",
        "C 項目両取り",
    ]
    for term in unsafe_terms:
        assert term not in md
