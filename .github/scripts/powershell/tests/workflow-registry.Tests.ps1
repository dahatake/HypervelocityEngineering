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
            $wf.name | Should -Be 'App Architecture Design'
            $wf.steps.Count | Should -Be 11
        }

        It 'retrieves ADFD workflow' {
            $wf = Get-Workflow -WorkflowId 'adfd'
            $wf.id | Should -Be 'adfd'
            $wf.name | Should -Be 'Dataflow Design'
            $wf.steps.Count | Should -Be 9
        }

        It 'retrieves ADFDV workflow' {
            $wf = Get-Workflow -WorkflowId 'adfdv'
            $wf.id | Should -Be 'adfdv'
            $wf.name | Should -Be 'Dataflow Dev'
            $wf.steps.Count | Should -Be 7
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

        It 'includes params for ADFDV' {
            $wf = Get-Workflow -WorkflowId 'adfdv'
            $wf.params | Should -Contain 'resource_group'
            $wf.params | Should -Contain 'app_id'
        }
    }

    Context 'Get-Step' {
        It 'retrieves a specific step' {
            $step = Get-Step -WorkflowId 'adfd' -StepId '1.1'
            $step.id | Should -Be '1.1'
            $step.custom_agent | Should -Be 'Arch-Dataflow-DomainAnalytics'
            $step.is_container | Should -Be $false
        }

        It 'throws for unknown step' {
            { Get-Step -WorkflowId 'aas' -StepId '999' } | Should -Throw "*not found*"
        }

        It 'declares the AAS persona steps in dependency order' {
            $personaCatalog = Get-Step -WorkflowId 'aas' -StepId '8'
            $personaCatalog.title | Should -Be 'ペルソナカタログ'
            $personaCatalog.custom_agent | Should -Be 'Arch-PersonaCatalog'
            $personaCatalog.depends_on | Should -Contain '7'
            $personaCatalog.body_template_path | Should -Be 'templates/aas/step-8.md'

            $personaScreen = Get-Step -WorkflowId 'aas' -StepId '9'
            $personaScreen.title | Should -Be 'ペルソナ別共通画面カタログ'
            $personaScreen.custom_agent | Should -Be 'Arch-UI-PersonaScreenList'
            $personaScreen.depends_on | Should -Contain '8'
            $personaScreen.body_template_path | Should -Be 'templates/aas/step-9.md'
        }

        It 'returns correct depends_on' {
            $step = Get-Step -WorkflowId 'adfd' -StepId '3'
            $step.depends_on | Should -Contain '1'
            $step.depends_on | Should -Contain '2'
        }
    }

    Context 'Get-NextStep (root steps)' {
        It 'returns root steps when nothing completed for AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @()
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '1'
        }

        It 'returns root steps for ADFD' {
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @()
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.1'
            $ids | Should -Contain '1.2'
        }
    }

    Context 'Get-NextStep (with completed steps)' {
        It 'advances when step 1 is completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '2'
        }

        It 'returns empty when all steps completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2', '3.1', '3.2', '4.1', '4.2', '5', '6', '7', '8', '9')
            $next.Count | Should -Be 0
        }

        It 'advances from step 7 to the persona catalog step in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2', '3.1', '3.2', '4.1', '4.2', '5', '6', '7')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '8'
            $next[0].custom_agent | Should -Be 'Arch-PersonaCatalog'
        }

        It 'advances from the persona catalog step to the persona screen step in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2', '3.1', '3.2', '4.1', '4.2', '5', '6', '7', '8')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '9'
            $next[0].custom_agent | Should -Be 'Arch-UI-PersonaScreenList'
        }

        It 'advances with dependency resolution in ADFD' {
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('1.1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '1.2'
            $ids | Should -Not -Contain '2'
        }

        It 'handles multiple dependencies in ADFD' {
            # Step 2 depends on both 1.1 and 1.2
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('1.1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Not -Contain '2'

            $next2 = Get-NextStep -WorkflowId 'adfd' -Completed @('1.1', '1.2')
            $ids2 = $next2 | ForEach-Object { $_.id }
            $ids2 | Should -Contain '2'
        }
    }

    Context 'Get-NextStep (with skipped steps)' {
        It 'treats skipped steps as resolved dependencies' {
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('1.1', '1.2') -Skipped @('2')
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
