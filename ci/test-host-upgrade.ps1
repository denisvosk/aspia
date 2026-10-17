# Runs only on an isolated GitHub Windows runner. Never uses a production config.
param([Parameter(Mandatory=$true)][string]$NewMsi,
      [ValidateSet('x86','x64')][string]$Arch = 'x86')
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$expectedHash = if ($Arch -eq 'x64') { '8ba2a5dbb716edfb7bbd72483163111f9efd6e978ae0f81a0769842970331d5d' } else { '969b312fc7d6d178155faed901cb14c08cc5f55fb2746d6315fd2289829b247f' }
$ErrorActionPreference = 'Stop'
$work = Join-Path $env:RUNNER_TEMP 'aspia-upgrade-test'
New-Item -ItemType Directory -Force $work | Out-Null
$old = Join-Path $work "aspia-host-2.7.0-$packageArch.msi"
Invoke-WebRequest "https://github.com/dchapyshev/aspia/releases/download/v2.7.0/aspia-host-2.7.0-$packageArch.msi" -OutFile $old
if ((Get-FileHash $old -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) {
    throw 'Original 2.7.0 MSI checksum mismatch'
}
function Install-TestMsi([string]$path, [string]$name) {
    $log = Join-Path $work "$name.log"
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$path`"", '/qn', '/norestart', '/l*v', "`"$log`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Get-Content $log -Tail 80
        throw "MSI $name failed or requires reboot: $($p.ExitCode)"
    }
    (Get-Service aspia-host-service).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
}
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
} finally {
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -notin 0,1605,3010) { Write-Warning "Cleanup MSI exit code: $($p.ExitCode)" }
}
