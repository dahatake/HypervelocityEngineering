BeforeAll {
    # Force re-load by removing guard functions
    if (Test-Path Function:\Get-Workflow) { Remove-Item Function:\Get-Workflow }
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    if (Test-Path Function:\Invoke-CopilotAssign) { Remove-Item Function:\Invoke-CopilotAssign }
    if (Test-Path Function:\Get-IssueMetadatum) { Remove-Item Function:\Get-IssueMetadatum }

    $ScriptRoot = "$PSScriptRoot/../powershell"
    $FixturesDir = "$PSScriptRoot/fixtures"
}

# ===========================================================================
# validate-plan.ps1 — fixture ベースのテスト
# ===========================================================================
Describe 'validate-plan with fixtures' {
    It 'passes for sample-plan.md fixture' {
        $ScriptPath = "$ScriptRoot/validate-plan.ps1"
        $output = & $ScriptPath -Path "$FixturesDir/sample-plan.md" *>&1 | Out-String
        $output | Should -Match 'PASS'
    }
}

# ===========================================================================
# validate-subissues.ps1 — fixture ベースのテスト
# ===========================================================================
Describe 'validate-subissues with fixtures' {
    It 'passes for sample-subissues.md fixture' {
        $ScriptPath = "$ScriptRoot/validate-subissues.ps1"
        $output = & $ScriptPath -Path "$FixturesDir/sample-subissues.md" *>&1 | Out-String
        $output | Should -Match 'PASS'
    }
}

# ===========================================================================
# create-subissues.ps1 — fixture ベースのテスト
# ===========================================================================
Describe 'create-subissues with fixtures' {
    It 'parses sample-subissues.md fixture (3 blocks)' {
        $ScriptPath = "$ScriptRoot/create-subissues.ps1"
        $output = & $ScriptPath -File "$FixturesDir/sample-subissues.md" -ParentIssue 99 -DryRun *>&1 | Out-String
        $output | Should -Match 'Found 3 sub-issue block'
        $output | Should -Match 'Parent issue: #99'
        $output | Should -Match 'Block 1:.*ドメイン分析'
        $output | Should -Match 'Block 2:.*サービス一覧抽出'
        $output | Should -Match 'Block 3:.*データモデリング'
        $output | Should -Match 'Depends on: \[1\]'
        $output | Should -Match 'Depends on: \[1, 2\]'
    }
}

# ===========================================================================
# orchestrate.ps1 — dry-run 出力テスト
# ===========================================================================
Describe 'orchestrate dry-run output' {
    It 'AAS dry-run output contains expected fields' {
        $ScriptPath = "$ScriptRoot/orchestrate.ps1"
        $output = & $ScriptPath -Workflow aas -DryRun *>&1 | Out-String
        $output | Should -Match 'AAS'
        $output | Should -Match 'ドライラン'
        $output | Should -Match 'Step'
    }

    It 'AAD dry-run output contains step list' {
        $ScriptPath = "$ScriptRoot/orchestrate.ps1"
        $output = & $ScriptPath -Workflow aad -DryRun *>&1 | Out-String
        $output | Should -Match 'AAD'
        $output | Should -Match 'Step'
    }

    It 'all 5 workflows produce dry-run output' {
        $ScriptPath = "$ScriptRoot/orchestrate.ps1"
        foreach ($wfId in @('aas', 'aad', 'asdw', 'abd', 'abdv')) {
            $output = & $ScriptPath -Workflow $wfId -DryRun *>&1 | Out-String
            $output | Should -Match $wfId.ToUpper()
        }
    }
}

# ===========================================================================
# run-workflow.ps1 — ヘルプ・ディスパッチテスト
# ===========================================================================
Describe 'run-workflow dispatch' {
    It 'shows help listing all subcommands' {
        $ScriptPath = "$ScriptRoot/run-workflow.ps1"
        $output = & $ScriptPath -Help *>&1 | Out-String
        $output | Should -Match 'advance'
        $output | Should -Match 'create-subissues'
        $output | Should -Match 'validate-plan'
        $output | Should -Match 'validate-subissues'
    }

    It 'dispatches validate-plan with fixture' {
        $ScriptPath = "$ScriptRoot/run-workflow.ps1"
        $output = & $ScriptPath -Action validate-plan -Path "$FixturesDir/sample-plan.md" *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'dispatches validate-subissues with fixture' {
        $ScriptPath = "$ScriptRoot/run-workflow.ps1"
        $output = & $ScriptPath -Action validate-subissues -Path "$FixturesDir/sample-subissues.md" *>&1 | Out-String
        $output | Should -Match 'PASS'
    }
}
