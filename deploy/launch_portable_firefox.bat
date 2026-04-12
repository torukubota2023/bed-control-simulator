@echo off
chcp 65001 >/dev/null
REM ポータブルFirefoxでベッドコントロールシミュレーターを開く
REM ※ 以下の設定を実際の環境に合わせて変更してください

SET SERVER_URL=http://192.168.1.100:8501
SET FIREFOX_PATH=\\server\shared\PortableApps\FirefoxPortable\FirefoxPortable.exe

REM ローカルコピーも探す
IF NOT EXIST "%FIREFOX_PATH%" SET FIREFOX_PATH=C:\PortableApps\FirefoxPortable\FirefoxPortable.exe
IF NOT EXIST "%FIREFOX_PATH%" SET FIREFOX_PATH=%USERPROFILE%\Desktop\FirefoxPortable\FirefoxPortable.exe

IF NOT EXIST "%FIREFOX_PATH%" (
    echo.
    echo [警告] ポータブルFirefoxが見つかりません
    echo 以下の場所を確認しました:
    echo   - \\server\shared\PortableApps\FirefoxPortable\FirefoxPortable.exe
    echo   - C:\PortableApps\FirefoxPortable\FirefoxPortable.exe
    echo   - %USERPROFILE%\Desktop\FirefoxPortable\FirefoxPortable.exe
    echo.
    echo 通常のブラウザで開きます...
    start "" "%SERVER_URL%"
    timeout /t 5
    exit /b
)

echo ポータブルFirefoxでベッドコントロールシミュレーターを開いています...
start "" "%FIREFOX_PATH%" "%SERVER_URL%"
