from .formatting import *
from .home import *
from .activation import *
from .models import *
from .accounts import *
from .proxies import *
from .tasks import *
from .incidents import *
from .reports import *
from .intelligence import *
from .learning import *
from .automations import *
from .opportunities import *
from .predictions import *
from .recovery import *
from .platforms import *
from .settings import *
from .team import *
from .team_intelligence import *
from .coo import *
from .search import *
from .ai import *
from .help import *
from .errors import *
from app.models.opportunity import CreatorPostAlert, OwnPostAlert
from app.services.opportunities import mark_creator_post_alert_reviewed, mark_own_post_alert_reviewed

def render_page(page: str, session: Session | None = None, user: User | None = None) -> Screen:
    if page == "owner_advanced":
        return render_owner_advanced_page()
    if page == "recovery_center" and session is not None:
        return render_recovery_center_page(session, user)
    if page == "recovery:details" and session is not None:
        return render_recovery_center_page(session, user, details=True)
    if page == "recovery:backup:run" and session is not None:
        return render_backup_run_page(session, user)
    if page == "recovery:history" and session is not None:
        return render_backup_history_page(session, user)
    if page == "recovery:storage" and session is not None:
        return render_backup_storage_page(session, user)
    if page.startswith("recovery:storage:s3") and session is not None:
        return render_backup_storage_page(session, user, target_type="s3_compatible")
    if page.startswith("recovery:storage:b2") and session is not None:
        return render_backup_storage_page(session, user, target_type="backblaze_b2")
    if page == "recovery:storage:manual" and session is not None:
        return render_backup_storage_page(session, user, target_type="manual_export")
    if page == "recovery:restore:test" and session is not None:
        return render_restore_test_page(session, user)
    if page == "recovery:disaster_plan":
        return render_disaster_plan_page()
    if page == "recovery:disaster_plan:details":
        return render_disaster_plan_page(details=True)
    if page == "team_intelligence" and session is not None:
        return render_team_intelligence_page(session, user)
    if page == "team_intelligence:details" and session is not None:
        return render_team_intelligence_page(session, user, details=True)
    if page == "platforms" and session is not None:
        return render_platform_connections_page(session, user)
    if page == "platforms:details" and session is not None:
        return render_platform_connections_page(session, user, details=True)
    if page == "platforms:notifications" and session is not None:
        return render_platform_notification_center_page(session, user)
    if page == "platforms:alert_routing" and session is not None:
        return render_alert_routing_center_page(session, user)
    if page == "platforms:alert_health" and session is not None:
        return render_alert_health_page(session, user)
    if page == "platforms:alert_health:details" and session is not None:
        return render_alert_health_page(session, user, details=True)
    if page.startswith("platforms:notifications:") and session is not None:
        parts = page.split(":")
        platform = parts[2] if len(parts) >= 3 else ""
        action = parts[3] if len(parts) >= 4 else None
        return render_platform_notification_detail_page(session, platform, user, action=action)
    if page.startswith("platforms:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2:
            platform = parts[1]
            if len(parts) >= 3 and parts[2] == "test_website":
                return render_platform_detail_page(session, platform, user, run_website_check=True)
            if len(parts) >= 3 and parts[2] == "details":
                return render_platform_detail_page(session, platform, user, details=True)
            if len(parts) >= 3 and parts[2] in {"connection", "stats"}:
                return render_platform_detail_page(session, platform, user, section=parts[2])
            return render_platform_detail_page(session, platform, user)
    if page == "today_priorities" and session is not None:
        return render_today_priorities_page(session, user)
    if page == "setup_progress" and session is not None:
        return render_setup_progress_page(session, user)
    if page == "assistant_next" and session is not None:
        return render_assistant_next_page(session, user)
    if page == "start_here" and session is not None:
        return render_start_here_page(session, user)
    if page == "first_workspace" and session is not None:
        return render_first_workspace_flow_page(session, user)
    if page == "structure":
        return render_structure_map_page()
    if page == "coo" and session is not None:
        return render_coo_dashboard_page(session, user)
    if page == "coo:top5" and session is not None:
        return render_today_top5_page(session, user)
    if page == "coo:readiness" and session is not None:
        return render_readiness_v2_page(session)
    if page == "coo:briefing" and session is not None:
        return render_coo_briefing_page(session, user)
    if page == "coo:briefing:details" and session is not None:
        return render_coo_briefing_page(session, user, details=True)
    if page == "search" and session is not None:
        return render_search_center_page(session, user)
    if page == "search:details" and session is not None:
        return render_search_center_page(session, user, details=True)
    if page == "search:run" and session is not None:
        return render_search_guided_page(session, "run", user)
    if page == "search:opportunity" and session is not None:
        return render_search_guided_page(session, "opportunity", user)
    if page == "search:platform_signals" and session is not None:
        return render_search_guided_page(session, "platform_signals", user)
    if page == "search:coo_context" and session is not None:
        return render_search_guided_page(session, "coo_context", user)
    if page == "search:history" and session is not None:
        return render_search_history_page(session, user)
    if page == "search:history:rerun" and session is not None:
        return render_search_history_page(session, user, rerun=True)
    if page == "search:results" and session is not None:
        return render_search_results_page(session, user)
    if page.startswith("search:results:") and session is not None:
        return render_search_results_page(session, user, action=page.split(":")[-1])
    if page == "search:settings" and session is not None:
        return render_search_settings_page(session, user)
    if page == "ai_brain" and session is not None:
        return render_ai_brain_page(session, user)
    if page == "ai_brain:details" and session is not None:
        return render_ai_brain_page(session, user, details=True)
    if page == "ai_brain:settings" and session is not None:
        return render_ai_settings_page(session, user)
    if page == "ai_brain:critic" and session is not None:
        return render_ai_critic_status_page(session, user)
    if page == "ai_brain:evidence" and session is not None:
        return render_ai_evidence_summary_page(session, user)
    if page == "ai_brain:search" and session is not None:
        return render_ai_search_summary_page(session, user)
    if page == "ai_brain:coo" and session is not None:
        return render_ai_coo_briefing_page(session, user)
    if page == "ai_brain:opportunity" and session is not None:
        return render_ai_opportunity_explanation_page(session, user)
    if page == "decision:top" and session is not None:
        return render_decision_top_priority_page(session, user)
    if page == "decision:details" and session is not None:
        return render_decision_details_page(session, user)
    if page.startswith("decision:feedback:") and session is not None:
        return render_decision_feedback_page(session, page.split(":")[-1], user)
    if page == "decision:memory" and session is not None:
        return render_decision_memory_page(session, user)
    if page.startswith("decision:memory:") and session is not None:
        suffix = page.split(":")[-1]
        if suffix == "details":
            return render_decision_memory_page(session, user, details=True)
        return render_decision_memory_page(session, user, status_filter=suffix)
    if page == "coo:load" and session is not None:
        return render_load_balancer_page(session)
    if page == "executive_mode" and session is not None:
        return render_executive_mode_page(session, user)
    if page == "manager_queue" and session is not None:
        return render_manager_queue_page(session, user)
    if page == "my_work" and session is not None and user is not None:
        return render_my_work_page(session, user)
    if page == "owner_daily_checklist" and session is not None and user is not None:
        return render_owner_daily_checklist_page(session, user)
    if page == "team_onboarding_activation" and session is not None:
        return render_team_onboarding_activation_page(session)
    if page.startswith("fortuna_action_log") and session is not None:
        parts = page.split(":")
        window = parts[1] if len(parts) > 1 else "today"
        return render_fortuna_action_log_page(session, window)
    if page == "agency_activation" and session is not None:
        return render_agency_activation_page(session)
    if page.startswith("agency_activation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 4 and parts[1] == "blocker":
            section = parts[2]
            index = int(parts[3]) if parts[3].isdigit() else 0
            if len(parts) >= 5 and parts[4] == "fix":
                blocker = find_activation_blocker(session, section, index)
                if blocker and blocker.get("action_page"):
                    return render_page(blocker["action_page"], session=session, user=user)
            explain = len(parts) >= 5 and parts[4] == "explain"
            return render_activation_blocker_detail_page(session, section, index, explain=explain)
        if len(parts) >= 2 and parts[1] == "accounts":
            return render_account_setup_state_page(session)
        section = parts[1] if len(parts) >= 2 else "models"
        return render_activation_section_page(session, section)
    if page in {"setup:wizard", "setup:wizard:start"} and session is not None:
        return render_setup_wizard_page(session, user)
    if page == "setup:wizard:model":
        return render_setup_model_prompt_page()
    if page == "setup:wizard:accounts" and session is not None:
        return render_setup_accounts_page(session, user)
    if page.startswith("setup:wizard:accounts:platform:") and session is not None:
        return render_setup_account_input_page(session, user, page.split(":")[-1])
    if page == "setup:wizard:team" and session is not None:
        return render_setup_team_page(session, user)
    if page.startswith("setup:wizard:team:assign:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 5:
            return render_setup_team_page(session, user, parts[4])
    if page == "setup:wizard:creators" and session is not None:
        return render_setup_creators_page(session, user)
    if page == "setup:wizard:opportunities" and session is not None:
        return render_setup_opportunities_page(session, user)
    if page in {"setup:wizard:summary", "setup:wizard:finish"} and session is not None:
        return render_setup_summary_page(session, user)
    if page in {"setup:cleanup", "setup:cleanup:archive_placeholders"} and session is not None:
        return render_placeholder_cleanup_page(session)
    if page == "first_day_plan" and session is not None and user is not None:
        return render_first_day_plan_page(session, user)
    if page == "manager_qa" and session is not None:
        return render_manager_setup_qa_page(session)
    if page.startswith("demo"):
        return render_demo_seed_page()
    if page == "daily_experience" and session is not None and user is not None:
        return render_daily_experience_page(session, user)
    if page == "performance" and session is not None and user is not None:
        return render_performance_page(session, user)
    if page == "help":
        return render_help_center_page(user)
    if page.startswith("help_from:"):
        body = page.removeprefix("help_from:")
        if ":topic:" in body:
            source_page, topic = body.split(":topic:", 1)
            return render_help_topic_page(topic, user, source_page=source_page)
        return render_help_center_page(user, source_page=body)
    if page.startswith("help:"):
        return render_help_topic_page(page.split(":", 1)[1], user)
    if page == "help_copilot" and session is not None:
        return render_help_copilot_page(session, user)
    if page.startswith("help_copilot_from:") and session is not None:
        body = page.removeprefix("help_copilot_from:")
        if ":question:" in body:
            source_page, question = body.split(":question:", 1)
            return render_help_copilot_page(session, user, question=question, source_page=source_page)
        return render_help_copilot_page(session, user, source_page=body)
    if page.startswith("help_copilot:question:") and session is not None:
        return render_help_copilot_page(session, user, question=page.split(":question:", 1)[1])
    if page.startswith("help_copilot:") and session is not None:
        return render_help_copilot_page(session, user, question=page.split(":", 1)[1])
    if page == "notification_group_pilot" and session is not None:
        return render_notification_group_pilot_page(session)
    if page == "ui_self_test" and session is not None:
        return render_ui_self_test_page(session, user)
    if page == "ui_self_test:run" and session is not None:
        return render_ui_self_test_page(session, user, run_now=True)
    if page == "ui_self_test:details" and session is not None:
        return render_ui_self_test_page(session, user, details=True)
    if page in {"button_health", "button_health:run"} and session is not None:
        return render_button_health_report_page(session, user, run_now=page.endswith(":run"))
    if page == "button_health:details" and session is not None:
        return render_button_health_report_page(session, user, details=True)
    if page == "callback_failure_review" and session is not None:
        return render_callback_failure_review_page(session, user)
    if page == "debug_last_error" and session is not None:
        return render_debug_last_error_page(session, user)
    if page.startswith("callback_error:report"):
        return render_callback_problem_reported_page()
    if page == "chatter_workspace" and session is not None and user is not None:
        return render_chatter_workspace_page(session, user)
    if page == "my_models" and session is not None and user is not None:
        return render_my_models_page(session, user)
    if page == "my_accounts" and session is not None and user is not None:
        return render_my_accounts_page(session, user)
    if page == "my_opportunities" and session is not None and user is not None:
        return render_my_opportunities_page(session, user)
    if page == "uploads":
        return render_uploads_placeholder_page()
    if page == "client_dashboard" and session is not None and user is not None:
        return render_client_dashboard_page(session, user)
    if page == "my_reports" and session is not None and user is not None:
        return render_my_reports_page(session, user)
    if page == "my_team" and session is not None and user is not None:
        return render_my_team_page(session, user)
    if page == "team_qa" and session is not None:
        return render_team_qa_page(session)
    if page == "team_activation" and session is not None:
        return render_team_activation_page(session)
    if page.startswith("team_qa:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_team_qa_detail_page(session, int(parts[1]))
    if page == "notification_digest" and session is not None:
        return render_notification_digest_mode_page(session, user=user)
    if page == "notification_digest:generate" and session is not None:
        return render_notification_digest_mode_page(session, user=user, generate=True)
    if page == "automations:scheduled" and session is not None:
        return render_scheduled_automations_page(session, user=user)
    if page == "automations:scheduled:run_due" and session is not None:
        return render_scheduled_automations_page(session, user=user, run_due=True)
    if page == "automations:daily_autopilot" and session is not None:
        return render_daily_autopilot_page(session, user=user)
    if page == "proxies":
        return render_proxies_home(session)
    if page == "proxies:add":
        return render_proxy_add_page()
    if page == "proxies:advanced":
        return render_proxy_advanced_page()
    if page == "proxies:rotation_help":
        return render_proxy_rotation_help_page()
    if page == "proxies:cleanup_result" and session is not None:
        return render_proxy_cleanup_result_page(session)
    if page == "proxies:list" and session is not None:
        return render_proxy_list_page(session)
    if page == "proxies:entry_check" and session is not None:
        return render_proxy_entry_check_page(session)
    if page == "proxies:real_check_pilot" and session is not None:
        return render_proxy_real_check_pilot_page(session)
    if page == "proxies:olympix":
        return render_olympix_proxy_wizard_page()
    if page == "proxies:olympix:paste":
        return render_olympix_proxy_paste_page(session)
    if page == "proxies:olympix:manual":
        return render_olympix_proxy_wizard_page()
    if page == "proxies:missing" and session is not None:
        return render_accounts_missing_proxy_page(session)
    if page == "proxies:simulation" and session is not None:
        return render_proxy_simulation_page(session)
    if page == "proxies:dashboard" and session is not None:
        return render_infrastructure_dashboard_page(session)
    if page.startswith("proxy:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            proxy_id = int(parts[1])
            if len(parts) == 2:
                return render_proxy_detail_page(session, proxy_id)
            if parts[2] == "manage":
                return render_proxy_manage_page(session, proxy_id)
            if parts[2] == "archive_confirm":
                return render_proxy_archive_confirm_page(session, proxy_id)
            if parts[2] == "archive_result":
                return render_proxy_archive_result_page()
            if parts[2] == "delete_confirm":
                return render_proxy_delete_confirm_page(session, proxy_id)
            if parts[2] == "delete_result":
                return render_proxy_delete_result_page()
            if parts[2] == "rotate_preview":
                return render_proxy_rotation_preview_page(session, proxy_id)
            if parts[2] == "rotated":
                history_id = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else None
                return render_proxy_rotation_result_page(session, proxy_id, history_id)
            if parts[2] == "rollback_result":
                history_id = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else None
                return render_proxy_rollback_result_page(session, proxy_id, history_id)
            if parts[2] == "rollback_empty":
                return render_proxy_no_rollback_page(session, proxy_id)
            if parts[2] == "check_result":
                return render_proxy_check_result_page(session, proxy_id)
            if parts[2] == "location":
                return render_proxy_location_page(session, proxy_id)
            if parts[2] == "advanced":
                return render_proxy_detail_advanced_page(session, proxy_id)
            if parts[2] == "imported":
                return render_proxy_import_success_page(session, proxy_id)
            if parts[2] == "assign":
                return render_proxy_assign_account_page(session, proxy_id)
            if parts[2] == "remove":
                return render_proxy_remove_account_page(session, proxy_id)
            if parts[2] == "accounts":
                return render_proxy_assigned_accounts_page(session, proxy_id)
            if parts[2] == "audit":
                return render_proxy_audit_page(session, proxy_id)
            if parts[2] == "history":
                return render_proxy_check_history_page(session, proxy_id)
            return render_proxy_detail_page(session, proxy_id)
    if page == "accounts":
        return render_accounts_home()
    if page == "accounts:list" and session is not None:
        return render_account_list_page(session)
    if page == "accounts:add" and session is not None:
        return render_account_model_choice_page(session)
    if page.startswith("accounts:add:model:") and session is not None:
        parts = page.split(":")
        if len(parts) == 4 and parts[3].isdigit():
            return render_account_platform_choice_page(session, int(parts[3]))
        if len(parts) >= 6 and parts[3].isdigit() and parts[4] == "platform":
            return render_account_input_page(session, int(parts[3]), parts[5])
    if page == "accounts:by_model" and session is not None:
        return render_accounts_by_model_page(session)
    if page.startswith("accounts:model:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            model_brand = session.get(ModelBrand, int(parts[2]))
            title = f"Accounts for {model_brand.display_name}" if model_brand else "Accounts"
            return render_account_list_page(
                session,
                accounts=accounts_for_model(session, int(parts[2])),
                title=title,
                back_to="accounts:by_model",
            )
    if page == "accounts:by_platform":
        return render_accounts_by_platform_page()
    if page.startswith("accounts:platform:") and session is not None:
        platform = page.split(":")[2]
        filtered = [account for account in list_accounts(session) if account.platform == platform]
        return render_account_list_page(
            session,
            accounts=filtered,
            title=f"{platform_label(platform)} Accounts",
            back_to="accounts:by_platform",
        )
    if page == "accounts:attention" and session is not None:
        return render_account_list_page(
            session,
            accounts=accounts_needing_attention(session),
            title="Accounts Needing Attention",
            back_to="accounts",
        )
    if page.startswith("account:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            account_id = int(parts[1])
            if len(parts) == 2:
                return render_account_detail_page(session, account_id)
            if parts[2] == "audit":
                return render_account_audit_page(session, account_id)
            if parts[2] == "auth" and len(parts) >= 4 and parts[3] == "enter":
                return render_account_auth_prompt_page(session, account_id)
            if parts[2] == "proxy" and len(parts) >= 4 and parts[3] == "assign":
                return render_account_proxy_assignment_page(session, account_id)
            return render_account_detail_page(session, account_id)
    if page == "models":
        return render_models_home()
    if page in {"models:list", "models:search"} and session is not None:
        return render_model_list_page(session)
    if page == "models:dashboard" and session is not None:
        return render_model_dashboard_page(session)
    if page.startswith("model:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            model_id = int(parts[1])
            if len(parts) == 2:
                return render_model_detail_page(session, model_id)
            if parts[2] == "edit":
                if len(parts) >= 4:
                    return render_model_field_edit_page(session, model_id, parts[3])
                return render_model_edit_page(session, model_id)
            if parts[2] == "complete":
                return render_model_completion_page(session, model_id)
            if parts[2] == "team":
                if len(parts) >= 5 and parts[3] == "assign":
                    return render_model_assignment_page(session, model_id, parts[4])
                if len(parts) >= 4 and parts[3] == "remove":
                    return render_model_remove_assignment_page(session, model_id)
                return render_model_team_page(session, model_id)
            if parts[2] == "audit":
                return render_model_audit_page(session, model_id)
            if parts[2] == "accounts":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Accounts for {model_brand.display_name}" if model_brand else "Accounts"
                return render_account_list_page(
                    session,
                    accounts=accounts_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
            if parts[2] == "creators":
                return render_model_creators_page(session, model_id)
            if parts[2] == "opportunities":
                return render_model_opportunities_page(session, model_id)
            if parts[2] == "tasks":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Tasks for {model_brand.display_name}" if model_brand else "Tasks"
                return render_task_list_page(
                    session,
                    tasks=tasks_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
            if parts[2] == "incidents":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Incidents for {model_brand.display_name}" if model_brand else "Incidents"
                return render_incident_list_page(
                    session,
                    incidents=incidents_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
    if page == "tasks":
        return render_tasks_home()
    if page == "tasks:list" and session is not None:
        return render_task_list_page(session)
    if page == "tasks:my" and session is not None and user is not None:
        return render_task_list_page(session, tasks=my_tasks(session, user), title="My Tasks", back_to="tasks")
    if page == "tasks:assigned" and session is not None:
        return render_task_list_page(
            session,
            tasks=assigned_tasks(session),
            title="Assigned Tasks",
            back_to="tasks",
        )
    if page == "tasks:team" and session is not None:
        return render_task_list_page(
            session,
            tasks=assigned_tasks(session),
            title="Team Tasks",
            back_to="tasks",
        )
    if page == "tasks:overdue" and session is not None:
        return render_task_list_page(session, tasks=overdue_tasks(session), title="Overdue Tasks", back_to="tasks")
    if page == "tasks:blocked" and session is not None:
        return render_task_list_page(session, tasks=blocked_tasks(session), title="Blocked Tasks", back_to="tasks")
    if page == "tasks:escalated" and session is not None:
        escalated = [task for task in list_tasks(session) if task.escalation_level > 0]
        return render_task_list_page(session, tasks=escalated, title="Escalated Tasks", back_to="tasks")
    if page.startswith("task:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            task_id = int(parts[1])
            if len(parts) >= 3 and parts[2] == "assign":
                return render_task_assignment_page(session, task_id)
            return render_task_detail_page(session, task_id)
    if page == "incidents":
        return render_incidents_home()
    if page == "incidents:list" and session is not None:
        return render_incident_list_page(session)
    if page == "incidents:open" and session is not None:
        return render_incident_list_page(
            session,
            incidents=open_incidents(session),
            title="Open Incidents",
            back_to="incidents",
        )
    if page == "incidents:my" and session is not None and user is not None:
        return render_incident_list_page(
            session,
            incidents=my_incidents(session, user),
            title="My Incidents",
            back_to="incidents",
        )
    if page == "incidents:critical" and session is not None:
        return render_incident_list_page(
            session,
            incidents=critical_incidents(session),
            title="Critical Incidents",
            back_to="incidents",
        )
    if page.startswith("incident:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            incident_id = int(parts[1])
            if len(parts) >= 3 and parts[2] == "assign":
                return render_incident_assignment_page(session, incident_id)
            if len(parts) >= 3 and parts[2] == "timeline":
                return render_incident_timeline_page(session, incident_id)
            return render_incident_detail_page(session, incident_id)
    if page == "reports":
        return render_reports_home()
    if page in {"reports:daily", "reports:daily:generate"} and session is not None:
        return render_daily_briefing_page(session, user=user)
    if page == "reports:daily:latest" and session is not None:
        return render_daily_briefing_page(session, user=user, mode="latest")
    if page in {"reports:daily:send_owner", "reports:daily:send_ops"} and session is not None:
        target = "owner" if page.endswith("send_owner") else "operations"
        request_briefing_send(session, actor=user, target=target)
        return render_daily_briefing_page(session, user=user, mode="latest")
    if page == "reports:accountability" and session is not None:
        return render_accountability_page(session, user=user)
    if page in {"reports:intelligence", "reports:intelligence:generate"} and session is not None:
        return render_intelligence_briefing_page(session, user=user)
    if page == "reports:intelligence:latest" and session is not None:
        return render_intelligence_briefing_page(session, user=user, mode="latest")
    if page == "reports:intelligence:send_hq" and session is not None:
        return render_intelligence_briefing_page(session, user=user, mode="send_hq")
    if page == "reports:workload" and session is not None:
        return render_workload_intelligence_page(session, user=user)
    if page == "reports:digest" and session is not None:
        return render_daily_digest_page(session, user=user)
    if page == "reports:digest:generate" and session is not None:
        return render_daily_digest_page(session, user=user, mode="generate")
    if page == "reports:digest:preview" and session is not None:
        return render_daily_digest_page(session, user=user, mode="preview")
    if page == "reports:digest:send_hq" and session is not None:
        return render_daily_digest_page(session, user=user, mode="send", purpose="owner")
    if page == "reports:digest:send_ops" and session is not None:
        return render_daily_digest_page(session, user=user, mode="send", purpose="operations")
    if page == "reports:digest:schedule" and session is not None:
        return render_daily_digest_page(session, user=user, mode="schedule")
    if page == "reports:digest:history" and session is not None:
        return render_daily_digest_page(session, user=user, mode="history")
    if page == "reports:executive" and session is not None:
        return render_executive_dashboard_page(session, user=user)
    if page == "reports:executive:recommendations" and session is not None:
        return render_recommendations_page(session, user=user)
    if page.startswith("recommendation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "why":
                return render_recommendation_why_page(session, int(parts[1]))
            return render_recommendation_detail_page(session, int(parts[1]))
    if page == "reports:operations" and session is not None:
        return render_operations_dashboard_page(session, user=user)
    if page == "reports:manager" and session is not None:
        return render_manager_command_page(session, user=user)
    if page == "reports:chatter" and session is not None:
        return render_chatter_dashboard_page(session, user=user)
    if page == "reports:va" and session is not None:
        return render_va_dashboard_page(session, user=user)
    if page == "intelligence" and session is not None:
        return render_intelligence_home(session)
    if page == "intelligence:details" and session is not None:
        return render_intelligence_details_page(session)
    if page == "intelligence:quality" and session is not None:
        return render_intelligence_quality_page(session, user)
    if page == "intelligence:quality:details" and session is not None:
        return render_intelligence_quality_page(session, user, details=True)
    if page == "intelligence:quality:trends" and session is not None:
        return render_decision_quality_trends_page(session, user)
    if page == "intelligence:quality:trends:details" and session is not None:
        return render_decision_quality_trends_page(session, user, details=True)
    if page == "intelligence:quality:categories" and session is not None:
        return render_category_trends_page(session, user)
    if page == "prediction:preview" and session is not None:
        return render_prediction_preview_page(session, user)
    if page == "prediction:preview:details" and session is not None:
        return render_prediction_preview_page(session, user, details=True)
    if page.startswith("prediction:feedback:") and session is not None:
        return render_prediction_feedback_page(session, page.split(":")[-1], user)
    if page.startswith("prediction:outcome:") and session is not None:
        return render_prediction_outcome_feedback_page(session, page.split(":")[-1], user)
    if page == "reality:check" and session is not None:
        return render_reality_check_page(session, user)
    if page == "reality:check:details" and session is not None:
        return render_reality_check_page(session, user, details=True)
    if page == "reality:outcomes" and session is not None:
        return render_prediction_outcomes_page(session, user)
    if page == "reality:calibration" and session is not None:
        return render_calibration_page(session, user)
    if page == "reality:accuracy" and session is not None:
        return render_accuracy_by_category_page(session, user)
    if page == "decision:review" and session is not None:
        return render_decision_review_page(session, user)
    if page == "decision:review:details" and session is not None:
        return render_decision_review_page(session, user, details=True)
    if page.startswith("owner_validation:") and session is not None:
        return render_owner_validation_page(session, page.split(":")[-1], user)
    if page == "evidence:notes" and session is not None:
        return render_evidence_notes_page(session, user)
    if page == "evidence:notes:record" and session is not None:
        return render_evidence_notes_page(session, user, record_note=True)
    if page == "knowledge:memory" and session is not None:
        return render_knowledge_memory_page(session, user)
    if page == "knowledge:memory:create" and session is not None:
        return render_knowledge_memory_page(session, user, create_lesson=True)
    if page == "decision:timeline" and session is not None:
        return render_decision_timeline_page(session, user)
    if page == "intelligence:runs" and session is not None:
        return render_intelligence_runs_page(session)
    if page.startswith("intelligence:run_detail:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            return render_intelligence_run_detail_page(session, int(parts[2]))
    if page == "intelligence:signals" and session is not None:
        return render_intelligence_signals_page(session)
    if page == "intelligence:patterns" and session is not None:
        return render_intelligence_patterns_page(session)
    if page == "intelligence:trends" and session is not None:
        return render_intelligence_trends_page(session)
    if page == "intelligence:trends:details" and session is not None:
        return render_intelligence_trend_details_page(session)
    if page == "intelligence:learning" and session is not None:
        return render_learning_center_page(session)
    if page == "intelligence:learning:details" and session is not None:
        return render_learning_details_page(session)
    if page == "intelligence:learning:playbooks" and session is not None:
        return render_playbooks_page(session)
    if page == "intelligence:learning:recommended" and session is not None:
        return render_playbooks_page(session, recommended=True)
    if page == "intelligence:learning:outcome_memory" and session is not None:
        return render_outcome_memory_page(session)
    if page == "intelligence:learning:confidence" and session is not None:
        return render_confidence_changes_page(session)
    if page == "intelligence:learning:automation" and session is not None:
        return render_automation_learning_page(session)
    if page == "intelligence:learning:opportunity" and session is not None:
        return render_opportunity_learning_page(session)
    if page == "intelligence:learning:briefing" and session is not None:
        return render_executive_memory_briefing_page(session)
    if page.startswith("playbook:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "history":
                return render_playbook_history_page(session, int(parts[1]))
            return render_playbook_detail_page(session, int(parts[1]))
    if page == "opportunities" and session is not None:
        return render_opportunities_home(session)
    if page.startswith("opportunities:creators:add") and session is not None:
        return render_creator_intake_page(session, page)
    if page.startswith("opportunities:posts:add") and session is not None:
        return render_post_intake_page(session, page)
    if page.startswith("opportunities:add") and session is not None:
        return render_opportunity_intake_page(session, page)
    if page == "opportunities:command" and session is not None:
        return render_opportunity_command_center_page(session, user=user)
    if page == "opportunities:score" and session is not None:
        return render_social_opportunity_intelligence_page(session)
    if page == "opportunities:best" and session is not None:
        return render_best_opportunity_page(session, user=user)
    if page == "opportunities:discovery" and session is not None:
        return render_social_discovery_page(session)
    if page == "opportunities:discovery:add_source":
        return render_social_discovery_instruction_page("add_source")
    if page == "opportunities:discovery:paste_post":
        return render_social_discovery_instruction_page("paste_post")
    if page == "opportunities:discovery:leads" and session is not None:
        return render_social_discovery_leads_page(session)
    if page == "opportunities:profiles" and session is not None:
        return render_comment_profile_leads_page(session, user=user)
    if page == "opportunities:comments" and session is not None:
        return render_comment_section_review_page(session, user=user)
    if page == "opportunities:list" and session is not None:
        return render_opportunity_list_page(session)
    if page == "opportunities:creators" and session is not None:
        return render_creator_watchlist_page(session)
    if page == "opportunities:posts" and session is not None:
        return render_post_watch_page(session)
    if page == "opportunities:posts:attention" and session is not None:
        return render_post_watch_page(session, status="attention_needed")
    if page == "opportunities:manager" and session is not None:
        return render_manager_opportunity_page(session)
    if page == "opportunities:learning" and session is not None:
        return render_opportunity_learning_v2_page(session)
    if page == "opportunities:results" and session is not None:
        return render_opportunity_results_page(session)
    if page.startswith("creator:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign_model":
                return render_creator_model_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "assign_chatter":
                return render_creator_chatter_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "priority":
                return render_creator_priority_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "niche":
                return Screen("Edit Niche\n\nSend the new niche in chat.", page_menu(back_to=f"creator:{parts[1]}"))
            if len(parts) >= 3 and parts[2] == "alert":
                return render_creator_post_alert_prompt_page(session, int(parts[1]))
            return render_creator_watch_detail_page(session, int(parts[1]))
    if page.startswith("creator_alert:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            alert = session.get(CreatorPostAlert, int(parts[1]))
            if alert is not None and len(parts) >= 3 and parts[2] == "reviewed":
                mark_creator_post_alert_reviewed(session, alert, actor=user)
            return render_creator_post_alert_detail_page(session, int(parts[1]))
    if page.startswith("post:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign_chatter":
                return render_post_chatter_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "alert":
                return render_own_post_alert_prompt_page(session, int(parts[1]))
            return render_post_watch_detail_page(session, int(parts[1]))
    if page.startswith("own_post_alert:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            alert = session.get(OwnPostAlert, int(parts[1]))
            if alert is not None and len(parts) >= 3 and parts[2] == "reviewed":
                mark_own_post_alert_reviewed(session, alert, actor=user)
            return render_own_post_alert_detail_page(session, int(parts[1]))
    if page.startswith("opportunity:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign":
                return render_opportunity_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "status":
                return render_opportunity_status_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "record_result":
                return render_opportunity_result_status_page(session, int(parts[1]))
            if len(parts) >= 4 and parts[2] == "result":
                return Screen(
                    f"Record Result\n\nStatus: {parts[3]}\nSend safe notes or type skip.",
                    page_menu(back_to=f"opportunity:{parts[1]}"),
                )
            if len(parts) >= 3 and parts[2] == "strategies":
                return render_opportunity_strategies_page(session, int(parts[1]))
            return render_opportunity_detail_page(session, int(parts[1]))
    if page.startswith("opportunity_prediction:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_opportunity_prediction_detail_page(session, int(parts[1]))
    if page.startswith("social_score:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 3 and parts[1].isdigit():
            return render_social_score_action_page(session, int(parts[1]), parts[2], user=user)
    if page.startswith("social_lead:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3:
                return render_social_discovery_lead_action_page(session, int(parts[1]), parts[2], user=user)
            return render_social_discovery_lead_detail_page(session, int(parts[1]))
    if page.startswith("social_profile:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3:
                return render_social_profile_action_page(session, int(parts[1]), parts[2], user=user)
            return render_social_profile_detail_page(session, int(parts[1]), user=user)
    if page == "users" and session is not None:
        return render_users_page(session)
    if page == "users:pending" and session is not None:
        return render_users_page(session, status_filter="pending")
    if page.startswith("user:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"assign_role", "remove_role"}:
                return render_role_assignment_page(session, int(parts[1]), parts[2])
            return render_user_detail_page(session, int(parts[1]))
    if page == "roles" and session is not None:
        return render_roles_page(session)
    if page.startswith("role:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"add_permission", "remove_permission"}:
                return render_permission_list_page(session, int(parts[1]), parts[2])
            return render_role_detail_page(session, int(parts[1]))
    if page == "permissions":
        return render_default_permissions_page()
    if page == "automations" and session is not None:
        return render_automations_home(session, user=user)
    if page == "automations":
        return render_automations_home()
    if page == "automations:rules" and session is not None:
        return render_automation_rules_page(session, user=user)
    if page == "automations:templates" and session is not None:
        return render_automation_templates_page(session, user=user)
    if page == "automations:approvals" and session is not None:
        return render_automation_approvals_page(session)
    if page == "automations:runs" and session is not None:
        return render_automation_runs_page(session)
    if page == "automations:health" and session is not None:
        return render_automation_health_page(session)
    if page.startswith("automation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            rule_id = int(parts[1])
            if len(parts) == 2:
                return render_automation_rule_detail_page(session, rule_id)
            if parts[2] == "simulations":
                return render_automation_rule_simulations_page(session, rule_id)
            if parts[2] == "rollback":
                return render_automation_rollback_page(session, rule_id)
            if parts[2] == "runs":
                return render_automation_runs_page(session, rule_id=rule_id)
            return render_automation_rule_detail_page(session, rule_id)
    if page.startswith("approval:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_approval_detail_page(session, int(parts[1]))
    if page.startswith("automation_run:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_run_detail_page(session, int(parts[1]))
    if page.startswith("automation_step:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_step_detail_page(session, int(parts[1]))
    if page == "automations:simulations" and session is not None:
        return render_simulation_runs_page(session)
    if page.startswith("simulation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_simulation_run_detail_page(session, int(parts[1]))
    if page == "audit_logs" and session is not None:
        return render_audit_logs_page(session, user)
    if page == "audit_logs:details" and session is not None:
        return render_audit_logs_page(session, user, details=True)
    if page == "audit_logs:issues" and session is not None:
        return render_audit_logs_page(session, user, issues_only=True)
    if page in {"bot_status", "production_status"} and session is not None:
        return render_bot_status_page(session, user)
    if page == "bot_status:details" and session is not None:
        return render_bot_status_page(session, user, details=True)
    if page == "production_observability" and session is not None:
        return render_production_observability_page(session, user)
    if page == "production_observability:details" and session is not None:
        return render_production_observability_page(session, user, details=True)
    if page == "bot_instance_status" and session is not None:
        return render_botstatus_page(session, user)
    if page == "bot_instance_status:details" and session is not None:
        return render_botstatus_page(session, user, details=True)
    if page == "integrity" and session is not None:
        return render_integrity_page(session, user)
    if page == "integrity:details" and session is not None:
        return render_integrity_page(session, user, details=True)
    if page == "settings:report_problem":
        return render_report_problem_page()
    if page == "settings:report_problem:start":
        return render_report_problem_page(started=True)
    if page == "settings:report_problem:saved":
        return render_problem_report_saved_page()
    if page == "availability" and session is not None and user is not None:
        return render_availability_page(session, user)
    if page == "availability:team" and session is not None:
        return render_team_availability_page(session)
    if page.startswith("onboarding") and session is not None and user is not None:
        parts = page.split(":")
        step = parts[2] if len(parts) >= 3 and parts[1] == "reset" else None
        return render_onboarding_page(session, user, step=step)
    if page == "notification_targets" and session is not None:
        return render_notification_targets_page(session)
    if page == "notification_group_setup" and session is not None:
        return render_notification_group_setup_page(session)
    if page == "notification_routing" and session is not None:
        return render_notification_routing_page(session)
    if page == "notification_targets:routing_test" and session is not None:
        return render_notification_routing_test_page(session)
    if page.startswith("notification_target:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "purpose":
                return render_notification_target_purpose_page(session, int(parts[1]))
            return render_notification_target_detail_page(session, int(parts[1]))
    if page == "settings":
        return Screen(text="Settings\n\nAdministrative tools.", reply_markup=settings_menu())
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
