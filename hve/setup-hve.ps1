[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$WithWorkIQ,
    [switch]$InstallExternalCopilotCli,
    [switch]$ForceRecreateVenv
)

$ErrorActionPreference = "Stop"
$script:WarningCount = 0
$script:GhAuthOk = $false

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message"
}

function Write-SetupWarning {
    param([string]$Message)
    $script:WarningCount++
    Write-Warning $Message
}

function Resolve-PreferredCommand {
    param(
        [string]$Name,
        [string[]]$PreferredNames = @()
    )
    foreach ($candidate in $PreferredNames) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    $fallback = Get-Command $Name -ErrorAction SilentlyContinue
    if ($fallback) { return $fallback.Source }
    return $null
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host ("> {0} {1}" -f $FilePath, ($Arguments -join " "))
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Probe {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Get-PythonInfo {
    param(
        [string]$Exe,
        [string[]]$Args = @(),
        [string]$Label = $Exe
    )
    $pythonCode = "import sys; print(sys.executable); print(f'{sys.version_info.major} {sys.version_info.minor} {sys.version_info.micro}')"
    try {
        $output = & $Exe @Args -c $pythonCode 2>$null
        if ($LASTEXITCODE -ne 0 -or $output.Count -lt 2) { return $null }
        $versionParts = ($output[1] -split " ") | ForEach-Object { [int]$_ }
        return [pscustomobject]@{
            Exe = $Exe
            Args = $Args
            Label = $Label
            Executable = $output[0]
            Major = $versionParts[0]
            Minor = $versionParts[1]
            Patch = $versionParts[2]
        }
    } catch {
        return $null
    }
}

function Test-IsPython311OrNewer {
    param($Info)
    return ($Info -and ($Info.Major -gt 3 -or ($Info.Major -eq 3 -and $Info.Minor -ge 11)))
}

function Find-Python311 {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $candidates += [pscustomobject]@{ Exe = $py.Source; Args = @("-3.11"); Label = "py -3.11" }
    }
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += [pscustomobject]@{ Exe = $command.Source; Args = @(); Label = $name }
        }
    }
    foreach ($candidate in $candidates) {
        $info = Get-PythonInfo -Exe $candidate.Exe -Args $candidate.Args -Label $candidate.Label
        if (Test-IsPython311OrNewer $info) { return $info }
    }
    return $null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Set-Location $repoRoot

Write-Step "Checking required tools"
$git = Resolve-PreferredCommand -Name "git"
if ($git) { Write-Host "Git: $git" } else { Write-SetupWarning "Git was not found. Install Git from https://git-scm.com/download/win." }

$gh = Resolve-PreferredCommand -Name "gh"
if ($gh) { Write-Host "GitHub CLI: $gh" } else { Write-SetupWarning "GitHub CLI was not found. Install it from https://cli.github.com/." }

$python = Find-Python311
if ($python) {
    Write-Host ("Python: {0} ({1}.{2}.{3})" -f $python.Executable, $python.Major, $python.Minor, $python.Patch)
} else {
    Write-SetupWarning "Python 3.11+ was not found. Install Python 3.11 or newer and rerun this script."
    if (-not $CheckOnly) { exit 1 }
}

if ($WithWorkIQ) {
    Write-Step "Checking Work IQ prerequisites"
    foreach ($tool in @("node", "npm")) {
        $resolved = Resolve-PreferredCommand -Name $tool -PreferredNames @("$tool.cmd", "$tool.exe")
        if ($resolved) { Write-Host "${tool}: $resolved" } else { Write-SetupWarning "$tool was not found. Install Node.js before using Work IQ." }
    }
    $npx = Resolve-PreferredCommand -Name "npx" -PreferredNames @("npx.cmd", "npx.exe")
    if ($npx) { Write-Host "npx: $npx" } else { Write-SetupWarning "npx was not found. Work IQ requires npx." }
    Write-Host "Work IQ may require Microsoft 365 sign-in, EULA acceptance, and Entra ID admin consent."
}

if ($InstallExternalCopilotCli) {
    Write-Step "Checking external Copilot CLI"
    $copilot = Resolve-PreferredCommand -Name "copilot" -PreferredNames @("copilot.cmd", "copilot.exe")
    if ($copilot) {
        Write-Host "External Copilot CLI: $copilot"
    } elseif ($CheckOnly) {
        Write-SetupWarning "External Copilot CLI was not found. It is optional unless COPILOT_CLI_PATH or --cli-path is used."
    } else {
        $winget = Resolve-PreferredCommand -Name "winget"
        if (-not $winget) { throw "winget was not found. Install Copilot CLI manually from GitHub Docs." }
        Invoke-Checked -FilePath $winget -Arguments @("install", "--id", "GitHub.Copilot", "-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements")
    }
}

Write-Step "Checking Python virtual environment"
if (Test-Path $venvPython) {
    $venvInfo = Get-PythonInfo -Exe $venvPython -Label ".venv"
    if (Test-IsPython311OrNewer $venvInfo) {
        Write-Host ("Existing .venv Python: {0}.{1}.{2}" -f $venvInfo.Major, $venvInfo.Minor, $venvInfo.Patch)
    } elseif ($ForceRecreateVenv -and -not $CheckOnly) {
        Write-SetupWarning "Existing .venv is older than Python 3.11. Recreating because -ForceRecreateVenv was specified."
        Remove-Item -Recurse -Force $venvDir
    } else {
        Write-SetupWarning "Existing .venv is older than Python 3.11. Rerun with -ForceRecreateVenv to recreate it."
        if (-not $CheckOnly) { exit 1 }
    }
} elseif ($CheckOnly) {
    Write-SetupWarning ".venv does not exist. Run without -CheckOnly to create it."
}

if (-not $CheckOnly -and -not (Test-Path $venvPython)) {
    if (-not $python) { throw "Python 3.11+ is required to create .venv." }
    Invoke-Checked -FilePath $python.Exe -Arguments @($python.Args + @("-m", "venv", $venvDir))
}

if (Test-Path $venvPython) {
    if (-not $CheckOnly) {
        Write-Step "Installing Python dependencies"
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "github-copilot-sdk")
    }

    Write-Step "Verifying HVE runtime"
    $importExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import copilot")
    if ($importExitCode -eq 0) { Write-Host "github-copilot-sdk import: OK" } else { Write-SetupWarning "github-copilot-sdk import failed. Run without -CheckOnly to install dependencies." }

    $hveHelpExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-m", "hve", "--help")
    if ($hveHelpExitCode -eq 0) { Write-Host "python -m hve --help: OK" } else { Write-SetupWarning "python -m hve --help failed." }
}

if ($gh) {
    Write-Step "Checking GitHub authentication"
    $ghAuthExitCode = Invoke-Probe -FilePath $gh -Arguments @("auth", "status")
    if ($ghAuthExitCode -eq 0) {
        $script:GhAuthOk = $true
        Write-Host "gh auth status: OK"
    } else {
        Write-SetupWarning "gh auth status failed. Run 'gh auth login' before using GitHub operations."
    }
}

Write-Step "Next steps"
if ($gh) {
    if ($script:GhAuthOk) {
        Write-Host "GitHub auth: OK (gh auth status)"
    } else {
        Write-Host "Authenticate GitHub CLI if needed: gh auth login"
        Write-Host "Then verify: gh auth status"
    }
}
if (Test-Path $venvPython) {
    Write-Host "Basic runtime check: $venvPython -m hve --help"
} else {
    Write-Host "Create .venv first (run setup without -CheckOnly), then run: .venv\\Scripts\\python.exe -m hve --help"
}
Write-Host "Optional: Node.js / npm / npx are only required when using Work IQ or Node-based MCP tools."

if ($CheckOnly) {
    Write-Host "`nCheck-only completed with $script:WarningCount warning(s)."
} else {
    Write-Host "`nHVE setup completed with $script:WarningCount warning(s)."
}
