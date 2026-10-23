[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $packageRoot 'source\RootStart\Services\ModChroot\LSA\Providers\Android\Wireless\implementation\lsa_nl80211.c'
$ndkRoot = $env:ANDROID_NDK_ROOT
if ([string]::IsNullOrWhiteSpace($ndkRoot)) {
    throw 'Set ANDROID_NDK_ROOT to an Android NDK installation before building the wireless helper.'
}
$ndk = Join-Path $ndkRoot 'toolchains\llvm\prebuilt\windows-x86_64\bin'

if (-not (Test-Path -LiteralPath $source)) { throw "Wireless helper source is missing: $source" }
foreach ($tool in @('aarch64-linux-android21-clang.cmd', 'armv7a-linux-androideabi21-clang.cmd')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ndk $tool))) { throw "Android NDK compiler is missing: $tool" }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$targets = @(
    @{ compiler = 'aarch64-linux-android21-clang.cmd'; output = 'lsa-nl80211-arm64' },
    @{ compiler = 'armv7a-linux-androideabi21-clang.cmd'; output = 'lsa-nl80211-armv7' }
)
foreach ($target in $targets) {
    $output = Join-Path $OutputDirectory $target.output
    & (Join-Path $ndk $target.compiler) -O2 -Wall -Wextra -Werror $source -o $output
    if ($LASTEXITCODE -ne 0) { throw "Wireless helper compilation failed for $($target.output)" }
    if ((Get-Item -LiteralPath $output).Length -lt 4096) { throw "Wireless helper is unexpectedly small: $output" }
}
