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
            $wf.steps.Count | Should -Be 10
        }

        It 'retrieves ARD workflow' {
            $wf = Get-Workflow -WorkflowId 'ard'
            $wf.id | Should -Be 'ard'
            $wf.steps.Count | Should -Be 10
        }

        It 'retrieves ADFD workflow' {
            $wf = Get-Workflow -WorkflowId 'adfd'
            $wf.id | Should -Be 'adfd'
            $wf.name | Should -Be 'Dataflow Design'
            $wf.steps.Count | Should -Be 7
        }

        It 'retrieves ADFDV workflow' {
            $wf = Get-Workflow -WorkflowId 'adfdv'
            $wf.id | Should -Be 'adfdv'
            $wf.name | Should -Be 'Dataflow Dev'
            $wf.steps.Count | Should -Be 8
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
            ($wf.params -join ',') | Should -Be 'app_ids,app_id,resource_group,tdd_max_retries'
        }

        It 'includes exact params for ADFD and AAS' {
            ((Get-Workflow -WorkflowId 'adfd').params -join ',') | Should -Be 'app_ids,app_id'
            (Get-Workflow -WorkflowId 'aas').params.Count | Should -Be 0
        }
    }

    Context 'Get-Step' {
        It 'retrieves a specific step' {
            $step = Get-Step -WorkflowId 'adfd' -StepId '0.1'
            $step.id | Should -Be '0.1'
            $step.custom_agent | Should -Be 'Arch-Dataflow-DataModel'
            $step.is_container | Should -Be $false
        }

        It 'includes the ADFDV requirements conformance step' {
            $step = Get-Step -WorkflowId 'adfdv' -StepId '4.3'
            $step.custom_agent | Should -Be 'QA-RequirementsConformanceEval'
            $step.depends_on | Should -Contain '4.1'
            $step.depends_on | Should -Contain '4.2'
        }

        It 'throws for unknown step' {
            { Get-Step -WorkflowId 'aas' -StepId '999' } | Should -Throw "*not found*"
        }

        It 'declares the AAS persona steps in dependency order' {
            $personaCatalog = Get-Step -WorkflowId 'aas' -StepId '7'
            $personaCatalog.title | Should -Be 'ペルソナカタログ'
            $personaCatalog.custom_agent | Should -Be 'Arch-PersonaCatalog'
            $personaCatalog.depends_on | Should -Contain '6'
            $personaCatalog.body_template_path | Should -Be '.github/prompts/steps/aas/step-7.prompt.md'

            $personaScreen = Get-Step -WorkflowId 'aas' -StepId '8'
            $personaScreen.title | Should -Be 'ペルソナ別共通画面カタログ'
            $personaScreen.custom_agent | Should -Be 'Arch-UI-PersonaScreenList'
            $personaScreen.depends_on | Should -Contain '7'
            $personaScreen.body_template_path | Should -Be '.github/prompts/steps/aas/step-8.prompt.md'
        }

        It 'preserves AAS skip fallback dependencies' {
            (Get-Step -WorkflowId 'aas' -StepId '4').skip_fallback_deps | Should -Contain '3.1'
            (Get-Step -WorkflowId 'aas' -StepId '8').skip_fallback_deps | Should -Contain '7'
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
            $ids.Count | Should -Be 1
            $ids | Should -Contain '0.1'
        }
    }

    Context 'Get-NextStep (with completed steps)' {
        It 'advances when step 1 is completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '2.1'
        }

        It 'returns empty when all steps completed in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2.1', '2.2', '3.1', '3.2', '4', '5', '6', '7', '8')
            $next.Count | Should -Be 0
        }

        It 'advances from step 6 to the persona catalog step in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2.1', '2.2', '3.1', '3.2', '4', '5', '6')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '7'
            $next[0].custom_agent | Should -Be 'Arch-PersonaCatalog'
        }

        It 'advances from the persona catalog step to the persona screen step in AAS' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @('1', '2.1', '2.2', '3.1', '3.2', '4', '5', '6', '7')
            $next.Count | Should -Be 1
            $next[0].id | Should -Be '8'
            $next[0].custom_agent | Should -Be 'Arch-UI-PersonaScreenList'
        }

        It 'advances from the ADFD root to the app catalog' {
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('0.1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '0.2'
            $ids | Should -Not -Contain '4'
        }

        It 'handles multiple dependencies in ADFD' {
            # Step 3 depends on both Step 1 and Step 2.
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('0.1', '0.2', '4', '5', '1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '2'
            $ids | Should -Not -Contain '3'

            $next2 = Get-NextStep -WorkflowId 'adfd' -Completed @('0.1', '0.2', '4', '5', '1', '2')
            $ids2 = $next2 | ForEach-Object { $_.id }
            $ids2 | Should -Contain '3'
        }
    }

    Context 'Get-NextStep (with skipped steps)' {
        It 'treats skipped steps as resolved dependencies' {
            $next = Get-NextStep -WorkflowId 'adfd' -Completed @('0.1', '0.2', '4', '5', '1') -Skipped @('2')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Contain '3'
        }

        It 'does not return skipped steps' {
            $next = Get-NextStep -WorkflowId 'aas' -Completed @() -Skipped @('1')
            $ids = $next | ForEach-Object { $_.id }
            $ids | Should -Not -Contain '1'
            $ids | Should -Contain '2.1'
        }
    }
}
