BeforeAll {
    # Force re-load by removing guard functions
    if (Test-Path Function:\Get-Workflow) { Remove-Item Function:\Get-Workflow }
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    if (Test-Path Function:\Invoke-CopilotAssign) { Remove-Item Function:\Invoke-CopilotAssign }
    if (Test-Path Function:\Get-IssueMetadatum) { Remove-Item Function:\Get-IssueMetadatum }
}

Describe 'validate-plan.ps1' {
    BeforeAll {
        $TmpRoot = Join-Path $PSScriptRoot '.tmp'
        $TmpDir = Join-Path $TmpRoot "ps-test-$([guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
        $ScriptPath = "$PSScriptRoot/../validate-plan.ps1"
    }

    AfterAll {
        if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    }

    It 'passes for valid plan with 完了条件' {
        $planContent = @"
# Test Plan

## 完了条件

- [ ] validate-plan が PASS する
"@
        $planPath = Join-Path $TmpDir 'plan-valid.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'passes without metadata and without 分割判定 when 完了条件 has content' {
        $planContent = @"
# Test Plan

## 概要

No metadata comments are required.

## 完了条件

- [ ] validate-plan が PASS する
"@
        $planPath = Join-Path $TmpDir 'plan-metadata-free.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'validates directory mode' {
        $dirMode = Join-Path $TmpDir 'dir-mode'
        New-Item -ItemType Directory -Path $dirMode -Force | Out-Null

        $planContent = @"
# Test

## 完了条件

- [ ] validate-plan が PASS する
"@
        Set-Content -Path (Join-Path $dirMode 'plan.md') -Value $planContent
        $output = & $ScriptPath -Directory $dirMode *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'fails for missing 完了条件 section' {
        # FR-DOD-02
        $planContent = @"
# Test Plan

## 概要

No completion criteria are present.
"@
        $planPath = Join-Path $TmpDir 'plan-missing-dod.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match "missing required section '## 完了条件'"
    }

    It 'fails for empty 完了条件 section' {
        # FR-DOD-02
        $planContent = @"
# Test Plan

## 完了条件
"@
        $planPath = Join-Path $TmpDir 'plan-empty-dod.md'
        Set-Content -Path $planPath -Value $planContent
        $output = & $ScriptPath -Path $planPath *>&1 | Out-String
        $output | Should -Match "section '## 完了条件' has no non-placeholder content"
    }
}

Describe 'validate-subissues.ps1' {
    BeforeAll {
        $TmpRoot = Join-Path $PSScriptRoot '.tmp'
        $TmpDir = Join-Path $TmpRoot "ps-test-sub-$([guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
        $ScriptPath = "$PSScriptRoot/../validate-subissues.ps1"
    }

    AfterAll {
        if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    }

    It 'passes when all blocks have title metadata' {
        $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
Body 1

## 完了条件

- [ ] done 1

<!-- subissue -->
<!-- title: Sub 2 -->
Body 2

## 完了条件

- [ ] done 2
"@
        $subPath = Join-Path $TmpDir 'subissues-valid.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match 'PASS'
    }

    It 'fails when title metadata is missing' {
        $subContent = @"
<!-- subissue -->
## Sub-001
- Title: Sub 1
"@
        $subPath = Join-Path $TmpDir 'subissues-missing-title.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match '欠落ブロック'
    }

    It 'fails when title metadata is empty' {
        $subContent = @"
<!-- subissue -->
<!-- title:    -->
Body
"@
        $subPath = Join-Path $TmpDir 'subissues-empty-title.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match '空値ブロック'
    }

    It 'fails when 完了条件 section is missing' {
        # FR-DOD-01
        $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X
"@
        $subPath = Join-Path $TmpDir 'subissues-missing-dod.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match "'## 完了条件' 欠落ブロック"
    }

    It 'fails when 完了条件 section is empty' {
        # FR-DOD-01
        $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件
"@
        $subPath = Join-Path $TmpDir 'subissues-empty-dod.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match "'## 完了条件' 空値・プレースホルダブロック"
    }

    It 'fails when 完了条件 contains only a REPLACE_ME placeholder' {
        # FR-DOD-01
        $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件
- [ ] {REPLACE_ME_DOD}
"@
        $subPath = Join-Path $TmpDir 'subissues-placeholder-dod.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match "'## 完了条件' 空値・プレースホルダブロック"
    }

    It 'does not accept a horizontal rule alone as 完了条件 content' {
        # FR-DOD-01: subissues.md はブロック区切りに `---` を使うため、水平線だけでは内容と認めない。
        $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件

---
"@
        $subPath = Join-Path $TmpDir 'subissues-hr-only-dod.md'
        Set-Content -Path $subPath -Value $subContent
        $output = & $ScriptPath -Path $subPath *>&1 | Out-String
        $output | Should -Match "'## 完了条件' 空値・プレースホルダブロック"
    }
}

Describe 'orchestrate.ps1' {
    It 'shows execution plan for AAS in dry-run' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $output = & $ScriptPath -Workflow aas -DryRun *>&1 | Out-String
        $output | Should -Match 'AAS.*App Architecture Design'
        $output | Should -Match '1'
        $output | Should -Match 'Step\.1:.*ソフトウェアアーキテクチャの推薦'
        $output | Should -Match 'ドライラン'
    }

    It 'shows execution plan for ADFD with step filter' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $output = & $ScriptPath -Workflow adfd -Steps '0.1,0.2' -DryRun *>&1 | Out-String
        $output | Should -Match 'ADFD.*Dataflow Design'
        $output | Should -Match 'Step\.0\.1:.*データフローデータモデル定義書'
        $output | Should -Match 'Step\.0\.2:.*データフローアプリカタログ'
        $output | Should -Match 'スキップされるステップ'
    }

    It 'shows execution plan for all 3 workflows' {
        $ScriptPath = "$PSScriptRoot/../orchestrate.ps1"
        $workflows = @(
            @{ id = 'aas';  prefix = 'AAS';  count = 10 },
            @{ id = 'adfd';  prefix = 'ADFD';  count = 7 },
            @{ id = 'adfdv'; prefix = 'ADFDV'; count = 8 }
        )
        foreach ($wf in $workflows) {
            $output = & $ScriptPath -Workflow $wf.id -DryRun *>&1 | Out-String
            $output | Should -Match "\[$($wf.prefix)\]"
            $output | Should -Match "作成するステップ \($($wf.count) 個\)"
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
        $TmpRoot = Join-Path $PSScriptRoot '.tmp'
        $TmpDir = Join-Path $TmpRoot "ps-test-cs-$([guid]::NewGuid().ToString('N').Substring(0,8))"
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
        $missingFile = Join-Path $TmpDir 'nonexistent-file.md'
        $output = & $ScriptPath -File $missingFile -DryRun *>&1 | Out-String
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
        $output | Should -Match 'validate-subissues'
        $output | Should -Match 'copilot'
    }

    It 'dispatches orchestrate as default action' {
        $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
        $output = & $ScriptPath -Workflow aas -DryRun *>&1 | Out-String
        $output | Should -Match 'AAS'
    }

    It 'dispatches validate-plan action' {
        $tmpRoot = Join-Path $PSScriptRoot '.tmp'
        New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
        $TmpPlan = Join-Path $tmpRoot "run-workflow-plan-$([guid]::NewGuid().ToString('N')).md"
        try {
            $planContent = @"
# Test

## 完了条件

- [ ] validate-plan が PASS する
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

    It 'dispatches validate-subissues action' {
        $tmpRoot = Join-Path $PSScriptRoot '.tmp'
        New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
        $tmpSub = Join-Path $tmpRoot "run-workflow-sub-$([guid]::NewGuid().ToString('N')).md"
        try {
            $subContent = @"
<!-- subissue -->
<!-- title: Sub 1 -->
Body

## 完了条件

- [ ] done
"@
            Set-Content -Path $tmpSub -Value $subContent
            $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
            $output = & $ScriptPath -Action validate-subissues -Path $tmpSub *>&1 | Out-String
            $output | Should -Match 'PASS'
        }
        finally {
            if (Test-Path $tmpSub) { Remove-Item $tmpSub -Force }
        }
    }

    It 'fails for missing workflow' {
        $ScriptPath = "$PSScriptRoot/../run-workflow.ps1"
        $output = & $ScriptPath *>&1 | Out-String
        $output | Should -Match 'Workflow.*required'
    }
}
