# ChatGPT Pro 用: KPI「未取得」バグの事後分析 & 検出可能性の検証

以下のプロンプトをChatGPT Proに貼り付けて使用してください。

---

## プロンプト（ここから下をコピー）

```
あなたは病院業務支援アプリの品質監査者です。
今回、Claude Codeが実装したアプリに重大なバグがあり、人間が画面を目視するまで発見できませんでした。
あなた（ChatGPT Pro）にも事前にGitHubリポジトリの検証を依頼しましたが、このバグは検出されませんでした。

このバグがコードレビューだけで検出可能だったのか、率直に分析してください。

## リポジトリ
https://github.com/torukubota2023/bed-control-simulator

## バグの内容

### 症状
ダッシュボードのKPI優先表示セクション（救急搬送後患者割合・施設基準チェック・病床稼働率）が全て「未取得」と表示された。
しかし、同じ画面の上部（本日の病床状況）には稼働率88.8%等のデータが正常に表示されていた。
つまり、データは存在するのにKPIセクションだけがデータを取得できていなかった。

### 根本原因
`scripts/bed_control_simulator_app.py` の結論カード生成コード（2693行目付近）で `_daily_df` という変数を参照していたが、この変数はファイルの7838行目（データ管理タブ内）で初めて定義される。

Streamlitでは上から下へ順次実行されるため、2693行目の時点では `_daily_df` は未定義。
参照した瞬間に `NameError` が発生する。

```python
# 2693行目（結論カード生成 — ファイルの前半）
_ac_overall_df = _daily_df if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0 else _ac_daily_df
#                ↑ NameError! この変数は7838行目で初めて定義される

# 7838行目（データ管理タブ — ファイルの後半）
_daily_df = st.session_state.get("daily_data", pd.DataFrame())
```

### なぜ全KPIが死んだか
この `NameError` は外側の `try/except Exception: pass` で握り潰された。
外側のtryブロックはKPIデータ準備の全体（稼働率・施設基準・救急搬送比率・翌朝受入余力・LOS余力・C群）を包含していたため、1つのNameErrorで全KPIの計算がスキップされ、全て None のまま「未取得」と表示された。

```python
try:
    _ac_daily_df = ...        # ← ここまでは成功
    _ac_daily_df_full = ...   # ← ここまでは成功
    _ac_overall_df = _daily_df if ...  # ← NameError!（ここで全体が中断）
    # 以下すべてスキップ:
    _ac_occupancy = ...       # 稼働率
    _ac_emergency_summary = ...  # 救急搬送比率
    _ac_guardrail_status = ... # 施設基準
    # ...
except Exception:
    pass  # ← NameErrorを握り潰し、エラーメッセージも出さない
```

### 修正内容（コミット f6efa96）
```python
# 修正後: session_stateから直接取得するフォールバック
_ac_overall_src = st.session_state.get("daily_data") if '_daily_df' not in dir() else _daily_df
_ac_overall_df = _ac_overall_src if isinstance(_ac_overall_src, pd.DataFrame) and len(_ac_overall_src) > 0 else _ac_daily_df
```

加えて、`except Exception: pass` を `except Exception as _ac_data_err:` に変更し、エラー発生時にデバッグ情報を画面に表示するようにした。

## 質問

### 1. コードレビューで検出可能だったか？
このバグを、アプリを実行せずにコードだけを読んで発見することは可能でしたか？
- `_daily_df` の定義箇所（7838行）と参照箇所（2693行）の距離は約5,000行
- ファイル全体は約9,000行
- 変数名は `_daily_df` と `_ac_daily_df` が混在（似ているが別物）
- `try/except Exception: pass` パターンが複数箇所にある

### 2. 前回の検証依頼で見落とした理由
前回、以下の検証依頼をしました：
- 制度余力タブのLOSデータソース修正の確認
- 結論カードの他病棟協力表示の確認
- 既存機能への影響確認

この検証項目に「KPIが正常に表示されるか」は含まれていませんでした。
なぜなら、修正対象ではない部分（KPI表示）が壊れているとは想定していなかったからです。
実際には、修正対象ではなく **元々壊れていた**（_daily_dfが7838行で定義される構造は以前から同じ）。

### 3. AIコードレビューの限界と対策
9,000行のStreamlitアプリで、以下のパターンのバグを自動検出する方法はありますか？

**パターン: 未定義変数の参照が try/except で握り潰される**
- 静的解析ツール（pylint, mypy, ruff）で検出できるか？
- LLMベースのコードレビューで検出するにはどのようなプロンプト設計が必要か？
- テストで検出するにはどのような設計が必要か？

### 4. 提案
このような「サイレント障害」を防ぐために、以下のどれが最も効果的ですか？
優先順位をつけて推奨してください。

A. `except Exception: pass` の全面禁止（最低でもログ出力を義務化）
B. 静的解析ツールの導入（pylint/ruff の undefined-variable チェック）
C. 画面スクリーンショットベースの自動テスト（Playwright等）
D. KPI表示のunit test追加（モックデータでrender関数を呼び、None以外が返ることを確認）
E. ファイルの分割（9,000行→複数ファイル）で変数スコープを小さくする
F. LLMレビューのプロンプトに「try/except pass パターンの危険性チェック」を追加

## 出力フォーマット

### 検出可能性の判定
| 手法 | 検出できたか | 理由 |
|------|------------|------|

### 根本原因の分類
このバグは以下のどれに分類されますか？
- [ ] 実装ミス（コーディングエラー）
- [ ] 設計ミス（アーキテクチャの問題）
- [ ] テスト不足
- [ ] レビュープロセスの問題

### 推奨対策（優先順位付き）
| 優先度 | 対策 | 期待効果 | 導入コスト |
|--------|------|---------|-----------|

### 率直な見解
AIコードレビュー（ChatGPT/Claude）の現在の限界について、率直に述べてください。
特に「9,000行の単一ファイルで、5,000行離れた変数の未定義参照を、try/exceptで握り潰されている状態で検出する」ことの現実的な難易度について。
```
