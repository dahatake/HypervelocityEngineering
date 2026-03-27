BeforeAll {
    # Force re-load by removing guard functions
    if (Test-Path Function:\Get-Workflow) { Remove-Item Function:\Get-Workflow }
    . "$PSScriptRoot/../lib/workflow-registry.ps1"
}

Describe 'workflow-registry.ps1' {

    Context 'Get-Workflow' {
        It 'retrieves AAS workflow' {
            $wf = Get-Workflow -WorkflowId 'aas'
            $wf.id | Should -Be 'aas'
            $wf.name | Should -Be 'Auto App Selection'
            $wf.steps.Count | Should -Be 2
        }

        It 'retrieves AAD workflow' {
            $wf = Get-Workflow -WorkflowId 'aad'
            $wf.id | Should -Be 'aad'
            $wf.name | Should -Be 'Auto App Design'
            $wf.steps.Count | Should -Be 16
        }

        It 'retrieves ASDW workflow' {
            $wf = Get-Workflow -WorkflowId 'asdw'
            $wf.id | Should -Be 'asdw'
            $wf.name | Should -Be 'Auto App Dev Microservice Azure'
            $wf.steps.Count | Should -Be 24
        }

        It 'retrieves ABD workflow' {
            $wf = Get-Workflow -WorkflowId 'abd'
            $wf.id | Should -Be 'abd'
            $wf.name | Should -Be 'Auto Batch Design'
            $wf.steps.Count | Should -Be 9
        }

        It 'retrieves ABDV workflow' {
            $wf = Get-Workflow -WorkflowId 'abdv'
            $wf.id | Should -Be 'abdv'
            $wf.name | Should -Be 'Auto Batch Dev'
            $wf.steps.Count | Should -Be 7
        }

        It 'retrieves AID workflow' {
            $wf = Get-Workflow -WorkflowId 'aid'
            $wf.id | Should -Be 'aid'
            $wf.name | Should -Be 'Auto IoT Design'
            $wf.steps.Count | Should -Be 10
        }

        It 'is case-insensitive' {
            $wf = Get-Workflow -WorkflowId 'AAS'
            $wf.id | Should -Be 'aas'
        }

        It 'throws for unknown workflow' {
            { Get-Workflow -WorkflowId 'unknown' } | Should -Throw '*Unknown workflow*'
        }

        It 'includes state_labels' {
            $wf = Get-Workflow -WorkflowId 'aas'
            $wf.state_labels.initialized | Should -Be 'aas:initialized'
            $wf.state_labels.ready | Should -Be 'aas:ready'
            $wf.state_labels.running | Should -Be 'aas:running'
            $wf.state_labels.done | Should -Be 'aas:done'
            $wf.state_labels.blocked | Should -Be 'aas:blocked'
        }

        It 'includes params for ASDW' {
            $wf = Get-Workflow -WorkflowId 'asdw'
            $wf.params | Should -Contain 'app_id'
            $wf.params | Should -Contain 'resource_group'
            $wf.params | Should -Contain 'usecase_id'
        }
    }

    Context 'Get-Step' {
        It 'retrieves a specific step' {
            $step = Get-Step -WorkflowId 'aad' -StepId '1.1'
            $step.id | Should -Be '1.1'
            $step.custom_agent | Should -Be 'Arch-Microservice-DomainAnalytics'
            $step.is_container | Should -Be $false
        }

        It 'retrieves a container step' {
            $step = Get-Step -WorkflowId 'aad' -StepId '1'
            $step.is_container | Should -Be $true
            $step.custom_agent | Should -BeNullOrEmpty
        }

        It 'throws for unknown step' {
            { Get-Step -WorkflowId 'aas' -StepId '999' } | Should -Throw "*not found*"
        }

        It 'returns correct depends_on' {
            $step = Get-Step -WorkflowId 'aad' -StepId '7.3'
            $step.depends_on | Should -Contain '6'
            $step.depends_on | Should -Contain '7.1'
            $step.depends_on | Should -Contain '7.2'
        }

        It 'returns step with alpha suffix (ASDW 2.3T)' {
            $step = Get-Step -WorkflowId 'asdw' -StepId '2.3T'
            $step.id | Should -Be '2.3T'
            $step.custom_agent | Should -Be 'Arch-TDD-TestSpec'
        }
    }

    Context 'Get-NextStep (root steps)' {
        It 'returns root steps when nothing completed for AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @()
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '1'
        }

        It 'returns root steps when nothing completed for AAD' {
            $next = Get-NextStep -WorkflowId 'aad' -Completed @()
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.1'
            # Containers should not be included
            $ids | Should -Not -Contain '1'
            $ids | Should -Not -Contain '7'
            $ids | Should -Not -Contain '8'
        }

        It 'returns root steps for ABD' {
            $next = Get-NextStep -WorkflowId 'abd' -Completed @()
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.1'
            $ids | Should -Contain '1.2'
        }

        It 'returns root steps for AID' {
            $next = Get-NextStep -WorkflowId 'aid' -Completed @()
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.1'
            $ids | Should -Contain '1.2'
            $ids | Should -Not -Contain '5'
        }
    }

    Context 'Get-NextStep (with completed steps)' {
        It 'advances when step 1 is completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '2'
        }

        It 'returns empty when all steps completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2')
            $next.Count | Should -Be 0
        }

        It 'advances with dependency resolution in AAD' {
            $next = Get-NextStep -WorkflowId 'aad' -Completed @('1.1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.2'
            $ids | Should -Not -Contain '2'
        }

        It 'handles multiple dependencies in ABD' {
            # Step 2 depends on both 1.1 and 1.2
            $next = Get-NextStep -WorkflowId 'abd' -Completed @('1.1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Not -Contain '2'

            $next2 = Get-NextStep -WorkflowId 'abd' -Completed @('1.1', '1.2')
            $ids2 = $next2 | ForEach-Object { $_.id }
            $ids2 | Should -Contain '2'
        }
    }

    Context 'Get-NextStep (with skipped steps)' {
        It 'treats skipped steps as resolved dependencies' {
            $next = Get-NextStep -WorkflowId 'aad' -Completed @('1.1', '1.2') -Skipped @('2')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '3'
        }

        It 'does not return skipped steps' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @() -Skipped @('1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Not -Contain '1'
            $ids | Should -Contain '2'
        }
    }
}
