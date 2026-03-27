BeforeAll {
    $env:DRY_RUN = '1'
    $env:REPO = 'test-owner/test-repo'
    # Force re-load by removing guard functions
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    . "$PSScriptRoot/../lib/gh-api.ps1"
}

Describe 'gh-api.ps1' {

    Context 'Invoke-GhApi' {
        It 'returns empty JSON in DRY_RUN mode' {
            $result = Invoke-GhApi -Method 'GET' -Endpoint '/repos/test/test/issues' 6>$null
            $result | Should -Be '{}'
        }

        It 'uses REPO env when Repo param is omitted' {
            # DRY_RUN mode so no actual call is made
            $result = Invoke-GhApi -Method 'GET' -Endpoint '/test' 6>$null
            $result | Should -Be '{}'
        }

        It 'throws when no repo is available' {
            $savedRepo = $env:REPO
            try {
                $env:REPO = ''
                { Invoke-GhApi -Method 'GET' -Endpoint '/test' } | Should -Throw '*Repository not specified*'
            }
            finally {
                $env:REPO = $savedRepo
            }
        }
    }

    Context 'New-GitHubIssue' {
        It 'returns "0 0" in DRY_RUN mode' {
            $result = New-GitHubIssue -Title 'test' -Body 'body' -LabelsJson '["bug"]' 6>$null
            $result | Should -Be '0 0'
        }
    }

    Context 'Add-SubIssueLink' {
        It 'runs without error in DRY_RUN mode' {
            { Add-SubIssueLink -ParentNum '1' -ChildId '123' 6>$null } | Should -Not -Throw
        }
    }

    Context 'Add-IssueLabel' {
        It 'runs without error in DRY_RUN mode' {
            { Add-IssueLabel -IssueNum '1' -Label 'bug' 6>$null } | Should -Not -Throw
        }
    }

    Context 'New-GitHubLabel' {
        It 'runs without error in DRY_RUN mode' {
            { New-GitHubLabel -Name 'test' -Color '0E8A16' 6>$null } | Should -Not -Throw
        }
    }

    Context 'Add-IssueComment' {
        It 'runs without error in DRY_RUN mode' {
            { Add-IssueComment -IssueNum '1' -Body 'comment' 6>$null } | Should -Not -Throw
        }
    }

    Context 'Get-GitHubIssue' {
        It 'returns PSCustomObject in DRY_RUN mode' {
            $result = Get-GitHubIssue -IssueNum '1' 6>$null
            $result | Should -BeOfType [PSCustomObject]
            $result.number | Should -Be 0
            $result.title | Should -Be ''
            $result.body | Should -Be ''
            $result.state | Should -Be ''
            $result.labels.Count | Should -Be 0
            $result.assignees.Count | Should -Be 0
            $result.id | Should -Be 0
            $result.node_id | Should -Be ''
        }
    }
}
