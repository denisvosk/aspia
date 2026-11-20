# Keep binary resources and all MSI ProductVersions tied to the same source version.
$cmake = Get-Content (Join-Path (Split-Path $PSScriptRoot -Parent) 'CMakeLists.txt') -Raw
$parts = foreach ($name in 'MAJOR', 'MINOR', 'PATCH') {
    $match = [regex]::Match($cmake, "(?m)^set\(ASPIA_VERSION_$name\s+(\d+)\)\s*$")
    if (!$match.Success) { throw "Cannot read ASPIA_VERSION_$name from CMakeLists.txt" }
    $match.Groups[1].Value
}
$parts -join '.'
