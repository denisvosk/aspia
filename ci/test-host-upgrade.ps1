# Runs only on an isolated GitHub Windows runner. Never uses a production config.
param([Parameter(Mandatory=$true)][string]$NewMsi,
      [ValidateSet('x86','x64')][string]$Arch = 'x86')
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$expectedHash = if ($Arch -eq 'x64') { '8ba2a5dbb716edfb7bbd72483163111f9efd6e978ae0f81a0769842970331d5d' } else { '969b312fc7d6d178155faed901cb14c08cc5f55fb2746d6315fd2289829b247f' }
$ErrorActionPreference = 'Stop'
# PowerShell accepts mixed separators, but Windows Installer can reject them
# with error 1324/1619. Resolve the preview before installing the old Host.
if (!(Test-Path -LiteralPath $NewMsi -PathType Leaf)) { throw "Preview MSI does not exist: $NewMsi" }
$NewMsi = (Get-Item -LiteralPath $NewMsi).FullName.Replace('/', '\')
$work = Join-Path $env:RUNNER_TEMP 'aspia-upgrade-test'
New-Item -ItemType Directory -Force $work | Out-Null
$old = Join-Path $work "aspia-host-2.7.0-$packageArch.msi"
Invoke-WebRequest "https://github.com/dchapyshev/aspia/releases/download/v2.7.0/aspia-host-2.7.0-$packageArch.msi" -OutFile $old
if ((Get-FileHash $old -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) {
    throw 'Original 2.7.0 MSI checksum mismatch'
}
function Install-TestMsi([string]$path, [string]$name) {
    $path = (Get-Item -LiteralPath $path).FullName.Replace('/', '\')
    $log = Join-Path $work "$name.log"
    Write-Host "Installing $name from $path"
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$path`"", '/qn', '/norestart', '/l*v', "`"$log`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Get-Content $log -Tail 80
        throw "MSI $name failed or requires reboot: $($p.ExitCode)"
    }
    (Get-Service aspia-host-service).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
}
$previousDir = Join-Path $work 'preview17'
New-Item -ItemType Directory -Force $previousDir | Out-Null
$previousName = "aspia-host-2.7.1-$packageArch.msi"
gh release download 'v2.7.1-clipboard-preview.17' --repo $env:GITHUB_REPOSITORY --pattern $previousName --dir $previousDir --clobber
if ($LASTEXITCODE) { throw 'Could not download the previously installed preview.17 for upgrade testing' }
$previous = Join-Path $previousDir $previousName
$previousHash = if ($Arch -eq 'x64') { 'e82fec2d9c42215fc82ba151c7b0c350240d50ddeb0f0610f111717fce5583c1' } else { '2eef47c374214a50cedca243ee4fcdff2730283ff76b389b5f48c8d6580055f1' }
if ((Get-FileHash $previous -Algorithm SHA256).Hash.ToLower() -ne $previousHash) { throw 'Preview.17 MSI checksum mismatch' }
$installed = $old
try {
    Install-TestMsi $old 'install-original'
    Stop-Service aspia-host-service
    $configPath = Join-Path $env:ProgramData 'aspia/host.json'
    $config = @{}
    if (Test-Path $configPath) { $config = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable }
    $config['PreviewUpgradeTest'] = [Guid]::NewGuid().ToString()
    $config['RouterEnabled'] = $false
    $config['RouterAddress'] = '127.0.0.1'
    $config['UpdateServer'] = 'https://updates.invalid.test'
    $config['AutoUpdateEnabled'] = $false
    $config['LastUpdateCheck'] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    New-Item -ItemType Directory -Force (Split-Path $configPath) | Out-Null
    $config | ConvertTo-Json -Depth 30 | Set-Content $configPath -Encoding utf8
    Start-Service aspia-host-service
    $before = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    Install-TestMsi $NewMsi 'upgrade-preview'
    $installed = $NewMsi
    $after = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $before.Keys) {
        $expected = ConvertTo-Json -InputObject $before[$key] -Depth 30 -Compress
        $actual = ConvertTo-Json -InputObject $after[$key] -Depth 30 -Compress
        if ($expected -ne $actual) { throw "Host setting changed during upgrade: $key" }
    }
    $programFiles = if ($Arch -eq 'x64') { $env:ProgramFiles } else { ${env:ProgramFiles(x86)} }
    $exe = Join-Path $programFiles 'Aspia/Host/aspia_host_service.exe'
    if (!(Test-Path $exe)) { throw 'Upgraded Host service executable missing' }
    if ((Get-Item $exe).VersionInfo.ProductVersion -notlike '2.7.1.*') { throw 'Host service was not upgraded to 2.7.1' }
    "Host $Arch 2.7.0 -> 2.7.1: service running and test configuration preserved." | Write-Host
    function Assert-InstalledPayload {
        $builtDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'builds/ninja-multi-vcpkg-ci/Release'
        foreach ($name in 'aspia_host_service.exe','aspia_host.exe','aspia_desktop_agent.exe') {
            $actual = Join-Path (Split-Path $exe) $name
            $expected = Join-Path $builtDir $name
            if ((Get-FileHash $actual).Hash -ne (Get-FileHash $expected).Hash) {
                throw "Installed executable was not replaced by this build: $name"
            }
        }
    }
    Assert-InstalledPayload
    # Also exercise the user's exact situation: replace an existing 2.7.1 preview.
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Could not prepare same-version upgrade test: $($p.ExitCode)" }
    $installed = $previous
    Install-TestMsi $previous 'install-preview17'
    $before = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    Install-TestMsi $NewMsi 'upgrade-preview17-to-current'
    $installed = $NewMsi
    $after = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $before.Keys) {
        if ((ConvertTo-Json -InputObject $before[$key] -Depth 30 -Compress) -ne
            (ConvertTo-Json -InputObject $after[$key] -Depth 30 -Compress)) {
            throw "Host setting changed during same-version upgrade: $key"
        }
    }
    Assert-InstalledPayload
    "Host $Arch preview.17 -> current 2.7.1: service running, configuration preserved, installed binary hashes match this build." | Write-Host
} finally {
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -notin 0,1605,3010) { Write-Warning "Cleanup MSI exit code: $($p.ExitCode)" }
}
