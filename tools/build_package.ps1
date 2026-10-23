[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$terpRoot = Split-Path -Parent $packageRoot
$sourceRoot = Join-Path $packageRoot 'source'
$payloadRoot = Join-Path $packageRoot 'payload'
$cygwinRoot = if ([string]::IsNullOrWhiteSpace($env:CYGWIN_ROOT)) { 'C:\cygwin64' } else { $env:CYGWIN_ROOT }
$tar = Join-Path $cygwinRoot 'bin\tar.exe'
$chmod = Join-Path $cygwinRoot 'bin\chmod.exe'
$find = Join-Path $cygwinRoot 'bin\find.exe'
$cygpath = Join-Path $cygwinRoot 'bin\cygpath.exe'

foreach ($required in @($tar, $chmod, $find, $cygpath, (Join-Path $sourceRoot 'RootStart'), (Join-Path $sourceRoot 'NonRootStart'))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required build input is missing: $required"
    }
}

function ConvertTo-CygwinPath {
    param([Parameter(Mandatory)][string]$Path)

    $converted = & $cygpath -u $Path
    $cygpathExitCode = $LASTEXITCODE
    if ($cygpathExitCode -ne 0 -or -not $converted) {
        throw "Unable to convert path for Cygwin: $Path"
    }
    return ([string]$converted).Trim()
}

$sourceCygwin = ConvertTo-CygwinPath $sourceRoot
$rootTarCygwin = ConvertTo-CygwinPath (Join-Path $payloadRoot 'RootStart.tar')
$nonRootTarCygwin = ConvertTo-CygwinPath (Join-Path $payloadRoot 'NonRootStart.tar')

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $terpRoot "tmp\backups\package-build\$stamp\LSALIVE\payload"
$previousPayload = @('RootStart.tar', 'NonRootStart.tar') |
    ForEach-Object { Join-Path $payloadRoot $_ } |
    Where-Object { Test-Path -LiteralPath $_ }
if ($previousPayload.Count -gt 0) {
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    foreach ($existing in $previousPayload) {
        Copy-Item -LiteralPath $existing -Destination (Join-Path $backup (Split-Path -Leaf $existing))
    }
}

New-Item -ItemType Directory -Force -Path $payloadRoot | Out-Null

& $find $sourceRoot -type f -name '*.sh' -exec $chmod 755 '{}' ';'
if ($LASTEXITCODE) { throw 'Failed to set shell-script modes in canonical source.' }

& $chmod 755 `
    (Join-Path $sourceRoot 'RootStart/RST.sh') `
    (Join-Path $sourceRoot 'NonRootStart/NRS.sh') `
    (Join-Path $sourceRoot 'RootStart/Services/ModChroot/LSA/Framework/lsectl') `
    (Join-Path $sourceRoot 'RootStart/Services/ModChroot/LSA/Framework/quarantine-project-backups.sh')
if ($LASTEXITCODE) { throw 'Failed to set LSA command modes in canonical source.' }

& $tar -cf $rootTarCygwin -C $sourceCygwin RootStart
if ($LASTEXITCODE) { throw 'Failed to build RootStart.tar.' }
& $tar -cf $nonRootTarCygwin -C $sourceCygwin NonRootStart
if ($LASTEXITCODE) { throw 'Failed to build NonRootStart.tar.' }

$rootHash = (Get-FileHash -LiteralPath (Join-Path $payloadRoot 'RootStart.tar') -Algorithm SHA256).Hash.ToLower()
$nonRootHash = (Get-FileHash -LiteralPath (Join-Path $payloadRoot 'NonRootStart.tar') -Algorithm SHA256).Hash.ToLower()
@(
    "$rootHash  payload/RootStart.tar"
    "$nonRootHash  payload/NonRootStart.tar"
) | Set-Content -LiteralPath (Join-Path $packageRoot 'manifest/PAYLOAD-SHA256SUMS') -NoNewline:$false

Write-Output "RootStart.tar    $rootHash"
Write-Output "NonRootStart.tar $nonRootHash"
