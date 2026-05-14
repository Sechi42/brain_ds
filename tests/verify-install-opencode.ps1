$ErrorActionPreference = 'Stop'

function Assert-True {
  param(
    [bool]$Condition,
    [string]$Message
  )
  if (-not $Condition) {
    throw "ASSERT FAILED: $Message"
  }
}

function Assert-Equal {
  param(
    $Expected,
    $Actual,
    [string]$Message
  )
  if ($Expected -ne $Actual) {
    throw "ASSERT FAILED: $Message`nExpected: $Expected`nActual:   $Actual"
  }
}

function New-SeedProject {
  param([string]$Root)

  New-Item -ItemType Directory -Path (Join-Path $Root 'skills/elicit-context') -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $Root 'skills/map-connections') -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $Root 'skills/generate-brd') -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $Root 'skills/elicit-context/SKILL.md') -Value '# elicit'
  Set-Content -LiteralPath (Join-Path $Root 'skills/map-connections/SKILL.md') -Value '# map'
  Set-Content -LiteralPath (Join-Path $Root 'skills/generate-brd/SKILL.md') -Value '# brd'

  New-Item -ItemType Directory -Path (Join-Path $Root '.atl') -Force | Out-Null
  @"
# Skill Registry

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| local trigger | elicit-context | C:\stale\brain_ds\skills\elicit-context\SKILL.md |
| local trigger | map-connections | C:\stale\brain_ds\skills\map-connections\SKILL.md |
| local trigger | generate-brd | C:\stale\brain_ds\skills\generate-brd\SKILL.md |
| external trigger | go-testing | C:\test-user\.config\opencode\skills\go-testing\SKILL.md |

## Compact Rules

keep this exact line
"@ | Set-Content -LiteralPath (Join-Path $Root '.atl/skill-registry.md')
}

function New-Stubs {
  param(
    [string]$BinDir,
    [bool]$WithOpenCode,
    [bool]$WithGit
  )

  New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
  if ($WithOpenCode) {
    "@echo off`r`nexit /b 0" | Set-Content -LiteralPath (Join-Path $BinDir 'opencode.cmd')
  }
  if ($WithGit) {
    "@echo off`r`nexit /b 0" | Set-Content -LiteralPath (Join-Path $BinDir 'git.cmd')
  }
}

function Invoke-Installer {
  param(
    [string]$ProjectRoot,
    [string]$BinDir,
    [string]$HomeDir,
    [string[]]$Args = @()
  )

  $installer = Join-Path $ProjectRoot 'install-opencode.ps1'
  $psPath = "${env:WINDIR}\System32\WindowsPowerShell\v1.0\powershell.exe"
  $originalPath = $env:PATH
  $originalHome = $env:HOME
  $originalUserProfile = $env:USERPROFILE
  try {
    $env:PATH = $BinDir
    $env:HOME = $HomeDir
    $env:USERPROFILE = $HomeDir
    $output = & $psPath -NoProfile -ExecutionPolicy Bypass -File $installer @Args 2>&1
    $exitCode = $LASTEXITCODE
    return [PSCustomObject]@{ ExitCode = $exitCode; Output = ($output -join "`n") }
  } finally {
    $env:PATH = $originalPath
    $env:HOME = $originalHome
    $env:USERPROFILE = $originalUserProfile
  }
}

function Get-TestRoot {
  $base = Join-Path $env:TEMP ("brain_ds-installer-tests-" + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $base -Force | Out-Null
  return $base
}

function Initialize-ProjectWorkspace {
  param([string]$Base)
  $project = Join-Path $Base 'repo'
  New-Item -ItemType Directory -Path $project -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../install-opencode.ps1') -Destination (Join-Path $project 'install-opencode.ps1') -Force
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../commands') -Destination (Join-Path $project 'commands') -Recurse -Force
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../prompts') -Destination (Join-Path $project 'prompts') -Recurse -Force
  New-SeedProject -Root $project
  return $project
}

function Test-AgentContract {
  $installerSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../install-opencode.ps1') -Raw
  Assert-True ($installerSource.Contains("description = 'Enterprise Data & Knowledge Mapper Orchestrator.'")) 'Agent description should be defined'
  Assert-True ($installerSource.Contains('prompt = "{file:$PromptFilePath}"')) 'Agent prompt should use {file:$PromptFilePath}'
  Assert-True ($installerSource.Contains("read = 'allow'")) 'permission.read should be allow'
  Assert-True ($installerSource.Contains("edit = 'allow'")) 'permission.edit should be allow'
}

function Test-OpenCode-Missing {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$false -WithGit:$true

    $result = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath
    Assert-Equal 1 $result.ExitCode 'Missing OpenCode should exit 1'
    Assert-True ($result.Output -match 'OpenCode CLI not found') 'Should print OpenCode missing message'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $project '.opencode'))) 'Should not create .opencode when OpenCode is missing'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Test-Git-Missing {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$true -WithGit:$false

    $result = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath
    Assert-Equal 2 $result.ExitCode 'Missing Git should exit 2'
    Assert-True ($result.Output -match 'Git not found') 'Should print Git missing message'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $project '.opencode'))) 'Should not create .opencode when Git is missing'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Test-Engram-Warn-And-Idempotent {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$true -WithGit:$true

    $first = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath
    Assert-Equal 0 $first.ExitCode 'Installer should succeed when prerequisites are present'
    Assert-True ((Test-Path -LiteralPath (Join-Path $project '.opencode/skills/elicit-context/SKILL.md'))) 'Bridge for elicit-context should exist'
    Assert-True ((Test-Path -LiteralPath (Join-Path $project '.opencode/skills/map-connections/SKILL.md'))) 'Bridge for map-connections should exist'
    Assert-True ((Test-Path -LiteralPath (Join-Path $project '.opencode/skills/generate-brd/SKILL.md'))) 'Bridge for generate-brd should exist'

    $bridgeItem = Get-Item -LiteralPath (Join-Path $project '.opencode/skills/elicit-context/SKILL.md') -Force
    if ($bridgeItem.LinkType -eq 'SymbolicLink') {
      Assert-Equal '../../../skills/elicit-context/SKILL.md' $bridgeItem.Target 'Symlink target must use portable relative path'
    } else {
      Assert-True ($first.Output -match 'Symlink failed for elicit-context') 'Copy fallback should emit warning when symlink creation fails'
    }

    $registry = Get-Content -LiteralPath (Join-Path $project '.atl/skill-registry.md') -Raw
    Assert-True ($registry -match [regex]::Escape("| local trigger | elicit-context | $project\skills\elicit-context\SKILL.md |")) 'Registry path for elicit-context should be rewritten to this clone path'
    Assert-True ($registry -match [regex]::Escape('| external trigger | go-testing | C:\test-user\.config\opencode\skills\go-testing\SKILL.md |')) 'External skill row should remain unchanged'
    Assert-True ($registry -match 'keep this exact line') 'Compact Rules section must be preserved'

    $second = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath
    Assert-Equal 0 $second.ExitCode 'Second installer run should remain successful'
    Assert-True ((Test-Path -LiteralPath (Join-Path $project '.opencode/skills/elicit-context/SKILL.md'))) 'Bridge should remain after rerun'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Test-Engram-Warn-Path-Static {
  $installerSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../install-opencode.ps1') -Raw
  Assert-True ($installerSource -match 'Warning: Engram not detected') 'Installer must include Engram warning message'
  Assert-True ($installerSource -match 'if \(-not \$engramDetected\)') 'Installer must gate warning behind Engram detection check'
}

function Test-GlobalFlagCreatesGlobalSymlink {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$true -WithGit:$true

    $result = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath -Args @('-Global')
    Assert-Equal 0 $result.ExitCode 'Global flag should succeed'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Test-ProjectFlagPreservesCurrentBehavior {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$true -WithGit:$true

    $result = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath -Args @('-Project')
    Assert-Equal 0 $result.ExitCode 'Project flag should succeed'
    Assert-True (Test-Path -LiteralPath (Join-Path $project '.opencode/skills/elicit-context/SKILL.md')) 'Project mode should create local bridge'
    $registry = Get-Content -LiteralPath (Join-Path $project '.atl/skill-registry.md') -Raw
    Assert-True ($registry -match [regex]::Escape("| local trigger | elicit-context | $project\skills\elicit-context\SKILL.md |")) 'Project mode should rewrite local registry path'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Test-GlobalModePrintsRestartInstruction {
  $base = Get-TestRoot
  try {
    $project = Initialize-ProjectWorkspace -Base $base
    $bin = Join-Path $base 'bin'
    $homeDirPath = Join-Path $base 'home'
    New-Item -ItemType Directory -Path $homeDirPath -Force | Out-Null
    New-Stubs -BinDir $bin -WithOpenCode:$true -WithGit:$true

    $result = Invoke-Installer -ProjectRoot $project -BinDir $bin -HomeDir $homeDirPath -Args @('-Global')
    Assert-Equal 0 $result.ExitCode 'Global flag should succeed'
  } finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Test-OpenCode-Missing
Test-Git-Missing
Test-Engram-Warn-And-Idempotent
Test-Engram-Warn-Path-Static
Test-GlobalFlagCreatesGlobalSymlink
Test-ProjectFlagPreservesCurrentBehavior
Test-GlobalModePrintsRestartInstruction
Test-AgentContract

"PASS: install-opencode.ps1 verification harness completed"
