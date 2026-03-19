param(
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"

$titles = @(
    "OpenAgents-Network",
    "Agent-travel_router",
    "Agent-weather_agent",
    "Agent-spot_agent",
    "Agent-plan_agent"
)

$patterns = @(
    "openagents.cli",
    "travel_router.yaml",
    "weather_agent.yaml",
    "spot_agent.yaml",
    "plan_agent.yaml",
    "mcp_server.py",
    "memory_mcp.py"
)

function Write-Log {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

Write-Log "Stopping OpenAgents windows..."
foreach ($title in $titles) {
    & taskkill /FI "WINDOWTITLE eq $title*" /T /F | Out-Null
}

Start-Sleep -Milliseconds 800

Write-Log "Scanning for orphaned OpenAgents Python processes..."
$currentPid = $PID
$targets = Get-CimInstance Win32_Process | Where-Object {
    if (-not $_.CommandLine) { return $false }
    if ($_.ProcessId -eq $currentPid) { return $false }

    $cmd = $_.CommandLine.ToLowerInvariant()
    if ($cmd.Contains("stop_openagents.ps1") -or $cmd.Contains("stop_all.bat")) {
        return $false
    }

    $hasOpenAgents = $cmd.Contains("openagents.cli")
    $hasProjectTarget = $patterns | Where-Object { $cmd.Contains($_.ToLowerInvariant()) }

    return ($hasOpenAgents -and $hasProjectTarget) -or $cmd.Contains("mcp_server.py") -or $cmd.Contains("memory_mcp.py")
}

foreach ($proc in $targets) {
    Write-Log ("Stopping PID {0}: {1}" -f $proc.ProcessId, $proc.CommandLine)
    Stop-Process -Id $proc.ProcessId -Force
}

Start-Sleep -Milliseconds 800

Write-Log "OpenAgents stop sequence finished."
