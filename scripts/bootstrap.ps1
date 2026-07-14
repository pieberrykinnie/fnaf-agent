# One-time project bootstrap. Run from repo root: .\scripts\bootstrap.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

# Claude Code project settings (pre-approved permissions)
New-Item -ItemType Directory -Force -Path ".claude" | Out-Null
Copy-Item "scripts\claude-settings.json" ".claude\settings.json" -Force

# Working directories
foreach ($d in "runs", "assets\templates", "tests\fixtures\live") {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
New-Item -ItemType File -Force -Path "tests\fixtures\live\.gitkeep" | Out-Null

# Python env
uv sync --group dev

# Git
if (-not (Test-Path ".git")) {
    git init
    git add -A
    git commit -m "chore: bootstrap fnaf-agent scaffold"
}

uv run pytest
Write-Host "`nBootstrap complete. Next: launch the game once, then 'uv run python scripts/capture_probe.py' (see BACKLOG.md Phase 0)."
