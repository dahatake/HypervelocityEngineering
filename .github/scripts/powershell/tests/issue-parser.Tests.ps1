BeforeAll {
    $env:DRY_RUN = '1'
    $env:REPO = 'test-owner/test-repo'
    $env:GH_TOKEN = 'test-token'
    # Force re-load by removing guard functions
    if (Test-Path Function:\Get-IssueMetadatum) { Remove-Item Function:\Get-IssueMetadatum }
    if (Test-Path Function:\Invoke-GhApi) { Remove-Item Function:\Invoke-GhApi }
    . "$PSScriptRoot/../lib/issue-parser.ps1"
}

Describe 'issue-parser.ps1' {

    Context 'Get-IssueMetadatum' {
        It 'extracts simple metadata' {
            $body = '<!-- root-issue: #42 -->'
            Get-IssueMetadatum -Body $body -Key 'root-issue' | Should -Be '#42'
        }

        It 'extracts metadata with spaces' {
            $body = '<!--   branch:   main   -->'
            Get-IssueMetadatum -Body $body -Key 'branch' | Should -Be 'main'
        }

        It 'extracts auto-context-review flag' {
            $body = '<!-- auto-context-review: true -->'
            Get-IssueMetadatum -Body $body -Key 'auto-context-review' | Should -Be 'true'
        }

        It 'returns empty string when key not found' {
            $body = '<!-- other-key: value -->'
            Get-IssueMetadatum -Body $body -Key 'missing-key' | Should -Be ''
        }

        It 'returns empty string for empty body' {
            Get-IssueMetadatum -Body '' -Key 'test' | Should -Be ''
        }

        It 'extracts metadata from multi-line body' {
            $body = @"
# Title

Some content here.

<!-- parent-issue: #100 -->
<!-- workflow: aad -->

More content.
"@
            Get-IssueMetadatum -Body $body -Key 'parent-issue' | Should -Be '#100'
            Get-IssueMetadatum -Body $body -Key 'workflow' | Should -Be 'aad'
        }

        It 'handles special regex chars in key' {
            $body = '<!-- pr-number: 55 -->'
            Get-IssueMetadatum -Body $body -Key 'pr-number' | Should -Be '55'
        }
    }

    Context 'Get-CustomAgent' {
        It 'extracts agent from Pattern 1 (## Custom Agent)' {
            $body = "## Custom Agent`n" + '`Arch-Microservice-DomainAnalytics`'
            Get-CustomAgent -Body $body | Should -Be 'Arch-Microservice-DomainAnalytics'
        }

        It 'extracts agent from Pattern 2 (Custom agent used)' {
            $body = '> **Custom agent used: Arch-DataModeling**'
            Get-CustomAgent -Body $body | Should -Be 'Arch-DataModeling'
        }

        It 'returns empty string when no agent found' {
            Get-CustomAgent -Body 'No agent here' | Should -Be ''
        }

        It 'returns empty string for empty body' {
            Get-CustomAgent -Body '' | Should -Be ''
        }

        It 'prefers Pattern 1 over Pattern 2' {
            $body = "## Custom Agent`n" + '`Agent1`' + "`n> **Custom agent used: Agent2**"
            Get-CustomAgent -Body $body | Should -Be 'Agent1'
        }

        It 'handles agent names with hyphens' {
            $body = '> **Custom agent used: Dev-Microservice-Azure-ServiceCoding-AzureFunctions**'
            Get-CustomAgent -Body $body | Should -Be 'Dev-Microservice-Azure-ServiceCoding-AzureFunctions'
        }
    }

    Context 'Find-ParentIssue' {
        It 'returns "0" in DRY_RUN mode' {
            $result = Find-ParentIssue -Repo 'test/repo' -IssueNumber '42' 6>$null
            $result | Should -Be '0'
        }
    }
}
