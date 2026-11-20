# Runs only after both complete Windows build/test/package jobs have passed.
# The release stays DRAFT; no update feed or live website is modified.
$ErrorActionPreference = 'Stop'
$version = & (Join-Path $PSScriptRoot 'read-version.ps1')
$root = Split-Path $PSScriptRoot -Parent
$sha = (git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw 'Cannot resolve source commit' }
$tag = "v$version-audit-inventory-preview.$env:GITHUB_RUN_NUMBER"
$work = Join-Path $env:RUNNER_TEMP "aspia-complete-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
New-Item -ItemType Directory -Force $work | Out-Null
$releaseText = gh release view $tag --repo $env:GITHUB_REPOSITORY --json isDraft,tagName,targetCommitish
if ($LASTEXITCODE) { throw 'The candidate draft release was not found.' }
$release = $releaseText | ConvertFrom-Json
if (!$release.isDraft -or $release.tagName -ne $tag -or $release.targetCommitish -ne $sha) {
    throw 'Refusing to finalize a published release or a release from another source revision.'
}
gh release download $tag --repo $env:GITHUB_REPOSITORY --dir $work --clobber
if ($LASTEXITCODE) { throw 'Could not download the complete draft for validation.' }
$expected = @{}
foreach ($arch in 'x86', 'x86_64') {
    $info = Get-Content (Join-Path $work "build-info-$arch.json") -Raw | ConvertFrom-Json
    if ($info.version -ne $version -or $info.architecture -ne $arch -or
        $info.source_commit -ne $sha -or $info.workflow_run_id -ne $env:GITHUB_RUN_ID) {
        throw "Build provenance mismatch for $arch"
    }
    foreach ($line in Get-Content (Join-Path $work "SHA256SUMS-$arch.txt")) {
        if ($line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9_.-]+)$') { throw "Invalid checksum line for $arch" }
        $hash, $name = $Matches[1], $Matches[2]
        if ($expected.ContainsKey($name) -and $expected[$name] -ne $hash) { throw "Architecture jobs disagree about $name" }
        $expected[$name] = $hash
        $file = Join-Path $work $name
        if (!(Test-Path -LiteralPath $file -PathType Leaf) -or
            (Get-FileHash $file -Algorithm SHA256).Hash.ToLower() -ne $hash) { throw "Release checksum mismatch: $name" }
    }
    foreach ($product in 'host', 'client', 'console', 'router') {
        if (!$expected.ContainsKey("aspia-$product-$version-$arch.msi")) { throw "Missing verified $product $arch MSI" }
    }
}
foreach ($name in "aspia-$version-audit-inventory-source.zip", 'LICENSE.md', 'README-preview.md') {
    if (!$expected.ContainsKey($name)) { throw "Missing verified release asset: $name" }
}
$siteOutput = Join-Path $work 'website'
python (Join-Path $PSScriptRoot 'make-download-site.py') --packages $work --output $siteOutput --version $version --commit $sha --tag $tag
if ($LASTEXITCODE) { throw 'Download site packaging failed.' }
$siteZip = Join-Path $siteOutput "aspia-downloads-$tag.zip"
$allAssets = @($expected.Keys | ForEach-Object { Join-Path $work $_ }) + @($siteZip)
$hashes = foreach ($asset in $allAssets | Sort-Object) { "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $asset).Hash.ToLower(), (Split-Path $asset -Leaf) }
$hashes | Set-Content (Join-Path $work 'SHA256SUMS.txt') -Encoding utf8
$notes = @"
Draft Aspia $version preview from commit $sha.

Both x86 and x64 build/test jobs passed. Eight MSI packages: Console, Host, Client and Router for each architecture. Existing protocol/OLE tests, all 23 installer cultures for the desktop products (Router: its two available cultures), MSI payload extraction/hash checks, Host 2.7.0 and preview.20 upgrades, the installed Host inventory worker/protobuf smoke test, and Router 2.7.0 configuration/users/Host identity preservation gates passed. Build provenance is included per architecture. All downloaded release checksums were verified again.

Read README-preview.md. Interactive two-computer acceptance (including Word/Explorer, journal identity/timing and real inventory) remains required. The Relay stays on 2.7. The Caddy-compatible website ZIP is a prepared download site; it has not been deployed. No automatic-update feed has been changed. This release remains a draft prerelease.
"@
$notesPath = Join-Path $work 'release-notes-complete.txt'
$notes | Set-Content $notesPath -Encoding utf8
gh release upload $tag --repo $env:GITHUB_REPOSITORY --clobber $siteZip (Join-Path $work 'SHA256SUMS.txt')
if ($LASTEXITCODE) { throw 'Could not upload verified website kit/checksums.' }
gh release edit $tag --repo $env:GITHUB_REPOSITORY --draft=true --prerelease --notes-file $notesPath
if ($LASTEXITCODE) { throw 'Could not update draft validation notes.' }
"Verified draft: $tag ($sha). Eight MSI packages and website ZIP; no production publication." >> $env:GITHUB_STEP_SUMMARY
