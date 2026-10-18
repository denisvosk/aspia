# Private experimental packages, never an automatic-update publication.
param([ValidateSet('x86','x64')][string]$Arch = 'x86')
$ErrorActionPreference = 'Stop'
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$root = Split-Path $PSScriptRoot -Parent
$bin = Join-Path $root 'builds/ninja-multi-vcpkg-ci/Release'
$out = Join-Path $root 'preview'
New-Item -ItemType Directory -Force $out | Out-Null
$env:ASPIA_VERSION = '2.7.1'
$env:ASPIA_BIN_DIR = $bin
$wixBin = Split-Path (Get-Command candle.exe).Source
$sdkScript = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x86/wisubstg.vbs" | Sort-Object FullName -Descending | Select-Object -First 1
if (!$sdkScript) { throw 'Windows SDK MSI scripts (wisubstg.vbs) not installed.' }
$sdk = $sdkScript.DirectoryName
# Match installer/build.cmd from 2.7: sv-fi.wxl exists in the source tree,
# but is not shipped and has no corresponding built-in WiX UI localization.
$installerCultures = @(
    'en-us', 'cs-cz', 'da-dk', 'de-de', 'el-gr', 'es-es', 'fr-fr', 'he-il',
    'hu-hu', 'it-it', 'ja-jp', 'ko-kr', 'nl-nl', 'nb-no', 'pl-pl', 'pt-br',
    'pt-pt', 'ru-ru', 'sv-se', 'tr-tr', 'uk-ua', 'zh-cn', 'zh-tw'
)
function Run-Native([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe failed with exit code $LASTEXITCODE" }
}
Push-Location (Join-Path $root 'installer')
try {
    foreach ($product in @('host', 'client', 'console')) {
        $base = Join-Path $out "aspia-$product-2.7.1-$packageArch.msi"
        $object = Join-Path $out "$product.wixobj"
        Run-Native "$wixBin/candle.exe" @('-nologo', '-out', $object, '-arch', $Arch, '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension', "$product.wxs")
        Write-Host "Linking $product MSI ($Arch, en-us)"
        Run-Native "$wixBin/light.exe" @('-nologo', '-sval', '-out', $base, '-cultures:en-us', '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension', '-loc', "translations/$product.en-us.wxl", $object)
        $languages = @('1033')
        foreach ($culture in $installerCultures) {
            if ($culture -eq 'en-us') { continue }
            $translation = Join-Path (Get-Location).Path "translations/$product.$culture.wxl"
            if (!(Test-Path $translation)) { throw "Missing installer translation: $translation" }
            $lcid = [System.Globalization.CultureInfo]::GetCultureInfo($culture).LCID
            $localized = Join-Path $out "$product-$culture.msi"
            $transform = Join-Path $out "$product-$culture.mst"
            Write-Host "Linking $product MSI ($Arch, $culture)"
            Run-Native "$wixBin/light.exe" @('-nologo', '-sval', '-out', $localized, "-cultures:$culture", '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension', '-loc', $translation, $object)
            Run-Native "$wixBin/torch.exe" @('-nologo', '-p', '-t', 'language', $base, $localized, '-out', $transform)
            Run-Native 'cscript.exe' @('//nologo', "$sdk/wisubstg.vbs", $base, $transform, "$lcid")
            $languages += "$lcid"
        }
        Run-Native 'cscript.exe' @('//nologo', "$sdk/wilangid.vbs", $base, 'Package', (($languages + '0') -join ','))
        # Administrative extraction verifies the cabinet and all packaged executables;
        # it does not install a remote-access service on the CI machine.
        $extract = Join-Path $out "extract-$product"
        $log = Join-Path $out "extract-$product.log"
        $p = Start-Process msiexec.exe -ArgumentList @('/a', "`"$base`"", '/qn', "TARGETDIR=`"$extract`"", '/l*v', "`"$log`"") -Wait -PassThru
        if ($p.ExitCode -notin 0,3010) { throw "$product MSI extraction failed: $($p.ExitCode)" }
        $executables = @(Get-ChildItem $extract -Recurse -File | Where-Object { $_.Extension -in '.exe','.dll' })
        if (!$executables.Count) { throw "$product MSI has no program files" }
        foreach ($file in $executables) {
            $built = Join-Path $bin $file.Name
            if (!(Test-Path $built) -or (Get-FileHash $built).Hash -ne (Get-FileHash $file.FullName).Hash) {
                throw "MSI content mismatch: $($file.Name)"
            }
        }
    }
} finally { Pop-Location }
& "$PSScriptRoot/test-host-upgrade.ps1" -NewMsi "$out/aspia-host-2.7.1-$packageArch.msi" -Arch $Arch
$sha = (git -C $root rev-parse HEAD).Trim()
Run-Native 'git' @('-C', $root, 'archive', '--format=zip', "--output=$out/aspia-2.7.1-clipboard-source.zip", $sha)
Copy-Item "$root/LICENSE.md" "$out/LICENSE.md"
Copy-Item "$root/docs/clipboard-preview.md" "$out/README-preview.md"
$assets = @((Get-ChildItem "$out/aspia-*-2.7.1-$packageArch.msi").FullName) + @("$out/aspia-2.7.1-clipboard-source.zip", "$out/LICENSE.md", "$out/README-preview.md")
$hashes = foreach ($asset in $assets) { "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $asset).Hash.ToLower(), (Split-Path $asset -Leaf) }
$hashes | Set-Content "$out/SHA256SUMS-$packageArch.txt" -Encoding utf8
$assets += "$out/SHA256SUMS-$packageArch.txt"
$tag = "v2.7.1-clipboard-preview.$env:GITHUB_RUN_NUMBER"
$notes = "Private test build from $sha. Windows Host, Client and Console; only architectures present in the MSI filenames have been built. Wait for the complete workflow before testing. Read README-preview.md before testing. Not published to any automatic-update server. Original Router/Relay 2.7 are unchanged. Automated protocol/OLE tests, MSI extraction and isolated Host upgrade test passed for the uploaded packages; two-computer interactive acceptance testing is still required."
$notes | Set-Content "$out/release-notes.txt" -Encoding utf8
gh release view $tag --repo $env:GITHUB_REPOSITORY --json id 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    gh release create $tag --repo $env:GITHUB_REPOSITORY --target $sha --draft --prerelease --title 'Aspia 2.7.1 — clipboard files preview' --notes-file "$out/release-notes.txt"
    if ($LASTEXITCODE -ne 0) {
        # Another architecture may have created the draft concurrently.
        Run-Native 'gh' @('release', 'view', $tag, '--repo', $env:GITHUB_REPOSITORY, '--json', 'id')
    }
}
Run-Native 'gh' (@('release', 'upload', $tag, '--repo', $env:GITHUB_REPOSITORY, '--clobber') + $assets)
"Draft release: https://github.com/$env:GITHUB_REPOSITORY/releases" >> $env:GITHUB_STEP_SUMMARY
