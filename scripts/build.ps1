param(
    [string]$DotnetExe = $env:WVG_DOTNET,
    [string]$NsisExe,
    [string]$OutputDirectory = 'artifacts',
    [switch]$Portable,
    [switch]$SkipEngine
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not $DotnetExe) { $DotnetExe = (Get-Command dotnet -ErrorAction Stop).Source }
if (-not $NsisExe) { $NsisExe = Join-Path $projectRoot '.tools\nsis\Bin\makensis.exe' }
Push-Location $projectRoot
try {
    $out = [IO.Path]::GetFullPath($OutputDirectory, $projectRoot)
    $payload = Join-Path $out 'app'
    & (Join-Path $PSScriptRoot 'make-icon.ps1')
    & $DotnetExe publish 'src\Guard.App\Guard.App.csproj' -c Release -o $payload -p:PublishSingleFile=false -p:RestoreLockedMode=true
    if ($LASTEXITCODE -ne 0) { throw 'WPF publish failed.' }
    if (-not $SkipEngine) {
        & $pythonExe -m PyInstaller --noconfirm --distpath 'artifacts\engine' --workpath 'artifacts\pyinstaller' 'engine\worker.spec'
        if ($LASTEXITCODE -ne 0) { throw 'Worker build failed.' }
    }
    $engineSource = Join-Path $projectRoot 'artifacts\engine\WeixinVolumeGuard.Engine'
    if (-not (Test-Path -LiteralPath (Join-Path $engineSource 'WeixinVolumeGuard.Engine.exe'))) { throw 'Missing worker.' }
    New-Item -ItemType Directory -Path (Join-Path $payload 'Engine') -Force | Out-Null
    Copy-Item -Path (Join-Path $engineSource '*') -Destination (Join-Path $payload 'Engine') -Recurse -Force
    & $pythonExe 'scripts\collect_licenses.py' $payload
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
    Copy-Item -LiteralPath (Join-Path $projectRoot '.tools\nsis\COPYING') -Destination (Join-Path $payload 'Licenses\NSIS-COPYING.txt')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $payload 'README.zh-CN.txt')
    New-Item -ItemType Directory -Path (Join-Path $payload 'docs') -Force | Out-Null
    Copy-Item -Path (Join-Path $projectRoot 'docs\*.md') -Destination (Join-Path $payload 'docs') -Force
    $dotnetRoot = Split-Path -Parent $DotnetExe
    foreach ($licenseName in @('LICENSE.txt','ThirdPartyNotices.txt')) {
        $licenseFile = Join-Path $dotnetRoot $licenseName
        if (Test-Path -LiteralPath $licenseFile) { Copy-Item -LiteralPath $licenseFile -Destination (Join-Path $payload ('Licenses\dotnet-' + $licenseName)) -Force }
    }
    $files = Get-ChildItem -LiteralPath $payload -File -Recurse | Where-Object Name -ne 'uninstall-files.nsh'
    $deleteLines = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $files) {
        $relative = [System.IO.Path]::GetRelativePath($payload, $file.FullName)
        $escaped = $relative.Replace('$', '$$').Replace('"', '$\"')
        $deleteLines.Add('Delete "$INSTDIR\' + $escaped + '"')
    }
    $deleteLines.Add('Delete "$INSTDIR\uninstall-files.nsh"')
    $directories = Get-ChildItem -LiteralPath $payload -Directory -Recurse | Sort-Object { $_.FullName.Length } -Descending
    foreach ($directory in $directories) {
        $relative = [System.IO.Path]::GetRelativePath($payload, $directory.FullName)
        $deleteLines.Add('RMDir "$INSTDIR\' + $relative.Replace('$', '$$') + '"')
    }
    $deleteLines | Set-Content -LiteralPath (Join-Path $payload 'uninstall-files.nsh') -Encoding utf8BOM
    $output = Join-Path $out 'WeixinVolumeGuard-Setup-0.1.0-x64.exe'
    & $NsisExe /INPUTCHARSET UTF8 "/DPAYLOAD=$payload" "/DOUTPUT=$output" 'installer\WeixinVolumeGuard.nsi'
    if ($LASTEXITCODE -ne 0) { throw 'Installer compile failed.' }
    if ($Portable) {
        $portableOutput = Join-Path $out 'WeixinVolumeGuard-Portable-0.1.0-x64.exe'
        & $NsisExe /INPUTCHARSET UTF8 "/DPAYLOAD=$payload" "/DOUTPUT=$portableOutput" 'installer\WeixinVolumeGuard-Portable.nsi'
        if ($LASTEXITCODE -ne 0) { throw 'Portable package compile failed.' }
        Get-Item -LiteralPath $portableOutput | Select-Object FullName,Length
    }
    $manifest = Get-ChildItem -LiteralPath $payload -File -Recurse | ForEach-Object {
        [ordered]@{path=[System.IO.Path]::GetRelativePath($payload,$_.FullName);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash;bytes=$_.Length}
    }
    [ordered]@{version='0.1.0';sdk=(& $DotnetExe --version);nsis=(& $NsisExe /VERSION);installer=$output;installerSha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash;files=@($manifest)} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'build-manifest.json') -Encoding utf8
    & $pythonExe -m pip freeze | Set-Content -LiteralPath (Join-Path $out 'python-environment.txt') -Encoding utf8
    Get-Item -LiteralPath $output | Select-Object FullName,Length
}
finally { Pop-Location }
