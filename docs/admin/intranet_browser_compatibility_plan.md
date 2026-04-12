# ブラウザ互換性対応方針 — ベッドコントロールシミュレーター

## 1. 問題の本質

ベッドコントロールシミュレーターは Python（Streamlit）で構築されているが、**互換性の問題は Python 側ではなく、ブラウザ側の JavaScript 互換性にある**。

Streamlit は以下の構成で動作する:

```
サーバー側（Python）          クライアント側（ブラウザ）
┌─────────────────┐          ┌─────────────────────┐
│ Python 3.11     │  HTTP    │ React アプリ         │
│ Streamlit       │ ──────→  │ JavaScript (ES2021+) │
│ pandas/plotly   │  WebSocket│ CSS Grid/Flexbox     │
│ matplotlib      │ ←──────  │ WebSocket Client     │
└─────────────────┘          └─────────────────────┘
```

**Python コードは問題なく動作する。問題は Streamlit が生成するフロントエンド JavaScript がブラウザで動作するかどうかである。**

## 2. Chromium 90 で使えない JavaScript API

院内標準の Edge 90（Chromium 90、2021年4月リリース）では、以下の JavaScript API が利用できない:

| API | 導入バージョン | 用途 |
|-----|---------------|------|
| `Array.at()` | Chromium 92 | 配列の要素アクセス |
| `Object.hasOwn()` | Chromium 93 | プロパティ存在確認 |
| `structuredClone()` | Chromium 98 | オブジェクトの深いコピー |
| `Array.findLast()` | Chromium 97 | 配列の後方検索 |
| `crypto.randomUUID()` | Chromium 92 | UUID生成 |
| `AbortSignal.timeout()` | Chromium 103 | タイムアウト制御 |
| CSS `@layer` | Chromium 99 | CSSカスケードレイヤー |
| CSS `color-mix()` | Chromium 111 | CSS色の合成 |

Streamlit のフロントエンドコード（React + Webpack ビルド出力）がこれらの API を使用している場合、**白画面やエラーが発生する**。

## 3. アプリ側で対処可能な問題

以下はアプリコード（`bed_control_simulator_app.py` 等）で使用している Streamlit 機能と、その互換性の評価:

### unsafe_allow_html（24箇所）
- `st.markdown(..., unsafe_allow_html=True)` で HTML/CSS を直接出力
- 使用している HTML/CSS は基本的なもの（`<div>`, `<span>`, `background-color`, `border` 等）
- **Chromium 90 で問題なし** — 基本 HTML/CSS は十分にサポートされている

### st.data_editor（3箇所）
- Streamlit 1.23+ で導入されたインタラクティブなデータ編集ウィジェット
- 古い Streamlit では `st.experimental_data_editor` または `st.dataframe` にフォールバック可能
- **フォールバック検討可** — ただし編集機能が失われる

### plotly_chart（4箇所）
- Plotly.js によるインタラクティブグラフ
- Plotly.js 自体は比較的広いブラウザ互換性を持つ
- **比較的互換性が高い** — ただし最新機能の使用状況による

### st.pyplot（33箇所）
- matplotlib によるグラフ描画
- **サーバーサイドで画像として描画**され、ブラウザには画像（PNG）として送信される
- **Chromium 90 で問題なし** — ブラウザ側は画像を表示するだけ

## 4. アプリ側で対処困難な問題

以下は開発者がアプリコードで対処することが**極めて困難**な問題:

### Streamlit フロントエンド本体の JavaScript
- Streamlit は React ベースの SPA（Single Page Application）として動作する
- フロントエンドのソースコードは Webpack でバンドルされ、minify されている
- このバンドルされた JavaScript が Chromium 90 で動作するかは、**Streamlit のビルド設定（Babel のターゲット設定等）に依存する**
- アプリ開発者が制御できる領域ではない

### st.tabs / st.columns 等の基本レイアウト部品
- タブ切替、カラムレイアウト等の基本UI部品は Streamlit フロントエンドの一部
- これらが動作しない場合、アプリの全体構造が崩壊する
- 代替手段（`st.selectbox` でのタブ代替等）は可能だが、UX が大幅に劣化する

## 5. 結論

**問題の所在はアプリコードではなく、Streamlit フレームワークとブラウザの互換性にある。**

```
対処可能な範囲:
  ✅ unsafe_allow_html → 基本HTML/CSSのみ、問題なし
  ✅ st.pyplot → サーバーサイド描画、問題なし
  ⚠️ st.data_editor → フォールバック可能だがUX劣化
  ⚠️ plotly_chart → 比較的互換性高いが要検証

対処困難な範囲:
  ❌ Streamlit フロントエンド本体のJS
  ❌ st.tabs / st.columns 等の基本レイアウト
  ❌ WebSocket 通信のポリフィル
```

**したがって、Edge 90 でのアプリコード修正による対応は現実的ではなく、ポータブルブラウザ（Firefox Portable）の導入が最も確実で低コストな解決策である。**

詳細は [院内LAN展開計画](intranet_deployment_plan.md) を参照。
