<#
Build the Tram Distribution Office plugin and install the mod as a local development item.

    .\build.ps1                 # compile mod\plugins\* into build\
    .\build.ps1 -Install        # compile, then deploy into the game's media_soviet\workshop_wip
    .\build.ps1 -Clean
    .\build.ps1 -Game 'D:\Games\SovietRepublic' -Install

The game folder defaults to the Steam library path; -Game or the WRSR_GAME
environment variable override it.

Deliberately does NOT go through vcvars64.bat: some Build Tools copies fail in
it when %ProgramFiles(x86)% is missing from the environment (any shell started
from Git Bash). INCLUDE and LIB are set directly instead, which makes the build
work from any shell.
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Clean,
    [string]$Game = $(if ($env:WRSR_GAME) { $env:WRSR_GAME } else { 'C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic' })
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# ---------------------------------------------------------------- toolchain --

function Find-Toolchain {
    $vsRoots = @(
        "${env:SystemDrive}\Program Files (x86)\Microsoft Visual Studio",
        "${env:SystemDrive}\Program Files\Microsoft Visual Studio"
    )
    $msvc = $null
    foreach ($r in $vsRoots) {
        if (-not (Test-Path $r)) { continue }
        $cand = Get-ChildItem -Path $r -Recurse -Depth 4 -Directory -Filter 'MSVC' -ErrorAction SilentlyContinue |
                ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue } |
                Where-Object { Test-Path (Join-Path $_.FullName 'bin\Hostx64\x64\cl.exe') } |
                Sort-Object Name -Descending
        if ($cand) { $msvc = $cand[0].FullName; break }
    }
    if (-not $msvc) { throw "No MSVC x64 toolset found. Install the 'Desktop development with C++' workload." }

    $sdkRoot = "${env:SystemDrive}\Program Files (x86)\Windows Kits\10"
    if (-not (Test-Path "$sdkRoot\Include")) { throw "Windows 10/11 SDK not found at $sdkRoot" }
    $sdkVer = (Get-ChildItem "$sdkRoot\Include" -Directory |
               Where-Object { Test-Path "$($_.FullName)\um\windows.h" } |
               Sort-Object Name -Descending)[0].Name
    if (-not $sdkVer) { throw "No usable Windows SDK version under $sdkRoot\Include" }

    [pscustomobject]@{ Msvc = $msvc; SdkRoot = $sdkRoot; SdkVer = $sdkVer }
}

$outDir = Join-Path $root 'build'
if ($Clean) {
    if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force }
    Write-Host '[build] cleaned'
    return
}

$tc = Find-Toolchain
$cl = Join-Path $tc.Msvc 'bin\Hostx64\x64\cl.exe'
$env:INCLUDE = @(
    (Join-Path $tc.Msvc 'include')
    "$($tc.SdkRoot)\Include\$($tc.SdkVer)\ucrt"
    "$($tc.SdkRoot)\Include\$($tc.SdkVer)\um"
    "$($tc.SdkRoot)\Include\$($tc.SdkVer)\shared"
) -join ';'
$env:LIB = @(
    (Join-Path $tc.Msvc 'lib\x64')
    "$($tc.SdkRoot)\Lib\$($tc.SdkVer)\ucrt\x64"
    "$($tc.SdkRoot)\Lib\$($tc.SdkVer)\um\x64"
) -join ';'
Write-Host "[build] MSVC $(Split-Path $tc.Msvc -Leaf)  SDK $($tc.SdkVer)" -ForegroundColor DarkGray

# ------------------------------------------------------------------ plugins --

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$plugins = Get-ChildItem (Join-Path $root 'mod\plugins') -Directory |
           Where-Object { Get-ChildItem $_.FullName -Filter *.cpp -ErrorAction SilentlyContinue }
if (-not $plugins) { throw 'No plugin sources found under mod\plugins' }

$failed = @()
foreach ($p in $plugins) {
    $name = $p.Name
    $src  = (Get-ChildItem $p.FullName -Filter *.cpp | ForEach-Object { $_.FullName })
    $obj  = Join-Path $outDir "$name\"
    New-Item -ItemType Directory -Force -Path $obj | Out-Null
    Write-Host "[build] $name.dll"
    # /MT: each plugin carries its own CRT - the loader API forbids passing allocations across it
    $clArgs = @('/nologo', '/O2', '/MT', '/W3', '/EHsc', '/LD', "/Fo$obj", "/Fd$obj",
                "/Fe$(Join-Path $outDir "$name.dll")", $src, '/link', 'kernel32.lib', 'user32.lib')
    & $cl @clArgs 2>&1 | ForEach-Object {
        if ($_ -match 'error|warning') { Write-Host "        $_" } else { Write-Verbose "$_" }
    }
    if ($LASTEXITCODE -ne 0) { $failed += $name }
}
if ($failed) { throw "FAILED: $($failed -join ', ')" }
Write-Host "[build] ok -> $outDir" -ForegroundColor Green

# ------------------------------------------------------------------ install --
#
# Unpublished workshop items live in <game>\media_soviet\workshop_wip\<numeric id>
# (the id is each item's workshopconfig.ini $ITEM_ID). Republic Mod Loader lists
# them as development items; enable them there. The plugin ships inside the
# item (mod\packages\tram_do): every plugin whose package.txt names it
# goes into <item>\plugins with its ini, rml.json and data folder (as <name>_data),
# so the loader switches them together with that item.
if ($Install) {
    $busy = Get-Process RepublicModLoader, SOVIET64 -ErrorAction SilentlyContinue
    if ($busy) { throw ('close these before installing: ' + (($busy | ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }) -join ', ')) }
    $wip = Join-Path $Game 'media_soviet\workshop_wip'
    if (-not (Test-Path (Split-Path $wip))) { throw "Game not found at $Game (use -Game or WRSR_GAME)" }
    New-Item -ItemType Directory -Force -Path $wip | Out-Null

    foreach ($kind in @('buildings', 'vehicles', 'packages')) {
        $bsrc = Join-Path $root "mod\$kind"
        if (-not (Test-Path $bsrc)) { continue }
        foreach ($b in Get-ChildItem $bsrc -Directory) {
            $cfg = Join-Path $b.FullName 'workshopconfig.ini'
            if (-not (Test-Path $cfg)) { continue }
            $id = (Select-String -Path $cfg -Pattern '^\$ITEM_ID\s+(\d+)').Matches[0].Groups[1].Value
            if (-not $id -or $id -eq '0') { Write-Warning "skipping $($b.Name): no numeric ITEM_ID"; continue }
            $to = Join-Path $wip $id
            $stage = "$to.new"                       # stage, then swap: a failed copy never leaves half an item
            if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
            Copy-Item $b.FullName $stage -Recurse -Force
            if ($kind -eq 'packages') {
                $pdir = Join-Path $stage 'plugins'
                New-Item -ItemType Directory -Force -Path $pdir | Out-Null
                foreach ($p in $plugins) {
                    $pt = Join-Path $p.FullName 'package.txt'
                    if (-not (Test-Path $pt) -or (Get-Content $pt -TotalCount 1).Trim() -ne $b.Name) { continue }
                    $pn = $p.Name
                    Copy-Item (Join-Path $outDir "$pn.dll") $pdir -Force
                    foreach ($f in @("$pn.ini", "$pn.rml.json")) {
                        $src = Join-Path $p.FullName $f
                        if (Test-Path $src) { Copy-Item $src $pdir -Force }
                    }
                    $data = Join-Path $p.FullName 'data'
                    if (Test-Path $data) { Copy-Item $data (Join-Path $pdir "$($pn)_data") -Recurse -Force }
                    Write-Host "[build] package $($b.Name): $pn" -ForegroundColor DarkGray
                }
            }
            try {
                if (Test-Path $to) { Remove-Item $to -Recurse -Force -ErrorAction Stop }
            } catch {
                Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
                throw "Cannot replace $to (a file there is locked). Close the loader and the game, then re-run."
            }
            Move-Item $stage $to
            Write-Host "[build] $kind $($b.Name) -> workshop_wip\$id" -ForegroundColor Green
        }
    }
    Write-Host '[build] open Republic Mod Loader, enable the development item 9000310 and its tramdo plugin, then launch.'
}
