BeforeAll {
    # Force re-load by removing guard functions
    if (Test-Path Function:\Get-Workflow) { Remove-Item Function:\Get-Workflow }
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    if (Test-Path Function:\Invoke-CopilotAssign) { Remove-Item Function:\Invoke-CopilotAssign }
    if (Test-Path Function:\Get-IssueMetadatum) { Remove-Item Function:\Get-IssueMetadatum }

    $ScriptRoot = "$PSScriptRoot/.."
}

Describe 'validate-plan.ps1' {
    BeforeAll {
        $TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "ps-test-$([guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
        $ScriptPath = "$PSScriptRoot/../validate-plan.ps1"
    }

    AfterAll {
        if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    }

    It 'passes for valid PROCEED plan' {
        $planContent = @"
<!-- estimate_total: 10 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定

- 見積合計: 10 分
- 判定結果: PROCEED
"@
        $planPath = Join-Path $TmpDir 'plan-proceed.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'fails for missing split_decision' {
        $planContent = @"
<!-- estimate_total: 10 -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
"@
        $planPath = Join-Path $TmpDir 'plan-no-decision.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'missing required metadata.*split_decision'
    }

    It 'fails for missing implementation_files' {
        $planContent = @"
<!-- estimate_total: 10 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->

# Test Plan

## 分割判定
"@
        $planPath = Join-Path $TmpDir 'plan-no-impl.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'missing required metadata.*implementation_files'
    }

    It 'fails when estimate > 15 but decision = PROCEED' {
        $planContent = @"
<!-- estimate_total: 20 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
"@
        $planPath = Join-Path $TmpDir 'plan-over15-proceed.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'estimate=20min.*PROCEED.*SPLIT_REQUIRED'
    }

    It 'fails when SPLIT_REQUIRED but implementation_files=true' {
        $subContent = "<!-- subissue -->`n<!-- title: Sub 1 -->`nBody"
        $subPath = Join-Path $TmpDir 'subissues.md'
        Set-Content -Path $subPath -Value $subContent

        $planContent = @"
<!-- estimate_total: 20 -->
<!-- split_decision: SPLIT_REQUIRED -->
<!-- subissues_count: 1 -->
<!-- implementation_files: true -->

# Test Plan

## 分割判定
"@
        $planPath = Join-Path $TmpDir 'plan-split-impl.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'SPLIT_REQUIRED but implementation_files=true'
    }

    It 'fails for missing 分割判定 section' {
        $planContent = @"
<!-- estimate_total: 10 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan
"@
        $planPath = Join-Path $TmpDir 'plan-no-bunkatsu.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match "missing required section.*分割判定"
    }

    It 'validates SPLIT_REQUIRED with matching subissues_count' {
        $subDir = Join-Path $TmpDir 'split-ok'
        New-Item -ItemType Directory -Path $subDir -Force | Out-Null

        $subContent = "<!-- subissue -->`n<!-- title: Sub 1 -->`nBody 1`n---`n<!-- subissue -->`n<!-- title: Sub 2 -->`nBody 2"
        Set-Content -Path (Join-Path $subDir 'subissues.md') -Value $subContent

        $planContent = @"
<!-- estimate_total: 20 -->
<!-- split_decision: SPLIT_REQUIRED -->
<!-- subissues_count: 2 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
"@
        Set-Content -Path (Join-Path $subDir 'plan.md') -Value $planContent
        $output = & $ScriptPath -Path (Join-Path $subDir 'plan.md') *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'fails when subissues_count does not match actual count' {
        $subDir = Join-Path $TmpDir 'split-mismatch'
        New-Item -ItemType Directory -Path $subDir -Force | Out-Null

        $subContent = "<!-- subissue -->`n<!-- title: Sub 1 -->`nBody 1"
        Set-Content -Path (Join-Path $subDir 'subissues.md') -Value $subContent

        $planContent = @"
<!-- estimate_total: 20 -->
<!-- split_decision: SPLIT_REQUIRED -->
<!-- subissues_count: 3 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
"@
        Set-Content -Path (Join-Path $subDir 'plan.md') -Value $planContent
        $output = & $ScriptPath -Path (Join-Path $subDir 'plan.md') *>&1 | Out-String
        $output | Should -Match 'subissues_count=3 but subissues.md has 1'
    }

    It 'validates directory mode' {
        $dirMode = Join-Path $TmpDir 'dir-mode'
        New-Item -ItemType Directory -Path $dirMode -Force | Out-Null

        $planContent = @"
<!-- estimate_total: 5 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test

## 分割判定
"@
        Set-Content -Path (Join-Path $dirMode 'plan.md') -Value $planContent
        $output = & $ScriptPath -Directory $dirMode *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'fails for invalid split_decision value' {
        $planContent = @"
<!-- estimate_total: 10 -->
<!-- split_decision: INVALID -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
"@
        $planPath = Join-Path $TmpDir 'plan-invalid-decision.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match "invalid split_decision='INVALID'"
    }
}

Describe 'orchestrate.ps1' {
    It 'shows execution plan for AAS in dry-run' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $output = & $ScriptPath -Workflow aas -DryRun *>&1 | Out-String
        $output | Should -Match 'AAS.*App Selection'
        $output | Should -Match '2'
        $output | Should -Match 'Step\.1:.*アプリケーションリストの作成'
        $output | Should -Match 'Step\.2:.*ソフトウェアアーキテクチャの推薦'
        $output | Should -Match 'ドライラン'
    }

    It 'shows execution plan for AAD with step filter' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $output = & $ScriptPath -Workflow aad -Steps '1.1,1.2' -DryRun *>&1 | Out-String
        $output | Should -Match 'AAD.*App Design'
        $output | Should -Match 'Step\.1\.1:.*ドメイン分析'
        $output | Should -Match 'Step\.1\.2:.*サービス一覧抽出'
        $output | Should -Match 'コンテナ Issue'
        $output | Should -Match 'スキップされるステップ'
    }

    It 'shows execution plan for all 6 workflows' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $workflows = @(
            @{ id = 'aas';  prefix = 'AAS';  count = 2 },
            @{ id = 'aad';  prefix = 'AAD';  count = 13 },
            @{ id = 'asdw'; prefix = 'ASDW'; count = 20 },
            @{ id = 'abd';  prefix = 'ABD';  count = 9 },
            @{ id = 'abdv'; prefix = 'ABDV'; count = 7 },
            @{ id = 'aid';  prefix = 'AID';  count = 9 }
        )
        foreach ($wf in $workflows) {
            $output = & $ScriptPath -Workflow $wf.id -DryRun *>&1 | Out-String
            $output | Should -Match "\[$($wf.prefix)\]"
            $output | Should -Match "$($wf.count)"
        }
    }

    It 'fails for unknown workflow' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $output = & $ScriptPath -Workflow 'invalid_wf' -DryRun *>&1 | Out-String
        $output | Should -Match '不明なワークフロー'
    }
}

Describe 'create-subissues.ps1' {
    BeforeAll {
        $TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "ps-test-cs-$([guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
        $ScriptPath = "$PSScriptRoot/../create-subissues.ps1"
    }

    AfterAll {
        if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    }

    It 'reports 0 blocks for empty file' {
        $emptyFile = Join-Path $TmpDir 'empty.md'
        Set-Content -Path $emptyFile -Value '# No subissues here'
        $output = & $ScriptPath -File $emptyFile -DryRun *>&1 | Out-String
        $output | Should -Match 'No.*subissue.*blocks found'
    }

    It 'parses subissue blocks with metadata' {
        $subFile = Join-Path $TmpDir 'test-subs.md'
        $content = @"
<!-- subissue -->
<!-- title: Task Alpha -->
<!-- labels: bug, feature -->
<!-- custom_agent: TestAgent -->

Body for alpha.

---

<!-- subissue -->
<!-- title: Task Beta -->
<!-- depends_on: 1 -->

Body for beta.
"@
        Set-Content -Path $subFile -Value $content
        $output = & $ScriptPath -File $subFile -ParentIssue 99 -DryRun *>&1 | Out-String
        $output | Should -Match 'Found 2 sub-issue block'
        $output | Should -Match 'Parent issue: #99'
        $output | Should -Match 'Total blocks: 2'
        $output | Should -Match 'Block 1: Task Alpha'
        $output | Should -Match 'Agent: TestAgent'
        $output | Should -Match 'Labels: bug, feature'
        $output | Should -Match 'Root node.*auto-assign Copilot'
        $output | Should -Match 'Block 2: Task Beta'
        $output | Should -Match 'Depends on: \[1\]'
        $output | Should -Match 'Root nodes.*\[1\]'
        $output | Should -Match 'Dependent nodes.*\[2\]'
    }

    It 'handles missing file' {
        $output = & $ScriptPath -File '/tmp/nonexistent-file.md' -DryRun *>&1 | Out-String
        $output | Should -Match 'not found'
    }

    It 'reports no parent when none specified' {
        $subFile = Join-Path $TmpDir 'no-parent.md'
        Set-Content -Path $subFile -Value "<!-- subissue -->`n<!-- title: Solo -->`nBody"
        $output = & $ScriptPath -File $subFile -DryRun *>&1 | Out-String
        $output | Should -Match 'No parent issue'
    }
}

Describe 'run-workflow.ps1' {
    It 'shows help' {
        $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
        $output = & $ScriptPath -Help *>&1 | Out-String
        $output | Should -Match 'Orchestrate a workflow'
        $output | Should -Match 'advance'
        $output | Should -Match 'create-subissues'
        $output | Should -Match 'validate-plan'
        $output | Should -Match 'copilot'
    }

    It 'dispatches orchestrate as default action' {
        $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
        $output = & $ScriptPath -Workflow aas -DryRun *>&1 | Out-String
        $output | Should -Match 'AAS'
    }

    It 'dispatches validate-plan action' {
        $TmpPlan = [System.IO.Path]::GetTempFileName()
        try {
            $planContent = @"
<!-- estimate_total: 5 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test

## 分割判定
"@
            Set-Content -Path $TmpPlan -Value $planContent
            $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
            $output = & $ScriptPath -Action validate-plan -Path $TmpPlan *>&1 | Out-String
            $output | Should -Match 'PASS'
        }
        finally {
            if (Test-Path $TmpPlan) { Remove-Item $TmpPlan -Force }
        }
    }

    It 'fails for missing workflow' {
        $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
        $output = & $ScriptPath *>&1 | Out-String
        $output | Should -Match 'Workflow.*required'
    }
}
