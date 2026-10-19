#Requires -Version 5.1
# Run as Administrator. Close the Aspia settings dialog before running.
# Only the three update settings change; no service restart or immediate update.
[CmdletBinding()]
param(
    [string]$UpdateServer = 'https://192.0.2.1/updates',
    [string]$ConfigPath = (Join-Path $env:ProgramData 'aspia\host.json')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$temp = $null
try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Right-click Configure-Updates.bat and select Run as administrator.'
    }
    $uri = [Uri]$UpdateServer
    if (!$uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or $uri.Query -or $uri.Fragment -or $uri.UserInfo) {
        throw 'UpdateServer must be an absolute HTTPS base URL without query, fragment or credentials.'
    }
    $UpdateServer = $UpdateServer.TrimEnd('/')
    $ConfigPath = (Get-Item -LiteralPath $ConfigPath -ErrorAction Stop).FullName
    $utf8 = New-Object Text.UTF8Encoding($false, $true)
    $originalBytes = [IO.File]::ReadAllBytes($ConfigPath)
    $original = $utf8.GetString($originalBytes).TrimStart([char]0xFEFF)
    $before = ConvertFrom-Json -InputObject $original
    if ($before -isnot [System.Management.Automation.PSCustomObject]) { throw 'Expected a JSON object.' }
    # Aspia stores booleans/numbers as strings. Never write JSON true or 1 here.
    $changes = [ordered]@{
        AutoUpdateEnabled = 'true'
        UpdateCheckFrequency = '1'
        UpdateServer = $UpdateServer
    }
    $updated = $original
    foreach ($key in $changes.Keys) {
        $property = $before.PSObject.Properties[$key]
        $regex = New-Object Text.RegularExpressions.Regex(('"' + $key + '"\s*:\s*"(?:\\.|[^"\\])*"'))
        $matches = $regex.Matches($updated)
        $pair = '"' + $key + '": ' + (ConvertTo-Json -InputObject $changes[$key] -Compress)
        if ($null -ne $property) {
            if ($property.Value -isnot [string] -or $matches.Count -ne 1) {
                throw "Unsupported or ambiguous setting: $key. No changes written."
            }
            $m = $matches[0]
            $updated = $updated.Substring(0, $m.Index) + $pair + $updated.Substring($m.Index + $m.Length)
        } else {
            if ($matches.Count -ne 0) { throw "Nested setting conflict: $key" }
            $open = $updated.IndexOf('{')
            $comma = if (@($before.PSObject.Properties).Count -or $updated.Substring($open + 1).TrimStart()[0] -ne '}') { ',' } else { '' }
            $updated = $updated.Insert($open + 1, "`r`n    " + $pair + $comma)
        }
    }
    $after = ConvertFrom-Json -InputObject $updated
    foreach ($key in $changes.Keys) {
        if ($after.$key -isnot [string] -or $after.$key -cne $changes[$key]) { throw "Verification failed: $key" }
    }
    foreach ($property in $before.PSObject.Properties) {
        if ($changes.Contains($property.Name)) { continue }
        $a = ConvertTo-Json -InputObject $property.Value -Depth 100 -Compress
        $b = ConvertTo-Json -InputObject $after.PSObject.Properties[$property.Name].Value -Depth 100 -Compress
        if ($a -cne $b) { throw "Unrelated setting changed: $($property.Name)" }
    }
    if ($original -ceq $updated) { Write-Host 'Settings already match. Nothing changed.'; exit 0 }
    $suffix = [Guid]::NewGuid().ToString('N')
    $temp = $ConfigPath + '.' + $suffix + '.tmp'
    $backup = $ConfigPath + '.before-updates-' + $suffix + '.bak'
    # Create an empty file, copy the original ACL, THEN put sensitive data in it.
    [IO.File]::WriteAllBytes($temp, [byte[]]@())
    Set-Acl -LiteralPath $temp -AclObject (Get-Acl -LiteralPath $ConfigPath)
    [IO.File]::WriteAllText($temp, $updated, $utf8)
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigPath)) -cne [Convert]::ToBase64String($originalBytes)) {
        throw 'Configuration changed concurrently. Close settings and retry. Nothing replaced.'
    }
    # Same-volume atomic replacement; backup remains beside host.json, never in the web directory.
    [IO.File]::Replace($temp, $ConfigPath, $backup)
    $temp = $null
    Write-Host 'Configured: automatic checks enabled, daily, custom HTTPS update server.'
    Write-Host "Server: $UpdateServer"
    Write-Host "Backup: $backup"
    Write-Host 'Users, SeedKey, Router settings and LastUpdateCheck preserved.'
    Write-Host 'Host watches this file. No service restart was requested.'
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($temp -and (Test-Path -LiteralPath $temp)) { Remove-Item -LiteralPath $temp -Force }
}
