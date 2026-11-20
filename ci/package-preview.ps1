# Draft experimental packages, never an automatic-update publication.
param([ValidateSet('x86','x64')][string]$Arch = 'x86')
$ErrorActionPreference = 'Stop'
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$root = Split-Path $PSScriptRoot -Parent
$bin = Join-Path $root 'builds/ninja-multi-vcpkg-ci/Release'
$out = Join-Path $root 'preview'
New-Item -ItemType Directory -Force $out | Out-Null
$version = & (Join-Path $PSScriptRoot 'read-version.ps1')
$env:ASPIA_VERSION = $version
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
    foreach ($product in @('host', 'client', 'console', 'router')) {
        $base = Join-Path $out "aspia-$product-$version-$packageArch.msi"
        $object = Join-Path $out "$product.wixobj"
        Run-Native "$wixBin/candle.exe" @('-nologo', '-out', $object, '-arch', $Arch, '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension', "$product.wxs")
        Write-Host "Linking $product MSI ($Arch, en-us)"
        Run-Native "$wixBin/light.exe" @('-nologo', '-sval', '-out', $base, '-cultures:en-us', '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension', '-loc', "translations/$product.en-us.wxl", $object)
        $languages = @('1033')
        # Router ships only these two translations in the 2.7 source. Retain all
        # 23 existing cultures for Host, Client and Console without substitution.
        $cultures = if ($product -eq 'router') { @('en-us', 'fr-fr') } else { $installerCultures }
        foreach ($culture in $cultures) {
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
$hostMsi = Join-Path $out "aspia-host-$version-$packageArch.msi"
& (Join-Path $PSScriptRoot 'test-host-upgrade.ps1') -NewMsi $hostMsi -Arch $Arch -ExpectedVersion $version
$routerMsi = Join-Path $out "aspia-router-$version-$packageArch.msi"
& (Join-Path $PSScriptRoot 'test-router-upgrade.ps1') -NewMsi $routerMsi -Arch $Arch -ExpectedVersion $version
$sha = (git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw 'Cannot resolve source commit' }
Run-Native 'git' @('-C', $root, 'archive', '--format=zip', "--output=$out/aspia-$version-audit-inventory-source.zip", $sha)
Copy-Item "$root/LICENSE.md" "$out/LICENSE.md"
Copy-Item "$root/docs/audit-inventory-preview.md" "$out/README-preview.md"
$buildInfo = [ordered]@{
    version = $version
    architecture = $packageArch
    source_commit = $sha
    workflow_run_id = $env:GITHUB_RUN_ID
    workflow_run_number = $env:GITHUB_RUN_NUMBER
    validation = @('ctest', 'localized-msi-extraction-and-hashes', 'host-2.7.0-upgrade', 'host-preview20-upgrade', 'installed-host-inventory-worker-protobuf', 'router-2.7.0-upgrade-and-data-preservation')
    interactive_acceptance = 'not_performed'
}
$buildInfo | ConvertTo-Json -Depth 5 | Set-Content "$out/build-info-$packageArch.json" -Encoding utf8
$assets = @((Get-ChildItem "$out/aspia-*-$version-$packageArch.msi").FullName) + @("$out/aspia-$version-audit-inventory-source.zip", "$out/LICENSE.md", "$out/README-preview.md", "$out/build-info-$packageArch.json")
$hashes = foreach ($asset in $assets) { "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $asset).Hash.ToLower(), (Split-Path $asset -Leaf) }
$hashes | Set-Content "$out/SHA256SUMS-$packageArch.txt" -Encoding utf8
$assets += "$out/SHA256SUMS-$packageArch.txt"
$tag = "v$version-audit-inventory-preview.$env:GITHUB_RUN_NUMBER"
$notes = "DRAFT — assembly in progress from $sha. Windows Host, Client, Console and Router. Only architectures present in the MSI filenames have been built. Wait for both architecture jobs and the final validation job before testing. This build has not been published to any automatic-update server. Relay 2.7 is retained. Read README-preview.md; real two-computer and Word/Explorer acceptance testing is still required."
$notes | Set-Content "$out/release-notes.txt" -Encoding utf8
gh release view $tag --repo $env:GITHUB_REPOSITORY --json id 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    gh release create $tag --repo $env:GITHUB_REPOSITORY --target $sha --draft --prerelease --title "Aspia $version — sessions and inventory preview" --notes-file "$out/release-notes.txt"
    if ($LASTEXITCODE -ne 0) {
        # Another architecture may have created the draft concurrently.
        Run-Native 'gh' @('release', 'view', $tag, '--repo', $env:GITHUB_REPOSITORY, '--json', 'id')
    }
}
$release = gh release view $tag --repo $env:GITHUB_REPOSITORY --json isDraft,targetCommitish,tagName | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or !$release.isDraft -or $release.tagName -ne $tag -or $release.targetCommitish -ne $sha) {
    throw 'Refusing to upload packages into a published release or a release from another commit.'
}
Run-Native 'gh' (@('release', 'upload', $tag, '--repo', $env:GITHUB_REPOSITORY, '--clobber') + $assets)
"Draft release: https://github.com/$env:GITHUB_REPOSITORY/releases" >> $env:GITHUB_STEP_SUMMARY
