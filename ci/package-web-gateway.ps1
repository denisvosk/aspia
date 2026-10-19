$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nodeVersion = '22.23.3'
$nodeName = "node-v$nodeVersion-win-x64"
$out = Join-Path $root 'gateway-package'
$package = Join-Path $out 'AspiaWebGateway'
New-Item -ItemType Directory -Force $package | Out-Null
function Run-Native([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe failed: $LASTEXITCODE" }
}
foreach ($file in @('web-gateway/Install-Gateway.ps1','ci/package-web-gateway.ps1')) {
    $parseTokens = $null; $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $root $file), [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
}
$nodeZip = Join-Path $out "$nodeName.zip"
$sumsFile = Join-Path $out 'NODE_SHASUMS256.txt'
Invoke-WebRequest "https://nodejs.org/dist/v$nodeVersion/SHASUMS256.txt" -OutFile $sumsFile
Invoke-WebRequest "https://nodejs.org/dist/v$nodeVersion/$nodeName.zip" -OutFile $nodeZip
$sumLine = @(Get-Content $sumsFile | Where-Object { $_ -match ('\s+' + [regex]::Escape("$nodeName.zip") + '$') })
if ($sumLine.Count -ne 1) { throw 'Node checksum missing or ambiguous' }
$expected = ($sumLine[0] -split '\s+')[0]
if ((Get-FileHash $nodeZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Node checksum mismatch' }
Expand-Archive $nodeZip -DestinationPath $out -Force
Copy-Item (Join-Path $out "$nodeName/node.exe") $package
Copy-Item (Join-Path $out "$nodeName/LICENSE") (Join-Path $package 'NODE_LICENSE.txt')
Copy-Item $sumsFile $package
$node = Join-Path $package 'node.exe'
Run-Native $node @('--test', (Join-Path $root 'web-gateway/test/gateway.test.mjs'))
Run-Native $node @('--check', (Join-Path $root 'web-gateway/public/app.js'))
$bridge = Join-Path $root 'builds/ninja-multi-vcpkg-ci/Release/aspia_web_bridge.exe'
if (!(Test-Path $bridge)) { throw 'Native bridge not built' }
Run-Native $bridge @('--self-test')
Run-Native $node @((Join-Path $root 'web-gateway/test/native-smoke.mjs'), $bridge)
Copy-Item $bridge $package
foreach ($name in @('server.mjs','auth.mjs','users.mjs','config.example.json','Install-Gateway.ps1','Caddy.fragment','README.md')) {
    Copy-Item (Join-Path $root "web-gateway/$name") $package
}
Copy-Item (Join-Path $root 'web-gateway/public') $package -Recurse
Copy-Item (Join-Path $root 'LICENSE.md') $package
$licenses = Join-Path $package 'licenses'
New-Item -ItemType Directory -Force $licenses | Out-Null
$share = Join-Path $root 'builds/ninja-multi-vcpkg-ci/vcpkg_installed/x64-windows-static/share'
Get-ChildItem $share -Filter copyright -Recurse -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $licenses ($_.Directory.Name + '.txt'))
}
$sha = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE) { throw 'Could not determine source commit' }
@{ repository = 'https://github.com/denisvosk/aspia'; commit = $sha; node = $nodeVersion; run = $env:GITHUB_RUN_ID; prototype = $true } |
    ConvertTo-Json | Set-Content (Join-Path $package 'BUILD.json') -Encoding utf8
$files = @(Get-ChildItem $package -File -Recurse | ForEach-Object {
    @{ path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\','/'); sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
})
@{ files = $files } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $package 'PACKAGE_SHA256.json') -Encoding utf8
$tag = "web-gateway-preview.$env:GITHUB_RUN_NUMBER"
$zip = Join-Path $out "aspia-web-gateway-$env:GITHUB_RUN_NUMBER-x64.zip"
Compress-Archive $package -DestinationPath $zip -Force
$checksum = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $([IO.Path]::GetFileName($zip))" | Set-Content "$zip.sha256" -Encoding ascii
$notes = Join-Path $out 'release-notes.txt'
@"
Experimental Aspia 2.7 browser gateway, Windows x64. Not a Host/Console MSI update.
Source: https://github.com/denisvosk/aspia/commit/$sha
Extract the stable AspiaWebGateway directory to C:\AspiaWebGateway (outside C:\Web).
Read README.md, install as administrator, then add Caddy.fragment to the existing IP site.
Includes Node $nodeVersion; no npm or VS installation required on the server.
Local web tests and native PNG/pipe smoke tests passed. Real Windows Host/browser-agent connection still needs validation.
No default credentials, no production deployment and no automatic-update publication.
"@ | Set-Content $notes -Encoding utf8
Run-Native 'gh' @('release','create',$tag,$zip,"$zip.sha256",'--draft','--prerelease','--target',$sha,'--title',"Aspia Web Gateway prototype $env:GITHUB_RUN_NUMBER (x64)",'--notes-file',$notes)
