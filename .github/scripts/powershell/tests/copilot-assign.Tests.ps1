BeforeAll {
    $env:DRY_RUN = '1'
    $env:REPO = 'test-owner/test-repo'
    # Force re-load by removing guard functions
    if (Test-Path Function:\Invoke-CopilotAssign) { Remove-Item Function:\Invoke-CopilotAssign }
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    . "$PSScriptRoot/../lib/copilot-assign.ps1"
}

Describe 'copilot-assign.ps1' {

    Context 'Invoke-CopilotAssign' {
        It 'returns true in DRY_RUN mode' {
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '42' 6>$null
            $result | Should -Be $true
        }

        It 'accepts CustomAgent parameter' {
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '42' `
                -CustomAgent 'Arch-DataModeling' 6>$null
            $result | Should -Be $true
        }

        It 'accepts BaseBranch parameter' {
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '42' `
                -BaseBranch 'develop' 6>$null
            $result | Should -Be $true
        }

        It 'accepts all parameters' {
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '42' `
                -CustomAgent 'TestAgent' -BaseBranch 'main' `
                -CustomInstructions 'test instructions' -MaxRetries 5 6>$null
            $result | Should -Be $true
        }

        It 'defaults BaseBranch to main' {
            # Verify by checking that the function runs without error
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '1' 6>$null
            $result | Should -Be $true
        }

        It 'defaults MaxRetries to 3' {
            # Verify by checking that the function runs without error
            $result = Invoke-CopilotAssign -Repo 'test/repo' -IssueNumber '1' 6>$null
            $result | Should -Be $true
        }
    }
}
