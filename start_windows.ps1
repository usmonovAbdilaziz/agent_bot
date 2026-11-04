# Windows PowerShell 5.1; use only ASCII in this file for older Windows decoders.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

function Find-Python {
    $probe = "import sys,struct; assert (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8; print(sys.executable)"
    $candidates = @(
        (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    )
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\Microsoft\WindowsApps\*') {
        $candidates += $command.Source
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            try {
                $result = & $candidate -I -c $probe 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) { return [string]($result | Select-Object -Last 1) }
            } catch { }
        }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.13','-3.12','-3.11')) {
            try {
                $result = & $launcher.Source $version -I -c $probe 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) { return [string]($result | Select-Object -Last 1) }
            } catch { }
        }
    }
    return $null
}

$mutex = $null
$locked = $false
try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw '64-bit Windows 10 yoki 11 kerak.'
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($PSScriptRoot.ToLowerInvariant()))).Replace('-','')
    } finally { $sha.Dispose() }
    $mutex = New-Object Threading.Mutex($false, ('Local\Qadam-' + $digest))
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Bot shu papkadan allaqachon ochilgan. Avval osha oynada Ctrl+C bosing.' }

    $python = Find-Python
    if (-not $python) {
        Write-Host 'Python topilmadi. Python.org dan Python 3.13.17 ornatilmoqda...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $tempDir = Join-Path ([IO.Path]::GetTempPath()) ('qadam-python-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tempDir | Out-Null
        $installer = Join-Path $tempDir 'python-3.13.17-amd64.exe'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.exe' -OutFile $installer
            # Published SHA256: https://www.python.org/downloads/release/python-31317/
            $expected = '5da012101ba2e17113a9a1cd901e9ce1441086f2b7ecb5de06ec94163899a190'
            if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expected) {
                throw 'Python yuklamasi tekshiruvdan otmadi. start.bat ni qayta oching.'
            }
            $install = Start-Process -FilePath $installer -ArgumentList @('/passive','InstallAllUsers=0','Include_launcher=0','Include_test=0','Include_pip=1','PrependPath=0','Shortcuts=0') -Wait -PassThru
            if ($install.ExitCode -notin @(0,3010)) { throw ('Python ornatilmadi. Kod: ' + $install.ExitCode) }
        } finally {
            Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        $python = Find-Python
        if (-not $python) { throw 'Python topilmadi. Windowsni qayta ochib start.bat ni yana bosing.' }
    }
    Write-Host 'Qadam: kutubxonalar, Tailscale Funnel, Mini App va bot tayyorlanmoqda.'
    Write-Host 'Birinchi ishga tushishda internet va tokenlar kerak. Toxtatish: Ctrl+C.'
    & $python -u (Join-Path $PSScriptRoot 'run.py')
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host ('Xatolik: ' + $_.Exception.Message) -ForegroundColor Red
    $exitCode = 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
exit $exitCode
