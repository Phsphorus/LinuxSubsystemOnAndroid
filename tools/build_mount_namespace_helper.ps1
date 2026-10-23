[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'source\RootStart\Tools\mountns\lsa_mountns.c'
$ndkRoot = $env:ANDROID_NDK_ROOT
if ([string]::IsNullOrWhiteSpace($ndkRoot)) {
    throw 'Set ANDROID_NDK_ROOT to an Android NDK installation before building the mount namespace helper.'
}
$hostTag = 'windows-x86_64'
$toolchain = Join-Path $ndkRoot "toolchains\llvm\prebuilt\$hostTag\bin"

if (-not (Test-Path -LiteralPath $source)) { throw "Missing mount namespace helper source: $source" }
if (-not (Test-Path -LiteralPath $toolchain)) { throw "Android NDK toolchain is unavailable: $toolchain" }

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$targets = @(
    @{ Name = 'arm64'; Compiler = 'aarch64-linux-android21-clang.cmd' },
    @{ Name = 'armv7'; Compiler = 'armv7a-linux-androideabi21-clang.cmd' },
    @{ Name = 'x86'; Compiler = 'i686-linux-android21-clang.cmd' },
    @{ Name = 'x86_64'; Compiler = 'x86_64-linux-android21-clang.cmd' }
)

foreach ($target in $targets) {
    $compiler = Join-Path $toolchain $target.Compiler
    if (-not (Test-Path -LiteralPath $compiler)) { throw "Missing Android compiler: $compiler" }
    $output = Join-Path $OutputDirectory ("lsa-mountns-" + $target.Name)
    & $compiler -O2 -fPIE -pie -Wall -Wextra -Werror $source -o $output
    if ($LASTEXITCODE -ne 0) { throw "Failed to build mount namespace helper for $($target.Name)" }
    Write-Output "$($target.Name) $output"
}
