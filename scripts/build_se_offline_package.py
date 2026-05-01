"""院内 SE 向けオフライン配布 zip 作成スクリプト.

副院長指示 (2026-05-01):
- 院内 LAN は GitHub に直接アクセスできない前提
- 外部ネット PC でこのスクリプトを実行 → zip 1 個を Teams で SE に送付

zip の内訳:
    bed_control_simulator_offline_YYYY-MM-DD.zip
    ├─ scripts/                  ← Python アプリ本体
    ├─ data/                     ← データ（空スキーマのみ）
    ├─ settings/                 ← 設定 YAML（手動シードテンプレ）
    ├─ docs/admin/               ← ドキュメント抜粋
    │   ├─ SE_install_manual_2026-05-01.docx
    │   └─ pre_lan_deployment_checklist.md
    ├─ wheels/                   ← pip オフラインインストール用 .whl
    ├─ deploy/                   ← 起動 bat / ps1 / plist テンプレ
    ├─ tools/browser_probe.html
    ├─ requirements.txt
    ├─ requirements-edge90.txt
    └─ README_FIRST.txt

使い方:
    .venv/bin/python scripts/build_se_offline_package.py
    → docs/admin/bed_control_simulator_offline_YYYY-MM-DD.zip

オプション:
    --skip-wheels   pip download をスキップ（高速確認用）
    --no-clean      作業フォルダを残す（デバッグ用）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# 配布対象（リポジトリルートからの相対パス）
INCLUDE_DIRS = [
    "scripts",
    "settings",
    "tools",
    "deploy",
]

# 除外パターン（zip 内に入れない）
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pyc",
    ".pyo",
    ".pytest_cache",
    ".DS_Store",
    "scripts/hooks",  # 開発用フック
    "scripts/views/__pycache__",
]

# 配布する個別ファイル（リポジトリルートからの相対パス）
INCLUDE_FILES = [
    "requirements.txt",
    "requirements-edge90.txt",
]

# data/ から含めるもの（空スキーマのみ。実データは含めない）
DATA_INCLUDE_FILES = [
    "admission_details.csv",
    "doctor_master.csv",
]

# docs/admin/ から含めるもの
DOC_INCLUDE_FILES = [
    "SE_install_manual_2026-05-01.docx",
    "pre_lan_deployment_checklist.md",
]


README_FIRST_TEXT = """\
=================================================================
ベッドコントロールシミュレーター — 院内 SE 向け配布パッケージ
おもろまちメディカルセンター 副院長 久保田 透
=================================================================

【まずこちらをお読みください】

1. このパッケージには次が入っています:
   - SE_install_manual_2026-05-01.docx（メインマニュアル / DOCX）
   - アプリ本体（scripts/）
   - Python 依存パッケージ（wheels/, requirements.txt）
   - 起動スクリプト（deploy/）
   - ブラウザ互換チェッカー（tools/browser_probe.html）

2. 設置手順は SE_install_manual_2026-05-01.docx を Word で開いて
   ご確認ください。Chapter 3 から順に実施いただければ完了します。

3. 院内 LAN は GitHub に直接アクセスできない前提で構築されています。
   pip install もオフラインで完結するよう wheels/ を同梱しています。

4. ご不明点は副院長まで Teams でご連絡ください。

=================================================================
"""


def _is_excluded(path: Path) -> bool:
    """除外パターンに該当するか判定."""
    s = str(path)
    for pattern in EXCLUDE_PATTERNS:
        if pattern in s:
            return True
    return False


def _copy_dir(src: Path, dst: Path) -> int:
    """ディレクトリを再帰的にコピー（除外パターン適用）。コピー数を返す。"""
    count = 0
    for entry in src.rglob("*"):
        if entry.is_dir():
            continue
        if _is_excluded(entry):
            continue
        rel = entry.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        count += 1
    return count


def _make_empty_admission_details(target: Path) -> None:
    """空の admission_details.csv を作成（ヘッダーのみ）."""
    # data_purity_guard / bed_data_manager が期待するスキーマ
    headers = (
        "patient_id,event_type,date,ward,doctor,route,short3_type,"
        "operation,age_band,memo,patient_status,created_at,detail_id,"
        "data_version,operation_subtype\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(headers, encoding="utf-8")


PLATFORM_PRESETS = {
    # 院内サーバーが Windows 64bit + Python 3.11 の想定
    "win": {
        "platform": ["win_amd64"],
        "python_version": "3.11",
        "implementation": "cp",
        "abi": "cp311",
    },
    # macOS（副院長の開発端末で動作確認用、配布対象外でも有用）
    "mac-arm": {
        "platform": ["macosx_11_0_arm64"],
        "python_version": "3.11",
        "implementation": "cp",
        "abi": "cp311",
    },
    # Linux x86_64（万一の予備）
    "linux": {
        "platform": ["manylinux2014_x86_64", "manylinux_2_17_x86_64"],
        "python_version": "3.11",
        "implementation": "cp",
        "abi": "cp311",
    },
}


def _download_wheels(
    wheels_dir: Path,
    requirements_path: Path,
    platform_name: str = "win",
) -> None:
    """pip download で wheels をオフライン用にダウンロード（クロスプラットフォーム対応）.

    院内サーバーは通常 Windows 64bit + Python 3.11。`platform_name="win"` がデフォルト。
    macOS で実行している副院長の Mac mini からでも、Windows 用 wheels を取得できる。
    """
    if platform_name not in PLATFORM_PRESETS:
        raise ValueError(
            f"unknown platform: {platform_name}. choose from {list(PLATFORM_PRESETS)}"
        )
    preset = PLATFORM_PRESETS[platform_name]
    wheels_dir.mkdir(parents=True, exist_ok=True)
    print(f"📦 pip download for [{platform_name}] → {wheels_dir}")

    cmd = [
        sys.executable, "-m", "pip", "download",
        "-r", str(requirements_path),
        "-d", str(wheels_dir),
        "--no-cache-dir",
        "--only-binary=:all:",
        "--python-version", preset["python_version"],
        "--implementation", preset["implementation"],
        "--abi", preset["abi"],
    ]
    for plat in preset["platform"]:
        cmd.extend(["--platform", plat])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️ pip download failed:")
        print(result.stderr)
        raise RuntimeError("pip download failed")
    n_wheels = len(list(wheels_dir.glob("*")))
    print(f"   → {n_wheels} ファイルをダウンロード完了")


def _zip_directory(source_dir: Path, output_zip: Path, root_name: str) -> None:
    """ディレクトリを zip 化（zip 内のルートディレクトリ名を root_name に）."""
    print(f"🗜  Creating zip: {output_zip}")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in source_dir.rglob("*"):
            if entry.is_dir():
                continue
            rel = entry.relative_to(source_dir)
            arcname = Path(root_name) / rel
            zf.write(entry, arcname)
    size_mb = output_zip.stat().st_size / 1024 / 1024
    print(f"   → {size_mb:.1f} MB")


def build(
    skip_wheels: bool = False,
    no_clean: bool = False,
    platform_name: str = "win",
) -> Path:
    today = date.today().isoformat()
    pkg_name = f"bed_control_simulator_offline_{platform_name}_{today}"
    output_zip = REPO_ROOT / "docs" / "admin" / f"{pkg_name}.zip"

    # 作業ディレクトリ
    work_root = Path(tempfile.mkdtemp(prefix="se_pkg_"))
    work_dir = work_root / pkg_name
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"📁 Work directory: {work_dir}")

    try:
        # 1. ディレクトリコピー
        for d in INCLUDE_DIRS:
            src = REPO_ROOT / d
            if not src.exists():
                print(f"   ⚠️  {d}/ が見つかりません（スキップ）")
                continue
            n = _copy_dir(src, work_dir / d)
            print(f"   📂 {d}/ {n} files")

        # 2. 個別ファイルコピー
        for f in INCLUDE_FILES:
            src = REPO_ROOT / f
            if not src.exists():
                print(f"   ⚠️  {f} が見つかりません（スキップ）")
                continue
            shutil.copy2(src, work_dir / f)
            print(f"   📄 {f}")

        # 3. data/（空スキーマ + 既存マスタのみ）
        data_dir = work_dir / "data"
        data_dir.mkdir(exist_ok=True)
        # 空 admission_details.csv（既存があってもデモ込みなので空で上書き）
        _make_empty_admission_details(data_dir / "admission_details.csv")
        print("   📄 data/admission_details.csv（空スキーマ）")
        # doctor_master.csv は既存をコピー（実医師コード allowlist は配布対象）
        for f in DATA_INCLUDE_FILES:
            if f == "admission_details.csv":
                continue  # 上で生成済
            src = REPO_ROOT / "data" / f
            if src.exists():
                shutil.copy2(src, data_dir / f)
                print(f"   📄 data/{f}")
        # data/archive/ は空のまま作成
        (data_dir / "archive").mkdir(exist_ok=True)

        # 4. docs/admin/（必要なものだけ）
        docs_admin_dir = work_dir / "docs" / "admin"
        docs_admin_dir.mkdir(parents=True, exist_ok=True)
        for f in DOC_INCLUDE_FILES:
            src = REPO_ROOT / "docs" / "admin" / f
            if not src.exists():
                print(f"   ⚠️  docs/admin/{f} が見つかりません（要再生成）")
                continue
            shutil.copy2(src, docs_admin_dir / f)
            print(f"   📄 docs/admin/{f}")

        # 5. wheels/（pip オフラインインストール用）
        if skip_wheels:
            print("   ⏭  wheels/ ダウンロードをスキップ（--skip-wheels）")
        else:
            _download_wheels(
                work_dir / "wheels",
                REPO_ROOT / "requirements.txt",
                platform_name=platform_name,
            )

        # 6. README_FIRST.txt
        (work_dir / "README_FIRST.txt").write_text(README_FIRST_TEXT, encoding="utf-8")
        print("   📄 README_FIRST.txt")

        # 7. zip 化
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        _zip_directory(work_dir, output_zip, root_name=pkg_name)

    finally:
        if not no_clean:
            shutil.rmtree(work_root, ignore_errors=True)
            print(f"🧹 Cleaned: {work_root}")

    print(f"\n✅ パッケージ完成: {output_zip}")
    print(f"   → このファイルを Microsoft Teams で SE にお送りください。")
    return output_zip


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SE 向けオフライン配布 zip ビルダー")
    parser.add_argument("--skip-wheels", action="store_true",
                        help="pip download をスキップ（高速確認用）")
    parser.add_argument("--no-clean", action="store_true",
                        help="作業フォルダを残す（デバッグ用）")
    parser.add_argument("--platform", choices=list(PLATFORM_PRESETS.keys()),
                        default="win",
                        help="対象プラットフォーム（既定: win = Windows 64bit）")
    args = parser.parse_args()
    build(
        skip_wheels=args.skip_wheels,
        no_clean=args.no_clean,
        platform_name=args.platform,
    )
