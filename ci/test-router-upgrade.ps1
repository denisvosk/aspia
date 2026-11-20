# This fixture runs only on a fresh isolated Windows CI runner. It never reads a
# production database and refuses to overwrite pre-existing Router state.
param([Parameter(Mandatory=$true)][string]$NewMsi,
      [ValidateSet('x86','x64')][string]$Arch = 'x86',
      [Parameter(Mandatory=$true)][string]$ExpectedVersion)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'The Router upgrade fixture may run only in isolated GitHub Windows CI.'
}
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$expectedHash = if ($Arch -eq 'x64') { '4f0f9f43b6e6190bf3ce192049e197d853b0bead420b3322d622bee3fadb8ad7' } else { 'a7f57160d27e46c355849c79ed61ca85788373d362497eb1e8f7a3b15755f6ef' }
$NewMsi = (Get-Item -LiteralPath $NewMsi).FullName.Replace('/', '\')
$work = Join-Path $env:RUNNER_TEMP 'aspia-router-upgrade-test'
New-Item -ItemType Directory -Force $work | Out-Null
$dataDir = Join-Path $env:ProgramData 'aspia'
$configPath = Join-Path $dataDir 'router.json'
$databasePath = Join-Path $dataDir 'router.db3'
$publicKeyPath = Join-Path $dataDir 'router.pub'
foreach ($path in $configPath, $databasePath, $publicKeyPath) {
    if (Test-Path -LiteralPath $path) { throw 'Router fixture requires a runner without existing Router state.' }
}
if (Get-Service 'aspia-router' -ErrorAction SilentlyContinue) { throw 'Router is already installed on this runner.' }
$old = Join-Path $work "aspia-router-2.7.0-$packageArch.msi"
Invoke-WebRequest "https://github.com/dchapyshev/aspia/releases/download/v2.7.0/aspia-router-2.7.0-$packageArch.msi" -OutFile $old
if ((Get-FileHash $old -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) { throw 'Original Router 2.7.0 MSI checksum mismatch' }
$programFiles = if ($Arch -eq 'x64') { $env:ProgramFiles } else { ${env:ProgramFiles(x86)} }
$exe = Join-Path $programFiles 'Aspia/Router/aspia_router.exe'
$snapshot = Join-Path $work 'data-before.json'
function Install-TestRouter([string]$path, [string]$name) {
    $path = (Get-Item -LiteralPath $path).FullName.Replace('/', '\')
    $log = Join-Path $work "$name.log"
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$path`"", '/qn', '/norestart', '/l*v', "`"$log`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Get-Content $log -Tail 80
        throw "Router MSI $name failed or requires reboot: $($p.ExitCode)"
    }
}
function Start-TestRouter {
    Start-Service 'aspia-router'
    (Get-Service 'aspia-router').WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    # Running alone is insufficient: the listener proves that startup opened the
    # existing DB and accepted its keys. It listens only on loopback in this test.
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync('127.0.0.1', 18060)
            if ($task.Wait([TimeSpan]::FromSeconds(2)) -and $client.Connected) { return }
        } catch { } finally { $client.Dispose() }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Router service did not expose the isolated loopback listener.'
}
$installed = $old
try {
    Install-TestRouter $old 'install-original-router'
    # The old CLI prints initial credentials; suppress them instead of emitting
    # generated secrets into public Actions logs.
    & $exe --create-config *> $null
    foreach ($path in $configPath, $databasePath, $publicKeyPath) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Original Router configuration creation failed.' }
    }
    $config = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    $config['ListenInterface'] = '127.0.0.1'
    $config['Port'] = 18060
    $config['PreviewUpgradeTest'] = [Guid]::NewGuid().ToString()
    foreach ($key in 'ClientWhiteList', 'HostWhiteList', 'AdminWhiteList', 'RelayWhiteList') { $config[$key] = '127.0.0.1' }
    $config | ConvertTo-Json -Depth 30 | Set-Content $configPath -Encoding utf8
    python (Join-Path $PSScriptRoot 'router-upgrade-data.py') seed $databasePath $snapshot
    if ($LASTEXITCODE) { throw 'Failed to seed Router upgrade fixture.' }
    Start-TestRouter
    Stop-Service 'aspia-router'
    $before = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    $publicKeyHash = (Get-FileHash $publicKeyPath -Algorithm SHA256).Hash
    $installed = $NewMsi
    Install-TestRouter $NewMsi 'upgrade-router'
    Start-TestRouter
    Stop-Service 'aspia-router'
    $after = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $before.Keys) {
        if ((ConvertTo-Json -InputObject $before[$key] -Depth 30 -Compress) -ne
            (ConvertTo-Json -InputObject $after[$key] -Depth 30 -Compress)) {
            throw "Router setting changed during upgrade: $key"
        }
    }
    if ((Get-FileHash $publicKeyPath -Algorithm SHA256).Hash -ne $publicKeyHash) { throw 'Router public key changed during upgrade.' }
    python (Join-Path $PSScriptRoot 'router-upgrade-data.py') verify $databasePath $snapshot
    if ($LASTEXITCODE) { throw 'Router identity/database preservation check failed.' }
    if ((Get-Item $exe).VersionInfo.ProductVersion -notlike "$ExpectedVersion.*") { throw "Router was not upgraded to $ExpectedVersion" }
    $built = Join-Path (Split-Path $PSScriptRoot -Parent) 'builds/ninja-multi-vcpkg-ci/Release/aspia_router.exe'
    if ((Get-FileHash $exe).Hash -ne (Get-FileHash $built).Hash) { throw 'Installed Router executable does not match this build.' }
    Start-TestRouter
    "Router $Arch 2.7.0 -> ${ExpectedVersion}: service/listener checked; configuration, keys, users and Host IDs preserved." | Write-Host
} finally {
    $service = Get-Service 'aspia-router' -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne 'Stopped') { Stop-Service 'aspia-router' }
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -notin 0,1605,3010) { Write-Warning "Router cleanup MSI exit code: $($p.ExitCode)" }
}
