[CmdletBinding()]
param(
  [switch]$Global,
  [switch]$Project,
  [switch]$Agent,
  [switch]$RegisterPath
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillsDir = Join-Path $RootDir 'skills'
$GlobalBridgeRoot = Join-Path $HOME '.config/opencode/skills'
$ProjectBridgeRoot = Join-Path $RootDir '.opencode/skills'
$RegistryPath = Join-Path $RootDir '.atl/skill-registry.md'
$AgentsPath = Join-Path $RootDir 'AGENTS.md'
$CommandsSourceDir = Join-Path $RootDir 'commands'
$GlobalCommandsRoot = Join-Path $HOME '.config/opencode/commands'
$PromptFilePath = Join-Path $RootDir 'prompts/brain-ds-orchestrator.md'
$GlobalBinRoot = Join-Path $HOME '.config/opencode/bin'

function Insert-BrainDsAgent {
  param([string]$ConfigPath)

  New-Item -ItemType Directory -Path (Split-Path -Parent $ConfigPath) -Force | Out-Null

  if (Test-Path -LiteralPath $ConfigPath) {
    $raw = Get-Content -LiteralPath $ConfigPath -Raw
    $cfg = if ([string]::IsNullOrWhiteSpace($raw)) { [pscustomobject]@{} } else { $raw | ConvertFrom-Json }
  } else {
    $cfg = [pscustomobject]@{}
  }

  if (-not ($cfg.PSObject.Properties.Name -contains 'agent')) {
    $cfg | Add-Member -NotePropertyName 'agent' -NotePropertyValue ([pscustomobject]@{})
  }

  $subagentNames = @('brainds-source-explorer', 'brainds-graph-mapper', 'brainds-connection-mapper', 'brainds-brd-writer')

  $taskPermission = [ordered]@{ '*' = 'deny' }
  foreach ($name in $subagentNames) { $taskPermission[$name] = 'allow' }

  $desired = [pscustomobject]@{
    mode = 'primary'
    model = 'opencode-go/deepseek-v4-flash'
    description = 'Enterprise Data & Knowledge Mapper Orchestrator.'
    prompt = "{file:$PromptFilePath}"
    tools = [pscustomobject]@{
      bash = $true
      read = $true
      write = $true
      engram = $true
      task = $true
    }
    permission = [pscustomobject]@{
      bash = [pscustomobject]@{
        '*git*' = 'allow'
      }
      read = 'allow'
      edit = 'allow'
      task = [pscustomobject]$taskPermission
    }
  }

  $existing = $cfg.agent.'brain-ds-orchestrator'
  if ($null -eq $existing) {
    $cfg.agent | Add-Member -NotePropertyName 'brain-ds-orchestrator' -NotePropertyValue $desired
    $state = 'inserted'
  } else {
    $cfg.agent.'brain-ds-orchestrator' = $desired
    $state = 'already exists - updated'
  }

  foreach ($name in $subagentNames) {
    $subPromptPath = Join-Path $RootDir "prompts/$name.md"
    $subDesired = [pscustomobject]@{
      mode = 'subagent'
      hidden = $true
      model = 'opencode-go/deepseek-v4-flash'
      description = "brain_ds executor sub-agent: $name."
      prompt = "{file:$subPromptPath}"
      tools = [pscustomobject]@{
        read = $true
        write = $true
        engram = $true
      }
      permission = [pscustomobject]@{
        read = 'allow'
        edit = 'allow'
      }
    }
    if ($null -eq $cfg.agent.$name) {
      $cfg.agent | Add-Member -NotePropertyName $name -NotePropertyValue $subDesired
    } else {
      $cfg.agent.$name = $subDesired
    }
  }

  ($cfg | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
  return $state
}

function Deploy-BrainDsCommands {
  param([string]$DestinationRoot)

  New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
  $templates = @('brain-ds-pipeline.md', 'brain-ds-map.md', 'brain-ds-brd.md', 'elicit-context.md', 'map-connections.md', 'generate-brd.md')
  foreach ($name in $templates) {
    $source = Join-Path $CommandsSourceDir $name
    if (-not (Test-Path -LiteralPath $source)) {
      throw "Command template not found: $source"
    }
    $dest = Join-Path $DestinationRoot $name
    Copy-Item -LiteralPath $source -Destination $dest -Force
  }
  return $templates.Count
}

function Sync-BrainDsMcpToGlobal {
  <#
    Merge the brain_ds MCP server entry into the user's global OpenCode config
    (~/.config/opencode/opencode.json) using the same payload the project-mode
    `apply_setup` writes. Always creates a timestamped backup before mutating,
    and never touches other MCP servers that the user already has configured.
  #>
  param([string]$ConfigPath, [string]$RepoRoot)

  New-Item -ItemType Directory -Path (Split-Path -Parent $ConfigPath) -Force | Out-Null

  if (Test-Path -LiteralPath $ConfigPath) {
    $raw = Get-Content -LiteralPath $ConfigPath -Raw
    $cfg = if ([string]::IsNullOrWhiteSpace($raw)) { [pscustomobject]@{} } else { $raw | ConvertFrom-Json }
  } else {
    $cfg = [pscustomobject]@{}
  }

  # Backup the entire global config (small file, cheap insurance).
  $backup = "{0}.{1}.bak" -f $ConfigPath, (Get-Date -Format "yyyyMMddTHHmmssZ")
  if (Test-Path -LiteralPath $ConfigPath) {
    Copy-Item -LiteralPath $ConfigPath -Destination $backup -Force
  }

  # Resolve the local brain_ds.cmd wrapper inside the repo so the global
  # config points at the same MCP the project's .opencode/opencode.json uses.
  $cmd = Join-Path $RepoRoot 'brain_ds.cmd'
  if (-not (Test-Path -LiteralPath $cmd)) {
    throw "Local brain_ds wrapper not found: $cmd. Run 'uv sync' first."
  }

  if (-not ($cfg.PSObject.Properties.Name -contains 'mcp')) {
    $cfg | Add-Member -NotePropertyName 'mcp' -NotePropertyValue ([pscustomobject]@{})
  }
  if ($null -eq $cfg.mcp) { $cfg.mcp = [pscustomobject]@{} }

  # No pinned --project-root and no BRAIN_DS_PROJECT_ROOT: the server resolves
  # its root from the session cwd, so each OpenCode session gets the store of
  # the folder it was opened in (workspace scoping fix).
  $cfg.mcp | Add-Member -NotePropertyName 'brain_ds' -NotePropertyValue ([pscustomobject]@{
      type = 'local'
      enabled = $true
      command = @($cmd, 'mcp')
    }) -Force

  ($cfg | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
  return $backup
}

if ($Global -and $Project) {
  "Choose only one scope: --global or --project"
  exit 3
}

function Resolve-InstallMode {
  if ($Global) { return 'global' }
  if ($Project) { return 'project' }

  $isInteractive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
  if (-not $isInteractive) { return 'project' }

  $choice = Read-Host 'Install globally [G] or only for this project [P]? (default: P)'
  if ($choice -match '^[Gg]$') { return 'global' }
  return 'project'
}

$InstallMode = Resolve-InstallMode
$BridgeRoot = if ($InstallMode -eq 'global') { $GlobalBridgeRoot } else { $ProjectBridgeRoot }

function Test-CommandExists([string]$Name) {
  return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-CommandExists 'opencode')) {
  "OpenCode CLI not found. Install: https://opencode.ai/docs"
  exit 1
}

if (-not (Test-CommandExists 'git')) {
  "Git not found. Install: https://git-scm.com/downloads"
  exit 2
}

$engramDetected = $false
$opencodeConfig = Join-Path $HOME '.config/opencode/opencode.json'
if (Test-Path -LiteralPath $opencodeConfig) {
  $cfg = Get-Content -LiteralPath $opencodeConfig -Raw -ErrorAction SilentlyContinue
  if ($cfg -match 'engram') { $engramDetected = $true }
}

$skillFiles = Get-ChildItem -LiteralPath $SkillsDir -Filter 'SKILL.md' -Recurse -File | Sort-Object FullName
$skillNames = @($skillFiles | ForEach-Object { $_.Directory.Name })

New-Item -ItemType Directory -Path $BridgeRoot -Force | Out-Null

if ($InstallMode -eq 'project') {
  $existingDirs = Get-ChildItem -LiteralPath $BridgeRoot -Directory -ErrorAction SilentlyContinue
  foreach ($dir in $existingDirs) {
    $canonical = Join-Path $SkillsDir (Join-Path $dir.Name 'SKILL.md')
    if (-not (Test-Path -LiteralPath $canonical)) {
      Remove-Item -LiteralPath $dir.FullName -Recurse -Force
    }
  }
}

$symlinked = New-Object System.Collections.Generic.List[string]
$copied = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

foreach ($name in $skillNames) {
  $source = Join-Path $SkillsDir (Join-Path $name 'SKILL.md')
  $destDir = Join-Path $BridgeRoot $name
  $destFile = Join-Path $destDir 'SKILL.md'
  New-Item -ItemType Directory -Path $destDir -Force | Out-Null

  if (Test-Path -LiteralPath $destFile) {
    Remove-Item -LiteralPath $destFile -Force
  }

  $relativeTarget = "../../../skills/$name/SKILL.md"
  $targetPath = if ($InstallMode -eq 'global') { $source } else { $relativeTarget }
  try {
    New-Item -ItemType SymbolicLink -Path $destFile -Target $targetPath -Force | Out-Null
    $symlinked.Add($name)
  } catch {
    Copy-Item -LiteralPath $source -Destination $destFile -Force
    $copied.Add($name)
    $warnings.Add("Symlink failed for $name. Copied file instead. Re-run installer after editing source skills.")
  }
}

$registryStatus = 'skipped (global mode)'
if ($InstallMode -eq 'project' -and (Test-Path -LiteralPath $RegistryPath)) {
  $lines = Get-Content -LiteralPath $RegistryPath
  $updated = New-Object System.Collections.Generic.List[string]
  $inUserSkills = $false
  $changed = $false

  foreach ($line in $lines) {
    $newLine = $line
    if ($line -eq '## User Skills') {
      $inUserSkills = $true
    } elseif ($inUserSkills -and $line -match '^##\s+') {
      $inUserSkills = $false
    }

    if ($inUserSkills -and $line -match '^\|.*\|.*\|.*\|$' -and $line -notmatch '^\|[-\s]+\|[-\s]+\|[-\s]+\|$') {
      $parts = $line.Split('|')
      if ($parts.Length -ge 5) {
        $trigger = $parts[1].Trim()
        $skill = $parts[2].Trim()
        $pathCell = $parts[3].Trim()
        $projectSkill = Test-Path -LiteralPath (Join-Path $SkillsDir (Join-Path $skill 'SKILL.md'))
        if ($projectSkill) {
          $relativePath = "skills\$skill\SKILL.md"
          $newLine = "| $trigger | $skill | $relativePath |"
          if ($newLine -ne $line) { $changed = $true }
        }
      }
    }
    $updated.Add($newLine)
  }

  if ($changed) {
    Set-Content -LiteralPath $RegistryPath -Value $updated -NoNewline:$false
    $registryStatus = 'updated for this machine'
  }
}

$agentsStatus = 'skipped (global mode)'
if ($InstallMode -eq 'project') {
  $agentsStatus = 'already exists - skipping'
}

$agentStatus = 'skipped'
$commandStatus = 'skipped'
$mcpStatus = 'skipped'
if ($Agent) {
  $agentStatus = Insert-BrainDsAgent -ConfigPath $opencodeConfig
  $count = Deploy-BrainDsCommands -DestinationRoot $GlobalCommandsRoot
  $commandStatus = "deployed ($count files)"
  $backup = Sync-BrainDsMcpToGlobal -ConfigPath $opencodeConfig -RepoRoot $RootDir
  $mcpStatus = "synced (backup: $backup)"
}
if ($InstallMode -eq 'project' -and -not (Test-Path -LiteralPath $AgentsPath)) {
@"
# AGENTS.md

Project: **brain_ds** - Enterprise Data & Knowledge Mapper.

## Quick Commands

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture missing organizational context |
| `/map-connections` | Build cross-entity knowledge maps |
| `/generate-brd` | Generate a BRD from mapped knowledge |

See `.atl/skill-registry.md` for compact rules and trigger resolution.

After running the installer, OpenCode auto-discovers project skills through `.opencode/skills/`.
"@ | Set-Content -LiteralPath $AgentsPath
  $agentsStatus = 'created'
}

""
"Skills activated: $($skillNames.Count)"
foreach ($n in $symlinked) { "- $n (symlink)" }
foreach ($n in $copied) { "- $n (copy)" }
"Registry: $registryStatus"
"AGENTS.md: $agentsStatus"
if ($InstallMode -eq 'global') {
  "Global mode: restart OpenCode to load newly installed skills"
}
if ($Agent) {
  "brain_ds agent: $agentStatus"
  "brain_ds commands: $commandStatus"
  "brain_ds mcp: $mcpStatus"
}
if (-not $engramDetected) {
  "Warning: Engram not detected. Install: https://github.com/engram-labs/engram-opencode"
}
foreach ($w in $warnings) { "Warning: $w" }

if ($RegisterPath) {
  New-Item -ItemType Directory -Path $GlobalBinRoot -Force | Out-Null
  $globalCmdWrapper = Join-Path $GlobalBinRoot 'brain_ds.cmd'
  @"
@echo off
setlocal

where uv >nul 2>nul
if errorlevel 1 (
  echo Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/ 1>&2
  exit /b 1
)

uv run --project "$RootDir" brain_ds %*
exit /b %ERRORLEVEL%
"@ | Set-Content -LiteralPath $globalCmdWrapper -Encoding ASCII
  "PATH registration: wrote brain_ds.cmd to $GlobalBinRoot"
  "PATH registration: add this directory to PATH if missing: $GlobalBinRoot"
}

if (Test-CommandExists 'uv') {
  "Python deps: running uv sync"
  try {
    & uv sync --project $RootDir
    "Python deps: uv sync completed"
  } catch {
    "Warning: uv sync failed. Run manually in repo root: uv sync"
  }
} else {
  "Warning: uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
}

"Next steps: Run /elicit-context, /map-connections, or /generate-brd in OpenCode"

exit 0
