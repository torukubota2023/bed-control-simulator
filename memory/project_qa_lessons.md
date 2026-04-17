# プロジェクト QA 教訓（バグパターン集）

このファイルは Claude Code の `/qa` 実行時に検出された**新しいバグパターン**を蓄積する。同一パターンが再発したらこのファイルを参照して即座に対応する。

---

## 2026-04-17: 環境依存の欠損パッケージが E2E を全滅させる

### 現象
Playwright E2E テストの data-testid 存在確認（`occupancy` / `alos` / `phase` / `vacancy` / `action-card` / `guardrail-summary`）が**全滅**し、タイムアウトで失敗する。稼働率や救急搬送の値はサイドバーに見えているのに、ダッシュボード本体の testid だけが DOM から完全に消失する。

### 根本原因
`bed_control_simulator_app.py` の `with _summary_expander:` ブロック内で `import plotly.graph_objects as go`（行 2570）が Runtime に実行される。`.venv/bin/streamlit` 実行環境に `plotly` が未インストールだと、この import で `ModuleNotFoundError` が発生し、**expander 配下のコードがすべて停止**する。結果としてその下流にある `render_action_card` / `render_kpi_priority_strip` / `render_morning_capacity_card` などの描画が実行されず、data-testid も DOM に現れない。

エラー画面にはスタックトレースが小さく出るが、E2E テストは別セクションを巡回するので気付きにくい。

### 検出方法
1. ダッシュボード expander HTML の長さが異常に短い（正常時 40,000 字 → 異常時 1,800 字）
2. `st.error` のアラート内に `ModuleNotFoundError: No module named 'plotly'` が出ている
3. ページテキストに「今日の一手」「本日のサマリー」の中身が存在しない

### 対策
- `.venv` 環境の必須パッケージに `plotly`・`pytest` を追加
- `docs/admin/bed_control_e2e_manual.md` 第3章「Python 仮想環境の用意」セクションで明示
- 同マニュアル Q2（data-testid が見つからない）に最頻原因として記載

### 横展開
似たパターンの潜在リスク: expander / tab / with ブロック内での late import（Matplotlib, openpyxl, reportlab 等）が同様の挙動を起こす。将来的には top-level import + try/except で事前に握りつぶすリファクタが安全。

---

## 2026-04-17: Streamlit ラジオは `getByRole('radio').click()` では押せない

### 現象
Playwright が `page.getByRole('radio', { name: '🎯 意思決定支援' })` で要素を見つけるが、`.click()` で `element is not visible` タイムアウト（180 秒）になる。

### 根本原因
Streamlit のラジオボタンは `<input type="radio" tabindex="-1" class="...">` で**視覚的には不可視**にされ、実際のクリック対象は親の `<label>` 要素。Playwright の `getByRole('radio')` は `<input>` を見つけるが、その input 自体は非表示なのでクリックできない。

### 対策
```typescript
// ❌ NG
const radio = page.getByRole('radio', { name: sectionName });
await radio.click();

// ✅ OK — 親 label をクリック
const sidebar = page.locator('[data-testid="stSidebar"]');
const label = sidebar.locator(`label:has-text("${sectionName}")`).first();
await label.click();
```

Streamlit のタブ切替も同様のパターン（`stTab` data-testid を持つコンテナをクリック）。

### 横展開
`utils/streamlit_helpers.ts` の `selectSidebarRadio()` は既にこのパターンで実装済み。他のテストで `getByRole` を直接使っている箇所があれば同様に修正する。
