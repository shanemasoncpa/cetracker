# CE Tracker - Multi-Agent Launcher
# Run this script to open 4 Claude Code terminals with specialized roles
# Usage: Right-click > Run with PowerShell, or run: powershell -File start-agents.ps1

$projectDir = $PSScriptRoot

Write-Host "Starting CE Tracker Multi-Agent Development Environment..." -ForegroundColor Cyan
Write-Host "Project: $projectDir" -ForegroundColor Gray
Write-Host ""

# Terminal 1: Manager Agent
Start-Process wt -ArgumentList "new-tab --title `"Manager Agent`" --startingDirectory `"$projectDir`" cmd /k `"echo MANAGER AGENT - Read CLAUDE.md for instructions && claude`""

Start-Sleep -Milliseconds 500

# Terminal 2: Backend Agent
Start-Process wt -ArgumentList "new-tab --title `"Backend Agent`" --startingDirectory `"$projectDir`" cmd /k `"echo BACKEND AGENT - Read CLAUDE.md for instructions && claude`""

Start-Sleep -Milliseconds 500

# Terminal 3: Frontend Agent
Start-Process wt -ArgumentList "new-tab --title `"Frontend Agent`" --startingDirectory `"$projectDir`" cmd /k `"echo FRONTEND AGENT - Read CLAUDE.md for instructions && claude`""

Start-Sleep -Milliseconds 500

# Terminal 4: QA Agent
Start-Process wt -ArgumentList "new-tab --title `"QA Agent`" --startingDirectory `"$projectDir`" cmd /k `"echo QA AGENT - Read CLAUDE.md for instructions && claude`""

Write-Host ""
Write-Host "All 4 agent terminals launched!" -ForegroundColor Green
Write-Host "Paste the role prompt from CLAUDE.md into each terminal to assign roles." -ForegroundColor Yellow
