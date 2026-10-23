[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$packageRoot = Split-Path -Parent $PSScriptRoot
$terpRoot = Split-Path -Parent $packageRoot
$sourceRoot = Join-Path $packageRoot 'source'
$assetsRoot = Join-Path $packageRoot 'assets'
$deployTemplate = Join-Path $packageRoot 'deploy'
$lsaX11Workspace = if ([string]::IsNullOrWhiteSpace($env:LSA_X11_WORKSPACE)) { Join-Path $terpRoot 'lsa-x11' } else { $env:LSA_X11_WORKSPACE }
$releaseRoot = Join-Path $terpRoot 'LSADeploy'
$tmpRoot = Join-Path $terpRoot 'tmp'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$buildRoot = Join-Path $tmpRoot "package-builds\$stamp"
$stageRoot = Join-Path $buildRoot 'LSADeploy'
$smokeRoot = Join-Path $buildRoot 'clean-extraction'
$wirelessBuildRoot = Join-Path $buildRoot 'wireless-helper'
$mountNamespaceBuildRoot = Join-Path $buildRoot 'mountns-helper'
$backupRoot = Join-Path $tmpRoot "backups\release-build\$stamp"
$cygwinRoot = if ([string]::IsNullOrWhiteSpace($env:CYGWIN_ROOT)) { 'C:\cygwin64' } else { $env:CYGWIN_ROOT }
$tar = Join-Path $cygwinRoot 'bin\tar.exe'
$cygpath = Join-Path $cygwinRoot 'bin\cygpath.exe'

foreach ($required in @(
    $sourceRoot,
    $assetsRoot,
    $deployTemplate,
    (Join-Path $deployTemplate 'deploy.sh'),
    (Join-Path $deployTemplate 'rootstart_pty.py'),
    (Join-Path $deployTemplate 'APPS.tsv'),
    (Join-Path $deployTemplate 'APPS-README.md'),
    (Join-Path $packageRoot 'VERSION'),
    (Join-Path $packageRoot 'README.txt'),
    (Join-Path $packageRoot 'LICENSE'),
    (Join-Path $packageRoot 'NOTICE'),
    (Join-Path $packageRoot 'THIRD_PARTY_NOTICES.md'),
    (Join-Path $packageRoot 'SOURCE_AVAILABILITY.md'),
    (Join-Path $packageRoot 'LICENSES\Apache-2.0.txt'),
    (Join-Path $packageRoot 'LICENSES\GPL-3.0.txt'),
    (Join-Path $packageRoot 'manifest\SOURCES.tsv'),
    (Join-Path $packageRoot 'manifest\LSA-X11-BUILD.tsv'),
    (Join-Path $lsaX11Workspace 'LICENSE'),
    (Join-Path $lsaX11Workspace 'gradlew'),
    (Join-Path $sourceRoot 'RootStart\Services\ModChroot\LSA\Framework\architecture-normalize.sh'),
    (Join-Path $sourceRoot 'RootStart\Services\ModChroot\LSA\Providers\Android\Wireless\implementation\lsa_nl80211.c'),
    (Join-Path $sourceRoot 'RootStart\Tools\mountns\lsa_mountns.c'),
    (Join-Path $PSScriptRoot 'build_wireless_helper.ps1'),
    (Join-Path $PSScriptRoot 'build_mount_namespace_helper.ps1'),
    $tar,
    $cygpath
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release input is missing: $required"
    }
}

function ConvertTo-CygwinPath {
    param([Parameter(Mandatory)][string]$Path)
    $converted = & $cygpath -u $Path
    if ($LASTEXITCODE -ne 0 -or -not $converted) {
        throw "Unable to convert path for Cygwin: $Path"
    }
    return ([string]$converted).Trim()
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory)][string]$Base,
        [Parameter(Mandatory)][string]$Path
    )
    # Windows PowerShell 5.1 runs on .NET Framework, which has no
    # System.IO.Path.GetRelativePath. Uri keeps the release builder usable on
    # the supported Windows hosts without requiring PowerShell 7.
    $baseUri = New-Object System.Uri(($Base.TrimEnd('\') + '\'))
    $pathUri = New-Object System.Uri($Path)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('\', '/')
}

function Assert-CleanCanonicalInputs {
    $canonicalRoots = @($sourceRoot, $deployTemplate, $PSScriptRoot)
    $forbidden = $canonicalRoots | ForEach-Object {
        Get-ChildItem -LiteralPath $_ -Recurse -Force -File
    } |
        Where-Object {
            $_.Name -match '\.(pyc|pyo)$' -or
            $_.FullName -match '(?i)[\\/](__pycache__|\.pids|logs|run|runtime)[\\/]' -or
            $_.Name -match '(?i)(^|\.)(pid|sock|secret)$'
        }
    if ($forbidden) {
        $names = $forbidden | ForEach-Object { $_.FullName }
        throw "Canonical source contains generated/runtime content:`n$($names -join "`n")"
    }
}

Assert-CleanCanonicalInputs

function Assert-SecurityReleaseInvariants {
    # These are release-stopping regressions, not lint preferences.  A normal
    # package must never force the whole host into Permissive, recreate the
    # historical world-readable HAL secret, or log an unauthenticated request
    # line that contains the credential.
    $rootStart = Join-Path $sourceRoot 'RootStart'
    $matches = @(
        Get-ChildItem -LiteralPath $rootStart -Recurse -File -Include *.sh,*.py |
            Select-String -Pattern '(?i)\bsetenforce\s+0\b|chmod\s*\(.*SECRET_PATH.*0o644|log\s*\(\s*f?["'']REQ\s*\{' -ErrorAction Stop
    )
    if ($matches) {
        $locations = $matches | ForEach-Object { "$($_.Path):$($_.LineNumber)" }
        throw "Security release invariant failed:`n$($locations -join "`n")"
    }
}

Assert-SecurityReleaseInvariants

# Rebuild the two canonical payloads first.  That helper records any previous
# payload copies under Terp\tmp\backups; it never discards the only prior copy.
& (Join-Path $PSScriptRoot 'build_package.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Canonical payload build failed.' }
& (Join-Path $PSScriptRoot 'build_wireless_helper.ps1') -OutputDirectory $wirelessBuildRoot
if ($LASTEXITCODE -ne 0) { throw 'Generic Wireless helper build failed.' }
& (Join-Path $PSScriptRoot 'build_mount_namespace_helper.ps1') -OutputDirectory $mountNamespaceBuildRoot
if ($LASTEXITCODE -ne 0) { throw 'Private mount-namespace helper build failed.' }

New-Item -ItemType Directory -Force -Path (Join-Path $stageRoot 'payload'), (Join-Path $stageRoot 'apps'), (Join-Path $stageRoot 'manifest'), (Join-Path $stageRoot 'bootstrap'), (Join-Path $stageRoot 'bootstrap\wireless'), (Join-Path $stageRoot 'bootstrap\mountns'), (Join-Path $stageRoot 'LICENSES'), (Join-Path $stageRoot 'sources') | Out-Null
Copy-Item -LiteralPath (Join-Path $packageRoot 'payload\RootStart.tar'), (Join-Path $packageRoot 'payload\NonRootStart.tar') -Destination (Join-Path $stageRoot 'payload')
Copy-Item -LiteralPath (Join-Path $deployTemplate 'deploy.sh') -Destination (Join-Path $stageRoot 'deploy.sh')
Copy-Item -LiteralPath (Join-Path $packageRoot 'VERSION') -Destination (Join-Path $stageRoot 'VERSION')
Copy-Item -LiteralPath (Join-Path $packageRoot 'README.txt') -Destination (Join-Path $stageRoot 'README.txt')
Copy-Item -LiteralPath (Join-Path $packageRoot 'LICENSE'), (Join-Path $packageRoot 'NOTICE'), (Join-Path $packageRoot 'THIRD_PARTY_NOTICES.md'), (Join-Path $packageRoot 'SOURCE_AVAILABILITY.md') -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $packageRoot 'LICENSES\Apache-2.0.txt'), (Join-Path $packageRoot 'LICENSES\GPL-3.0.txt') -Destination (Join-Path $stageRoot 'LICENSES')
Copy-Item -LiteralPath (Join-Path $packageRoot 'manifest\LSA-X11-BUILD.tsv') -Destination (Join-Path $stageRoot 'manifest\LSA-X11-BUILD.tsv')
Copy-Item -LiteralPath (Join-Path $deployTemplate 'APPS-README.md') -Destination (Join-Path $stageRoot 'apps\README.md')
Copy-Item -LiteralPath (Join-Path $sourceRoot 'RootStart\Services\ModChroot\LSA\Framework\architecture-normalize.sh') -Destination (Join-Path $stageRoot 'bootstrap\architecture-normalize.sh')
Copy-Item -LiteralPath (Join-Path $deployTemplate 'rootstart_pty.py') -Destination (Join-Path $stageRoot 'bootstrap\rootstart_pty.py')
Copy-Item -LiteralPath (Join-Path $wirelessBuildRoot 'lsa-nl80211-arm64'), (Join-Path $wirelessBuildRoot 'lsa-nl80211-armv7') -Destination (Join-Path $stageRoot 'bootstrap\wireless')
Copy-Item -LiteralPath (Join-Path $mountNamespaceBuildRoot 'lsa-mountns-arm64'), (Join-Path $mountNamespaceBuildRoot 'lsa-mountns-armv7'), (Join-Path $mountNamespaceBuildRoot 'lsa-mountns-x86'), (Join-Path $mountNamespaceBuildRoot 'lsa-mountns-x86_64') -Destination (Join-Path $stageRoot 'bootstrap\mountns')

$apps = Import-Csv -LiteralPath (Join-Path $deployTemplate 'APPS.tsv') -Delimiter "`t"
if ($apps.Count -lt 2) { throw 'The release must contain both Termux:API and LSA X11 app entries.' }
foreach ($app in $apps) {
    $input = Join-Path $assetsRoot $app.file
    $output = Join-Path $stageRoot "apps\$($app.file)"
    if (-not (Test-Path -LiteralPath $input)) { throw "Bundled application input is missing: $input" }
    $actual = (Get-FileHash -LiteralPath $input -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $app.sha256.ToLower()) {
        throw "Bundled application checksum differs from approved metadata: $($app.file)"
    }
    Copy-Item -LiteralPath $input -Destination $output
}
@(
    "file`tpackage`tversion_code`tversion_name`tsha256"
    foreach ($app in $apps) {
        "$($app.file)`t$($app.package)`t$($app.version_code)`t$($app.version_name)`t$($app.sha256)"
    }
) | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\APPS.tsv')

$lsaX11App = @($apps | Where-Object { $_.file -eq 'lsa-x11.apk' })
if ($lsaX11App.Count -ne 1) { throw 'Exactly one lsa-x11.apk app metadata entry is required.' }
$lsaX11Revision = (& git -C $lsaX11Workspace rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $lsaX11Revision -notmatch '^[0-9a-f]{40}$') {
    throw 'Unable to identify the designated LSA-X11 workspace Git revision.'
}
$lsaX11DirtyEntries = @(& git -C $lsaX11Workspace status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Unable to determine designated LSA-X11 workspace status.' }
$lsaX11WorkspaceState = if ($lsaX11DirtyEntries.Count -gt 0) { 'DIRTY_WORKSPACE' } else { 'CLEAN_WORKSPACE' }
$lsaX11BuildAttestation = @(Import-Csv -LiteralPath (Join-Path $packageRoot 'manifest\LSA-X11-BUILD.tsv') -Delimiter "`t")
if ($lsaX11BuildAttestation.Count -ne 1) { throw 'Exactly one LSA-X11 build attestation entry is required.' }
$lsaX11Attestation = $lsaX11BuildAttestation[0]
if ($lsaX11Attestation.apk_file -ne 'lsa-x11.apk' -or
    $lsaX11Attestation.apk_sha256.ToLower() -ne $lsaX11App[0].sha256.ToLower() -or
    $lsaX11Attestation.workspace_revision -ne $lsaX11Revision -or
    $lsaX11Attestation.workspace_state -ne $lsaX11WorkspaceState -or
    $lsaX11Attestation.build_task -ne ':lorie-app:assembleStandaloneDebug' -or
    $lsaX11Attestation.correspondence_status -ne 'REBUILT_FROM_RECORDED_WORKSPACE') {
    throw 'LSA-X11 build attestation does not match the approved APK or designated workspace.'
}
$lsaX11SourceCorrespondence = $lsaX11Attestation.correspondence_status
$lsaX11ShortRevision = $lsaX11Revision.Substring(0, 12)
$lsaX11SourceArchiveName = "lsa-x11-workspace-$lsaX11ShortRevision-source.tar.gz"
$lsaX11SourceArchive = Join-Path $stageRoot "sources\$lsaX11SourceArchiveName"

# The APK is a separately licensed GPL component. Ship a source snapshot of
# the designated build workspace in the same release without source-machine
# caches, build outputs, local SDK paths, historical Workshop data, or Git
# metadata. Nested checked-out upstream source trees remain included.
$lsaX11ArchiveArgs = @(
    '--create', '--gzip',
    "--file=$(ConvertTo-CygwinPath -Path $lsaX11SourceArchive)",
    "--directory=$(ConvertTo-CygwinPath -Path $lsaX11Workspace)",
    "--transform=s,^\./,lsa-x11-workspace-$lsaX11ShortRevision/,",
    '--exclude=.git', '--exclude=.gradle', '--exclude=.cxx', '--exclude=build',
    '--exclude=BuildOut', '--exclude=Workshop', '--exclude=local.properties',
    '.'
)
& $tar @lsaX11ArchiveArgs
if ($LASTEXITCODE -ne 0) { throw 'Unable to create the LSA-X11 source snapshot.' }
$lsaX11SourceArchiveEntries = @(& $tar -tzf (ConvertTo-CygwinPath -Path $lsaX11SourceArchive))
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the LSA-X11 source snapshot.' }
if ($lsaX11SourceArchiveEntries | Where-Object { $_ -match '(^|/)(\.git|\.gradle|\.cxx|build|BuildOut|Workshop)(/|$)|(^|/)local\.properties$' }) {
    throw 'LSA-X11 source snapshot contains excluded local/build/history material.'
}
foreach ($requiredSourceEntry in @("lsa-x11-workspace-$lsaX11ShortRevision/LICENSE", "lsa-x11-workspace-$lsaX11ShortRevision/README.md", "lsa-x11-workspace-$lsaX11ShortRevision/gradlew")) {
    if ($lsaX11SourceArchiveEntries -notcontains $requiredSourceEntry) {
        throw "LSA-X11 source snapshot is missing required source file: $requiredSourceEntry"
    }
}
$lsaX11SourceArchiveHash = (Get-FileHash -LiteralPath $lsaX11SourceArchive -Algorithm SHA256).Hash.ToLower()

Copy-Item -LiteralPath (Join-Path $packageRoot 'manifest\SOURCES.tsv') -Destination (Join-Path $stageRoot 'manifest\SOURCES.tsv')
$tab = [string][char]9
@(
    @(
        'LSA-X11 workspace snapshot',
        "sources/$lsaX11SourceArchiveName",
        'GPL-3.0-only',
        'LICENSES/GPL-3.0.txt',
        'Terp/lsa-x11 workspace',
        "$lsaX11Revision;$lsaX11WorkspaceState",
        "Same-release source archive;sha256=$lsaX11SourceArchiveHash",
        $lsaX11SourceCorrespondence
    ) -join $tab
) | Add-Content -LiteralPath (Join-Path $stageRoot 'manifest\SOURCES.tsv')

$payloadEntries = @('payload/RootStart.tar', 'payload/NonRootStart.tar', 'bootstrap/wireless/lsa-nl80211-arm64', 'bootstrap/wireless/lsa-nl80211-armv7', 'bootstrap/mountns/lsa-mountns-arm64', 'bootstrap/mountns/lsa-mountns-armv7', 'bootstrap/mountns/lsa-mountns-x86', 'bootstrap/mountns/lsa-mountns-x86_64') + ($apps | ForEach-Object { "apps/$($_.file)" })
$checksumLines = foreach ($relative in $payloadEntries) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $stageRoot $relative.Replace('/', '\')) -Algorithm SHA256).Hash.ToLower()
    "$hash  $relative"
}
$checksumLines | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\PAYLOAD-SHA256SUMS')

$sourcePaths = @(
    'Canonical inputs:'
    'source/RootStart/'
    'source/NonRootStart/'
    'deploy/deploy.sh'
    'deploy/APPS.tsv'
    'deploy/APPS-README.md'
    'LICENSE'
    'NOTICE'
    'THIRD_PARTY_NOTICES.md'
    'SOURCE_AVAILABILITY.md'
    'LICENSES/Apache-2.0.txt'
    'LICENSES/GPL-3.0.txt'
    'manifest/SOURCES.tsv'
    'manifest/LSA-X11-BUILD.tsv'
    'assets/termux-api.apk'
    'assets/lsa-x11.apk'
    'Terp/lsa-x11 (designated source workspace)'
    ''
    'Canonical source files:'
) + (Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Sort-Object FullName | ForEach-Object { "source/$(Get-RelativePath -Base $sourceRoot -Path $_.FullName)" })
$sourcePaths | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\SOURCE_PATHS.txt')

@(
    "release_version=$(Get-Content -LiteralPath (Join-Path $packageRoot 'VERSION') -Raw | ForEach-Object { $_.Trim() })"
    "built_utc=$((Get-Date).ToUniversalTime().ToString('o'))"
    'source_tree=LSALIVE/source'
    'architecture_policy=android_abi,kernel,termux_userspace,linux_rootfs,individual_binary_are_independent_axes'
    'wireless_helper=generic_nl80211_frame_tx;architectures:arm64,armv7;source:LSA Providers Android Wireless implementation lsa_nl80211.c'
    'mount_namespace_helper=generic_private_mount_tree;architectures:arm64,armv7,x86,x86_64;source:LSA RootStart Tools mountns lsa_mountns.c'
    'rootfs_mapping=arm64:arm64;armv7:armhf;x86_64:amd64;x86:i386'
    'device_model_policy=reporting_only_not_selection'
    'secret_policy=device_local_only;state:0711;secret_dir:0700;secret:0600'
    "lsa_x11_workspace_revision=$lsaX11Revision"
    "lsa_x11_workspace_state=$lsaX11WorkspaceState"
    "lsa_x11_source_archive=sources/$lsaX11SourceArchiveName"
    "lsa_x11_source_archive_sha256=$lsaX11SourceArchiveHash"
    'lsa_x11_build_attestation=manifest/LSA-X11-BUILD.tsv'
    "lsa_x11_source_correspondence=$lsaX11SourceCorrespondence"
) | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\build-info.txt')

@(
    "package`trequired_for`tinstallation_context"
    "bash`tframework execution`tTermux user"
    "python`tLSA service runtime and device-local secret generation`tTermux user"
    "debootstrap`trootfs creation when no complete rootfs exists`tTermux package, launched by Android root"
    "termux-api`tgeneric Termux sensor/camera/location command provider`tTermux user"
    "iw`tstandard nl80211 inspection and qualification tool; materialized into an LSA-owned root-readable path`tTermux user package bootstrap"
) | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\termux-packages.txt')

@(
    "package`trole"
    "debootstrap minbase (detected Debian architecture)`tbase rootfs"
    "libasound2-plugins	generic Linux audio integration when available"
) | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\debian-packages.txt')

@(
    "path	owner_at_install	mode_policy"
    "/data/local/RootStart	0:0	root-owned release tree"
    "/data/data/com.termux/files/home/NonRootStart	resolved Termux UID:GID	Termux-user release tree"
    "/data/local/RootStart/Services/halagent/state	0:0	0711"
    "/data/local/RootStart/Services/halagent/state/secret	0:0	0700"
    "/data/local/RootStart/Services/halagent/state/secret/secret	0:0	0600"
    "/data/local/RootStart/Services/ModChroot/state	0:0	0700"
    "/data/local/RootStart/Services/ModChroot/state/backend-rejections.tsv	0:0	0600 when present"
) | Set-Content -LiteralPath (Join-Path $stageRoot 'manifest\OWNERSHIP.tsv')

Get-ChildItem -LiteralPath $stageRoot -Recurse -Force | Sort-Object FullName |
    ForEach-Object { Get-RelativePath -Base $stageRoot -Path $_.FullName } |
    Where-Object { $_ -ne 'manifest/TREE.txt' } |
    Add-Content -LiteralPath (Join-Path $stageRoot 'manifest\TREE.txt')
Add-Content -LiteralPath (Join-Path $stageRoot 'manifest\TREE.txt') 'manifest/TREE.txt'

# The artifact must be usable from a clean extraction rather than accidentally
# relying on a sibling source tree.
$stageCygwin = ConvertTo-CygwinPath $stageRoot
$smokeCygwin = ConvertTo-CygwinPath $smokeRoot
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
& $tar -xf (ConvertTo-CygwinPath (Join-Path $stageRoot 'payload\RootStart.tar')) -C $smokeCygwin
if ($LASTEXITCODE -ne 0) { throw 'Clean RootStart extraction failed.' }
& $tar -xf (ConvertTo-CygwinPath (Join-Path $stageRoot 'payload\NonRootStart.tar')) -C $smokeCygwin
if ($LASTEXITCODE -ne 0) { throw 'Clean NonRootStart extraction failed.' }

foreach ($required in @(
    'RootStart/RST.sh',
    'RootStart/Services/ModChroot/ModChroot.sh',
    'RootStart/Services/ModChroot/LSA/Framework/lsectl',
    'RootStart/Services/ModChroot/LSA/Framework/architecture-normalize.sh',
    'RootStart/Services/ModChroot/LSA/Modules/Wireless/backends/host-interface.backend',
    'RootStart/Services/ModChroot/LSA/Modules/Wireless/backends/termux-uplink-z.backend',
    'RootStart/Services/ModChroot/LSA/Providers/Android/Wireless/wireless.provider',
    'RootStart/Services/ModChroot/LSA/Providers/Android/Wireless/implementation/wireless_inventory.py',
    'RootStart/Services/ModChroot/LSA/Providers/Android/Wireless/implementation/wireless_qualification.py',
    'RootStart/Services/ModChroot/LSA/Providers/Android/Wireless/implementation/lsa_nl80211.c',
    'RootStart/Tools/mountns/lsa_mountns.c',
    'NonRootStart/NRS.sh'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $smokeRoot $required.Replace('/', '\')))) {
        throw "Clean extraction is missing expected file: $required"
    }
}
$forbiddenPayload = & $tar -tf (ConvertTo-CygwinPath (Join-Path $stageRoot 'payload\RootStart.tar'))
$forbiddenPayload += & $tar -tf (ConvertTo-CygwinPath (Join-Path $stageRoot 'payload\NonRootStart.tar'))
if ($forbiddenPayload | Where-Object { -not $_.EndsWith('/') -and $_ -match '(?i)(^|/)(__pycache__|\.pids|logs|run|runtime)(/|$)|\.(pyc|pyo)$|(^|/)(secret|.*\.pid|.*\.sock)$' }) {
    throw 'Payload contains generated runtime state, a secret, PID/socket state, or Python bytecode.'
}
if ($forbiddenPayload | Where-Object { $_ -match '(^|/)\.\.(/|$)|^/' }) {
    throw 'Payload archive contains an unsafe absolute or parent-traversal member.'
}

foreach ($required in @(
    'deploy.sh', 'VERSION', 'README.txt', 'payload/RootStart.tar', 'payload/NonRootStart.tar',
    'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_AVAILABILITY.md',
    'LICENSES/Apache-2.0.txt', 'LICENSES/GPL-3.0.txt',
    'apps/termux-api.apk', 'apps/lsa-x11.apk', 'apps/README.md',
    'bootstrap/architecture-normalize.sh', 'bootstrap/rootstart_pty.py',
    'bootstrap/wireless/lsa-nl80211-arm64', 'bootstrap/wireless/lsa-nl80211-armv7',
    'bootstrap/mountns/lsa-mountns-arm64', 'bootstrap/mountns/lsa-mountns-armv7', 'bootstrap/mountns/lsa-mountns-x86', 'bootstrap/mountns/lsa-mountns-x86_64',
    'manifest/PAYLOAD-SHA256SUMS', 'manifest/APPS.tsv', 'manifest/SOURCE_PATHS.txt',
    'manifest/TREE.txt', 'manifest/build-info.txt', 'manifest/termux-packages.txt',
    'manifest/debian-packages.txt', 'manifest/OWNERSHIP.tsv', 'manifest/SOURCES.tsv',
    'manifest/LSA-X11-BUILD.tsv',
    "sources/$lsaX11SourceArchiveName"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $stageRoot $required.Replace('/', '\')))) {
        throw "Release layout verification failed: $required"
    }
}

 $publishByMirror = $false
if (Test-Path -LiteralPath $releaseRoot) {
    # Preserve even an empty prior output.  Release construction must never
    # destroy the only prior package copy merely to make a destination name
    # available.  Windows indexers and file-preview clients can retain a read
    # handle on a release file, making a directory rename unavailable even
    # though a normal file-level update is safe.  In that case copy the prior
    # release to the required tmp backup first, then mirror the fully-validated
    # stage into the canonical package directory and retain the stage as build
    # evidence.  This avoids a destructive delete/recreate fallback.
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    try {
        Move-Item -LiteralPath $releaseRoot -Destination (Join-Path $backupRoot 'LSADeploy') -ErrorAction Stop
    } catch {
        Copy-Item -LiteralPath $releaseRoot -Destination (Join-Path $backupRoot 'LSADeploy') -Recurse -Force -ErrorAction Stop
        $publishByMirror = $true
        Write-Warning 'LSADeploy was in use; preserved a copied backup and will publish the validated stage with robocopy.'
    }
}
if ($publishByMirror) {
    & robocopy $stageRoot $releaseRoot /MIR /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Validated release publish failed with robocopy exit code $LASTEXITCODE"
    }
} else {
    Move-Item -LiteralPath $stageRoot -Destination $releaseRoot
}

Write-Output "LSA deployment package built: $releaseRoot"
Write-Output "Build evidence retained: $buildRoot"
Write-Output "Prior release preserved when present: $backupRoot"
