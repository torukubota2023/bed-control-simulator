@echo off
chcp 65001 >/dev/null
REM ベッドコントロールシミュレーター サーバー起動スクリプト
REM 使い方: サーバーPCでこのバッチファイルをダブルクリック
echo.
echo ======================================
echo  ベッドコントロールシミュレーター
echo  サーバー起動中...
echo ======================================
echo.
cd /d "%~dp0.."
IF NOT EXIST ".venv\Scripts\activate.bat" (
    echo [エラー] Python仮想環境が見つかりません。
    echo セットアップ手順を確認してください。
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
echo サーバーを起動しています...
echo ブラウザから http://[このPCのIPアドレス]:8501 でアクセスできます
echo 終了するにはこのウィンドウを閉じてください
echo.
streamlit run scripts/bed_control_simulator_app.py --server.address 0.0.0.0 --server.port 8501
pause
