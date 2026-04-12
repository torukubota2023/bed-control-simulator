# ベッドコントロールシミュレーター アクセススクリプト
# 使い方: 右クリック → 「PowerShellで実行」
# ※ サーバーURLとFirefoxパスを環境に合わせて変更してください

$ServerUrl = "http://192.168.1.100:8501"
$FirefoxPaths = @(
    "\\server\shared\PortableApps\FirefoxPortable\FirefoxPortable.exe",
    "C:\PortableApps\FirefoxPortable\FirefoxPortable.exe",
    "$env:USERPROFILE\Desktop\FirefoxPortable\FirefoxPortable.exe"
)

$Found = $false
foreach ($Path in $FirefoxPaths) {
    if (Test-Path $Path) {
        Write-Host "ポータブルFirefoxでベッドコントロールシミュレーターを開いています..." -ForegroundColor Green
        Start-Process $Path $ServerUrl
        $Found = $true
        break
    }
}

if (-not $Found) {
    Write-Host "[警告] ポータブルFirefoxが見つかりません。通常のブラウザで開きます。" -ForegroundColor Yellow
    Start-Process $ServerUrl
}
