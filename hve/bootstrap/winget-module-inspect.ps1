# FR-LOCAL-SURFACE-04: package-owned module/command inspection in a disposable child.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ExpectedVersion,
    [Parameter(Mandatory)][string]$ExpectedModuleBase,
    [switch]$Repair
)

$ErrorActionPreference = 'Stop'
$env:PSModulePath = Join-Path $PSHOME 'Modules'
try {
    if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'runtime' }
    $moduleBaseFullPath = [IO.Path]::GetFullPath($ExpectedModuleBase).TrimEnd('\', '/')
    $manifestFullPath = [IO.Path]::GetFullPath($ManifestPath)
    if (-not [string]::Equals($manifestFullPath, (Join-Path $moduleBaseFullPath 'Microsoft.WinGet.Client.psd1'),
            [StringComparison]::OrdinalIgnoreCase)) { throw 'manifest-path' }
    foreach ($path in @($moduleBaseFullPath, $manifestFullPath)) {
        if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'reparse-point' }
    }
    $modules = @(Import-Module $manifestFullPath -Force -PassThru -ErrorAction Stop)
    if ($modules.Count -ne 1) { throw 'module-count' }
    $module = $modules[0]
    $moduleBaseMatches = [string]::Equals([IO.Path]::GetFullPath($module.ModuleBase).TrimEnd('\', '/'),
        $moduleBaseFullPath, [StringComparison]::OrdinalIgnoreCase)
    if ($module.Name -cne 'Microsoft.WinGet.Client' -or $module.Version.ToString() -cne $ExpectedVersion -or
        -not $moduleBaseMatches) { throw 'module-ownership' }
    $commands = @(Get-Command Repair-WinGetPackageManager -Module $module.Name -ErrorAction Stop)
    if ($commands.Count -ne 1) { throw 'command-count' }
    $command = $commands[0]
    $commandModuleMatches = $command.ModuleName -ceq $module.Name
    $commandVersionMatches = $command.Version.ToString() -ceq $module.Version.ToString()
    $commandModuleBaseMatches = [string]::Equals([IO.Path]::GetFullPath($command.Module.ModuleBase).TrimEnd('\', '/'),
        $moduleBaseFullPath, [StringComparison]::OrdinalIgnoreCase)
    if (-not $commandModuleMatches -or -not $commandVersionMatches -or -not $commandModuleBaseMatches) { throw 'command-ownership' }
    foreach ($name in @('Force', 'Latest')) {
        if (-not $command.Parameters.ContainsKey($name)) { throw 'command-parameters' }
    }
    if ($Repair) { & $command -Force -Latest | Out-Null }
    [ordered]@{
        schema_version = 1; status = 'PASS'; module_name = $module.Name
        module_version = $module.Version.ToString(); module_base_match = $moduleBaseMatches
        command = $command.Name; command_module_match = $commandModuleMatches
        command_version_match = $commandVersionMatches; command_module_base_match = $commandModuleBaseMatches
        required_parameters = @('Force', 'Latest')
    } | ConvertTo-Json -Compress -Depth 3
} catch {
    [Console]::Error.WriteLine('BOOTSTRAP_FAIL stage=winget-module reason=inspection-failed retry=true')
    exit 3
}