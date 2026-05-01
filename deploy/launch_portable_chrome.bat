@echo off
chcp 65001 >nul
REM ベッドコントロールシミュレーター — Chrome Portable で開く
REM
REM 使い方:
REM   1. 下の SERVER_URL をサーバー PC の実際の IP に書き換える
REM   2. 下の CHROME_PATH を Chrome Portable の実体パスに書き換える
REM   3. このファイルをダブルクリック（または右クリック → 「ショートカットの作成」してデスクトップに配置）
REM
REM ※ Edge バージョン 90（電子カルテ用）には一切干渉しません

REM ====================================================
REM 設定（環境に合わせて編集してください）
REM ====================================================
SET SERVER_URL=http://192.168.1.100:8501

REM 共有フォルダ優先 → ローカル → デスクトップの順で探索
SET CHROME_PATH=\\server\shared\PortableApps\GoogleChromePortable\GoogleChromePortable.exe
IF NOT EXIST "%CHROME_PATH%" SET CHROME_PATH=C:\PortableApps\GoogleChromePortable\GoogleChromePortable.exe
IF NOT EXIST "%CHROME_PATH%" SET CHROME_PATH=%USERPROFILE%\Desktop\GoogleChromePortable\GoogleChromePortable.exe

REM ====================================================
REM 実行
REM ====================================================
IF NOT EXIST "%CHROME_PATH%" (
    echo.
    echo [警告] Chrome Portable が見つかりません
    echo 以下の場所を確認しました:
    echo   - \\server\shared\PortableApps\GoogleChromePortable\GoogleChromePortable.exe
    echo   - C:\PortableApps\GoogleChromePortable\GoogleChromePortable.exe
    echo   - %USERPROFILE%\Desktop\GoogleChromePortable\GoogleChromePortable.exe
    echo.
    echo 通常のブラウザで開きます（電子カルテ用 Edge とは別タブで）...
    start "" "%SERVER_URL%"
    timeout /t 5
    exit /b
)

echo Chrome Portable でベッドコントロールシミュレーターを開いています...
start "" "%CHROME_PATH%" --new-window "%SERVER_URL%"
