# ベッドコントロール開発 - Claude Code運用フロー

この文書は、ベッドコントロールシミュレーターを Claude Code で止まりにくく開発するための実務ガイドです。

## 目的
- 許可ダイアログで作業が止まる回数を減らす
- Claude Code に触らせる場所と、人が管理する場所を分ける
- 修正依頼を毎回同じ流れで出せるようにする
- Codex が補助修正した場合も、Claude Code が後から追えるようにする

## 0. Claude Code 中心運用と Codex 補助の見える化

ベッドコントロール開発の主担当は Claude Code とし、Codex は以下のような補助に使う。

- GitHub Actions / CI / E2E の赤原因調査
- PR の状態確認、失敗ログの読み取り、再現性の修正
- README / QA文書 / 運用フローの整合性更新
- Claude Code が次に作業しやすいように、変更理由と確認結果を文書へ残す

Codex が修正した場合は、必ず以下を残す。

1. PR またはブランチ名
2. 変更した主なファイル
3. なぜ変更したか
4. 実行した確認コマンド
5. Claude Code が次に見るべき残タスク

### Codex 補助履歴

| 日付 | PR/ブランチ | 内容 | 確認 |
|------|-------------|------|------|
| 2026-04-25 | PR #17 / `codex/fix-main-ci-actions` | GitHub Actions 復旧、E2E CI を正準テストに整理、Node依存を明示、READMEと本フローを更新 | ruff critical check / smoke test / Playwright CI E2E / GitHub Actions green |
| 2026-04-25 | `codex/nursing-necessity-strategy` | 2026看護必要度の割合指数（該当患者割合 + 救急患者応需係数）をアプリ内で病棟別試算。`nursing_necessity_strategy.py` とテストを追加し、医師別分析タブへ不足pt・必要該当日数・A/C項目パッケージ試算を表示 | pytest targeted / ruff critical check / smoke test |
| 2026-04-26 | `codex/6f-nursing-necessity-strategy` | 過去1年分析の看護必要度トレンドに、6F（内科・ペイン科）実データ版ストラテジーボードを追加。12ヶ月平均/直近3ヶ月の不足を患者日数に換算し、倫理・医学・行動・UIの4観点と職種別アクションを表示 | py_compile / nursing necessity targeted pytest |

## 1. Claude に触らせる場所
通常の実装・修正は、以下を優先して触らせる。

### 実装本体
- [scripts/bed_control_simulator_app.py](/Users/torukubota/ai-management/scripts/bed_control_simulator_app.py)
- [scripts/views](/Users/torukubota/ai-management/scripts/views)
- [scripts/guardrail_engine.py](/Users/torukubota/ai-management/scripts/guardrail_engine.py)
- [scripts/demand_wave.py](/Users/torukubota/ai-management/scripts/demand_wave.py)
- [scripts/c_group_control.py](/Users/torukubota/ai-management/scripts/c_group_control.py)
- [scripts/emergency_ratio.py](/Users/torukubota/ai-management/scripts/emergency_ratio.py)
- [scripts/scenario_manager.py](/Users/torukubota/ai-management/scripts/scenario_manager.py)

### テスト
- [tests](/Users/torukubota/ai-management/tests)
- とくに [tests/test_app_integration.py](/Users/torukubota/ai-management/tests/test_app_integration.py)
- Playwright の通常CI対象: [playwright/test_app.spec.ts](/Users/torukubota/ai-management/playwright/test_app.spec.ts)
- Playwright の手動監査対象: [playwright/test_audit.spec.ts](/Users/torukubota/ai-management/playwright/test_audit.spec.ts), [playwright/test_scenario_qa.spec.ts](/Users/torukubota/ai-management/playwright/test_scenario_qa.spec.ts)

### 普段更新する文書
- [docs/admin/bed_control_app_quality_assurance.md](/Users/torukubota/ai-management/docs/admin/bed_control_app_quality_assurance.md)
- [docs/admin/BedControl_Manual_v3.md](/Users/torukubota/ai-management/docs/admin/BedControl_Manual_v3.md)
- [docs/admin/demo_scenario_v3.5.md](/Users/torukubota/ai-management/docs/admin/demo_scenario_v3.5.md)
- [docs/admin/regression_test_checklist.md](/Users/torukubota/ai-management/docs/admin/regression_test_checklist.md)

## 2. なるべく触らせない場所
以下は Claude Code の通常開発中には頻繁に編集しない。

### 保護されやすい設定
- [app-quality-assurance.md](/Users/torukubota/ai-management/.claude/rules/app-quality-assurance.md)
- [.claude/commands](/Users/torukubota/ai-management/.claude/commands)
- [.claude/settings.local.json](/Users/torukubota/ai-management/.claude/settings.local.json)

### 原則
- 可変の教訓、チェック項目、運用メモは `.claude` に追記しない
- よく変わる内容は `docs/admin/*.md` に置く
- `.claude` は「短い固定ルール」と「コマンド定義」に絞る

## 3. 開発の基本フロー
1. Claude Desktop を起動する
2. ベッドコントロールの作業対象を明示する
3. 修正対象を `scripts/` と `tests/` に寄せる
4. 連動する説明文は `docs/admin/*.md` に反映させる
5. 最後に `/qa` を実行する

## 4. 依頼文テンプレート
そのまま貼って使える形にしておく。

### 機能追加
```text
ベッドコントロールシミュレーターに新機能を追加してください。
修正対象は scripts/ と tests/ を優先し、運用ルールの追記は docs/admin/bed_control_app_quality_assurance.md に書いてください。
.claude 配下は固定ルール以外できるだけ触らないでください。
変更後は test_app_integration と smoke_test を含めて確認してください。
```

### バグ修正
```text
ベッドコントロールシミュレーターの不具合を修正してください。
まず根本パターンを1文で言語化し、同一パターンを全体検索してください。
修正対象は scripts/ と tests/ を優先し、運用メモの更新は docs/admin/bed_control_app_quality_assurance.md に書いてください。
.claude 配下の更新は必要最小限にしてください。
```

### UI整理
```text
ベッドコントロールシミュレーターのUIを整理してください。
表示ロジックは可能なら scripts/views/ に寄せてください。
関連マニュアルの更新が必要なら docs/admin/BedControl_Manual_v3.md も更新してください。
.claude 配下には新しい運用メモを追加しないでください。
```

### QAだけ回す
```text
/qa scripts/bed_control_simulator_app.py
```

### Codex が入った後に Claude Code へ渡す
```text
Codex が GitHub Actions / CI / E2E まわりを補助修正しました。
まず docs/admin/bed_control_claude_code_workflow.md の「Codex 補助履歴」と README の現在の開発ステータスを確認してください。
そのうえで、通常の開発はこれまで通り scripts/ と tests/ を中心に進めてください。
```

## 5. 許可ダイアログが出た時の判断

### 出ても進めてよいもの
- `scripts/` 配下の編集
- `tests/` 配下の編集
- `docs/admin/*.md` の更新
- 通常の `python`, `pytest`, `rg`, `git`, `streamlit run` など

### 立ち止まるもの
- `.claude/rules/...` の編集
- `.claude/commands/...` の編集
- `.claude/settings.local.json` の変更

### 迷った時の原則
- 普段の開発中に `.claude/...` の編集許可が出たら、まず「本当に固定ルール変更か」を確認する
- 固定ルール変更でなければ、`docs/admin/bed_control_app_quality_assurance.md` 側に逃がす

## 6. 止まりにくい運用のコツ
- 機能要求は「どのディレクトリを優先するか」まで最初に書く
- 教訓やチェックリストは `.claude` に育てず、`docs/admin` に蓄積する
- 大きな修正は「実装」「テスト」「文書」の3点セットで依頼する
- `.claude` を触る仕事は、設定整理のターンとして分ける

## 7. 現在のおすすめ
- ベッドコントロールの実装は `scripts/` と `tests/` 中心で進める
- QAルールの育成は [docs/admin/bed_control_app_quality_assurance.md](/Users/torukubota/ai-management/docs/admin/bed_control_app_quality_assurance.md) に集約する
- `.claude/rules/app-quality-assurance.md` は短い固定ルールのまま維持する
