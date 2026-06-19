from .formatting import *

def render_setup_wizard_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    lines = [
        "Fortuna Setup Wizard",
        "",
        "Use this to make Fortuna OS usable for the team without guessing where to start.",
        "",
        "Steps:",
        "1. Create Model/Brand",
        "2. Add Accounts",
        "3. Assign Team",
        "4. Add Creator Watchlist Starters",
        "5. Create Starter Opportunities",
        "6. Review Setup Summary",
        "",
        f"Current Model: {model.display_name if model else 'None yet'}",
        f"Accounts Added: {summary['accounts']}",
        f"Team Assigned: {summary['team']}",
        f"Creators Added: {summary['creators']}",
        f"Opportunities Created: {summary['opportunities']}",
    ]
    if summary["missing"]:
        lines.extend(["", "Still Missing:", *[f"- {item.title()}" for item in summary["missing"]]])
    else:
        lines.extend(["", "Setup has the basics. Review and finish when ready."])
    return Screen("\n".join(lines), setup_wizard_menu())

def render_agency_activation_page(session: Session) -> Screen:
    report = build_activation_report(session)
    blockers = report["blockers"]
    recent_actions = recent_operations_activity(session)
    open_blockers = outstanding_blockers(session)
    lines = [
        "Fortuna Activation",
        "",
        f"Fortuna Readiness: {_status_marker('healthy' if report['readiness_score'] >= 85 else 'warning' if report['readiness_score'] >= 60 else 'critical')} {report['readiness_score']}% ({_readiness_label(report['readiness_score'])})",
        "",
        f"Models Ready: {report['models_ready']}%",
        f"Accounts Ready: {report['accounts_ready']}%",
        f"Teams Ready: {report['teams_ready']}%",
        f"Creators Ready: {report['creators_ready']}%",
        f"Opportunities Ready: {report['opportunities_ready']}%",
        f"Notifications Ready: {report['notifications_ready']}%",
        "",
        "Top Blockers:",
    ]
    if not blockers:
        lines.append("- None. Setup is ready for daily operations.")
    for blocker in blockers[:6]:
        lines.append(f"- {blocker['title']}")
    lines.extend(["", "What Fortuna OS Did Today:"])
    lines.extend(f"- {item}" for item in recent_actions[:4])
    if not recent_actions:
        lines.append("- No autonomous actions recorded yet.")
    lines.extend(["", "Outstanding Blockers:"])
    lines.extend(f"- {item}" for item in open_blockers[:4])
    if not open_blockers:
        lines.append("- No autonomous blockers currently open.")
    lines.extend(
        [
            "",
            "Run Activation Scan to save this readiness snapshot, refresh recommendations, and create setup tasks without duplicates.",
        ]
    )
    return Screen("\n".join(lines), agency_activation_menu())

def render_activation_section_page(session: Session, section: str) -> Screen:
    report = build_activation_report(session)
    blockers = [blocker for blocker in report["blockers"] if blocker.get("section") == section]
    title = {
        "models": "Fix Models",
        "accounts": "Fix Accounts",
        "team": "Fix Team",
        "creators": "Fix Creators",
        "opportunities": "Fix Opportunities",
        "notifications": "Fix Notifications",
    }.get(section, "Fix Setup")
    lines = [title, ""]
    if not blockers:
        lines.append("Nothing blocking this area right now.")
    for blocker in blockers[:10]:
        lines.append(f"- {blocker['title']}")
        lines.append(f"  Next: {blocker['description']}")
    choices: list[tuple[str, str]] = []
    for index, blocker in enumerate(blockers[:8]):
        choices.append((blocker["title"][:40], f"nav:agency_activation:blocker:{section}:{index}"))
        if blocker.get("action_page"):
            choices.append((f"Fix Now: {blocker['title'][:31]}", f"nav:{blocker['action_page']}"))
    choices.append(("Run Activation Scan", "nav:agency_activation:scan"))
    if not choices:
        return Screen("\n".join(lines), activation_section_menu(section))
    return Screen("\n".join(lines), choice_menu(choices, back_to="agency_activation"))

def render_activation_blocker_detail_page(session: Session, section: str, index: int, *, explain: bool = False) -> Screen:
    blocker = find_activation_blocker(session, section, index)
    if blocker is None:
        return Screen("This blocker is no longer active.", activation_section_menu(section))
    lines = [
        "Setup Blocker",
        "",
        blocker["title"],
        "",
        f"Status: {_status_marker(blocker.get('severity', 'warning'))} {blocker.get('severity', 'warning').title()}",
        f"Area: {section.title()}",
        "",
        "What is happening:",
        blocker["description"],
        "",
        "What to do next:",
        "Use Fix Now to open the exact setup screen. Use Skip for Later if this is real but not today's priority. Use Mark Not Needed only when this blocker does not apply to your agency.",
    ]
    if explain:
        lines.extend(
            [
                "",
                "Why this matters:",
                "Fortuna OS uses this signal to decide readiness, create setup tasks, and route work to the right person. Closing irrelevant blockers keeps the owner checklist focused.",
            ]
        )
    return Screen(
        "\n".join(lines),
        activation_blocker_detail_menu(section, index, blocker.get("action_page")),
    )

def render_model_completion_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="agency_activation:models"))
    accounts = accounts_for_model(session, model_id)
    creators = [creator for creator in list_creator_watches(session) if creator.assigned_model_id == model_id]
    opportunities = [opportunity for opportunity in list_opportunities(session) if opportunity.model_brand_id == model_id]
    relationship_types = {member.relationship_type for member in model_brand.members}
    checks = [
        ("Country", model_brand.country),
        ("Timezone", model_brand.timezone),
        ("Primary Platform", model_brand.primary_platform),
        ("Team", "assigned" if relationship_types else None),
        ("Accounts", str(len(accounts)) if accounts else None),
        ("Creators", str(len(creators)) if creators else None),
        ("Opportunities", str(len(opportunities)) if opportunities else None),
    ]
    lines = [
        "Model Completion Wizard",
        "",
        f"Model: {model_brand.display_name}",
        f"Status: {model_brand.status}",
        "",
        "Setup Checklist:",
    ]
    for label, value in checks:
        marker = "Done" if value else "Needs setup"
        lines.append(f"- {label}: {marker}{f' ({value})' if value else ''}")
    lines.extend(
        [
            "",
            "Use the buttons below to fill the missing pieces. You can come back here anytime from Fortuna Activation.",
        ]
    )
    return Screen("\n".join(lines), model_completion_menu(model_id))

def render_account_setup_state_page(session: Session) -> Screen:
    states = account_setup_states(session)
    lines = ["Account Setup State", ""]
    buttons: list[tuple[str, str]] = []
    if not states:
        lines.append("No accounts yet. Create a model first, then add IG/X/OF/Email account records without passwords.")
    for state in states[:12]:
        lines.append(f"{state.platform.title()} @{state.username}")
        lines.append(f"   Model: {state.model_name} | Status: {state.status}")
        lines.append(f"   Checklist: {', '.join(state.checklist)}")
        if state.recommended_actions:
            lines.append(f"   Next: {state.recommended_actions[0]}")
        buttons.append((f"{state.platform.title()} @{state.username}", f"nav:account:{state.account_id}"))
    return Screen("\n".join(lines), account_setup_state_menu(buttons))

def render_setup_model_prompt_page() -> Screen:
    lines = [
        "Create First Model",
        "",
        "Send the model/brand details in this format:",
        "",
        "Display Name | Stage Name | Country | Timezone | Notes",
        "",
        "Example:",
        "Fortuna Solstice | Fortuna | United States | America/New_York | Launch profile",
        "",
        "You can type skip for optional notes.",
    ]
    return Screen("\n".join(lines), page_menu(back_to="setup:wizard"))

def render_setup_accounts_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Add Accounts\n\nNo model exists yet. Create your first model/brand before adding IG/X/OF accounts.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    choices = [
        ("Instagram", "nav:setup:wizard:accounts:platform:instagram"),
        ("X", "nav:setup:wizard:accounts:platform:x"),
        ("OnlyFans", "nav:setup:wizard:accounts:platform:onlyfans"),
        ("Email", "nav:setup:wizard:accounts:platform:email"),
        ("Other", "nav:setup:wizard:accounts:platform:other"),
    ]
    return Screen(
        "\n".join(
            [
                "Add Accounts",
                "",
                f"Model: {model.display_name}",
                "Choose a platform, then send username/display/reference details.",
                "Credential values stay out of Telegram.",
            ]
        ),
        choice_menu(choices, back_to="setup:wizard"),
    )

def render_setup_account_input_page(session: Session, user: User | None, platform: str) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return render_setup_accounts_page(session, user)
    return Screen(
        "\n".join(
            [
                "Add Account",
                "",
                f"Model: {model.display_name}",
                f"Platform: {platform_label(platform)}",
                "",
                "Send:",
                "username | display name | URL/reference | notes",
                "",
                "Never send passwords or 2FA codes here.",
            ]
        ),
        page_menu(back_to="setup:wizard:accounts"),
    )

def render_setup_team_page(session: Session, user: User | None = None, relationship_type: str | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Assign Team\n\nCreate a model/brand first, then assign managers, chatters, and VAs.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    if relationship_type is None:
        choices = [
            ("Assign Manager", "nav:setup:wizard:team:assign:manager"),
            ("Assign Chatter Manager", "nav:setup:wizard:team:assign:chatter_manager"),
            ("Assign Senior Chatter", "nav:setup:wizard:team:assign:senior_chatter"),
            ("Assign Chatter", "nav:setup:wizard:team:assign:chatter"),
            ("Assign VA", "nav:setup:wizard:team:assign:va"),
            ("Skip For Later", "nav:setup:wizard:creators"),
        ]
        return Screen(
            f"Assign Team\n\nModel: {model.display_name}\nChoose the role you want to assign.",
            choice_menu(choices, back_to="setup:wizard"),
        )
    users = active_users_for_assignment(session)
    choices = [
        (_identity(user)[:40], f"nav:setup:wizard:team:assign:{relationship_type}:{user.id}")
        for user in users
    ]
    if not choices:
        return Screen(
            "Assign Team\n\nNo active users available yet. Approve users first, then come back.",
            choice_menu([("Pending Users", "nav:users:pending")], back_to="setup:wizard:team"),
        )
    label = RELATIONSHIP_LABELS.get(relationship_type, relationship_type)
    return Screen(
        f"Assign {label}\n\nModel: {model.display_name}\nPick a team member.",
        choice_menu(choices, back_to="setup:wizard:team"),
    )

def render_setup_creators_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Add Creator Starters\n\nCreate a model/brand first, then add creators worth watching.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    return Screen(
        "\n".join(
            [
                "Add Creator Starters",
                "",
                f"Model: {model.display_name}",
                "Send one creator in this format:",
                "",
                "platform | username | display name | niche | priority",
                "",
                "Example: x | creatorname | Creator Name | fitness | high",
            ]
        ),
        choice_menu([("Use Full Creator Flow", "nav:opportunities:creators:add")], back_to="setup:wizard"),
    )

def render_setup_opportunities_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Create Starter Opportunities\n\nCreate a model/brand first, then create manual opportunities.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    return Screen(
        "\n".join(
            [
                "Create Starter Opportunities",
                "",
                f"Model: {model.display_name}",
                "Send one opportunity in this format:",
                "",
                "title | platform | niche | assigned user id",
                "",
                "Use skip for assigned user id if you want to assign later.",
            ]
        ),
        choice_menu([("Use Full Opportunity Flow", "nav:opportunities:add")], back_to="setup:wizard"),
    )

def render_setup_summary_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    lines = [
        "Setup Summary",
        "",
        f"Model Created: {model.display_name if model else 'No'}",
        f"Accounts Added: {summary['accounts']}",
        f"Team Assigned: {summary['team']}",
        f"Creators Added: {summary['creators']}",
        f"Opportunities Created: {summary['opportunities']}",
        "",
        "Missing Items:",
    ]
    lines.extend(f"- {item.title()}" for item in summary["missing"]) if summary["missing"] else lines.append("- None")
    return Screen("\n".join(lines), setup_finish_menu(model.id if model else None))

def render_first_day_plan_page(session: Session, user: User) -> Screen:
    plan = first_day_plan(session, user)
    lines = [
        "First Day Plan",
        "",
        f"Progress: {plan['completion_score']}%",
        "",
        "Use this checklist to activate the agency cleanly.",
        "",
    ]
    for item in plan["items"]:
        marker = "Done" if item["done"] else "Next"
        lines.append(f"{marker}: {item['label']}")
    return Screen("\n".join(lines), first_day_plan_menu(plan["items"]))

def render_manager_setup_qa_page(session: Session) -> Screen:
    qa = manager_setup_qa(session)
    lines = [
        "Manager Setup / QA",
        "",
        "This shows what still needs a human owner. Use it to clean up setup gaps.",
        "",
        f"Models Without Manager: {len(qa['models_without_manager'])}",
        f"Models Without Chatters: {len(qa['models_without_chatters'])}",
        f"Accounts Without Model: {len(qa['accounts_without_model'])}",
        f"Opportunities Without Assignee: {len(qa['opportunities_without_assignee'])}",
        f"Tasks Without Owner: {len(qa['tasks_without_owner'])}",
        f"Users Pending Approval: {len(qa['users_pending'])}",
        f"Users Without Timezone: {len(qa['users_without_timezone'])}",
        f"Users Without Role: {len(qa['users_without_role'])}",
        f"Users Not Onboarded: {len(qa['users_not_onboarded'])}",
    ]
    return Screen("\n".join(lines), manager_setup_qa_menu())

def render_placeholder_cleanup_page(session: Session) -> Screen:
    summary = placeholder_cleanup_summary(session)
    placeholder_models = summary["placeholder_models"]
    placeholder_opportunities = summary["placeholder_opportunities"]
    unlinked_opportunities = summary["unlinked_opportunities"]
    demo_counts = summary["demo_counts"]
    lines = [
        "Placeholder Cleanup",
        "",
        "Use this when starter records are confusing the setup flow.",
        "Fortuna archives obvious placeholders and keeps real production records safe.",
        "",
        "Placeholder records:",
    ]
    if not placeholder_models and not placeholder_opportunities:
        lines.append("- None found.")
    for model in placeholder_models[:5]:
        lines.append(f"- Model: {model.display_name}")
    for opportunity in placeholder_opportunities[:5]:
        lines.append(f"- Opportunity: {opportunity.title}")
    if unlinked_opportunities:
        lines.extend(["", "Unlinked opportunities:"])
        for opportunity in unlinked_opportunities[:5]:
            lines.append(f"- {opportunity.title}")
    lines.extend(["", "Demo records:"])
    if not any(demo_counts.values()):
        lines.append("- None found.")
    else:
        for label, count in demo_counts.items():
            if count:
                lines.append(f"- {label.title()}: {count}")
    lines.extend(
        [
            "",
            "Safe options:",
            "- Archive placeholders keeps history but removes them from setup blockers.",
            "- Clear demo data only removes records explicitly marked as demo.",
        ]
    )
    choices = []
    if placeholder_models or placeholder_opportunities:
        if placeholder_models:
            choices.append(("Complete Placeholder Model", "nav:setup:cleanup:complete_placeholder"))
        choices.append(("Archive Placeholder Records", "nav:setup:cleanup:archive_placeholders"))
    if unlinked_opportunities:
        choices.append(("Link First Opportunity", "nav:setup:cleanup:link_unlinked_opportunity"))
        choices.append(("Archive First Unlinked Opportunity", "nav:setup:cleanup:archive_unlinked_opportunity"))
    if any(demo_counts.values()):
        choices.append(("Clear Demo Data", "nav:demo:clear"))
    choices.append(("Back to Setup", "nav:setup:wizard"))
    return Screen("\n".join(lines), choice_menu(choices, back_to="setup:wizard"))

def render_demo_seed_page() -> Screen:
    return Screen(
        "\n".join(
            [
                "Demo Seed Mode",
                "",
                "Owner-only test data for learning the UI.",
                "Demo records are marked and can be cleared without touching real records.",
                "",
                "Only create demo data when you intentionally want sample screens.",
            ]
        ),
        demo_seed_menu(),
    )

def render_owner_daily_checklist_page(session: Session, user: User) -> Screen:
    checklist = owner_daily_checklist(session, user)
    next_run = checklist["daily_autopilot_next_run"]
    lines = [
        "Owner Daily Checklist",
        "",
        f"Readiness Score: {checklist['readiness_score']}%",
        f"Owner Approvals Needed: {checklist['approvals_needed']}",
        f"Critical Incidents: {checklist['critical_incidents']}",
        f"Accounts Needing Setup: {checklist['accounts_needing_setup']}",
        f"Opportunities Needing Assignment: {checklist['opportunities_needing_assignment']}",
        f"Follow-Ups Due: {checklist['followups_due']}",
        f"Daily Autopilot: {'Enabled' if checklist['daily_autopilot_enabled'] else 'Disabled'}",
        f"Next Daily Run: {format_user_datetime(user, next_run) if next_run else 'Disabled'}",
        f"Last Daily Result: {checklist['daily_autopilot_last_result']}",
        "",
        "Top Blockers:",
    ]
    if not checklist["top_blockers"]:
        lines.append("- None right now.")
    for blocker in checklist["top_blockers"]:
        lines.append(f"- {blocker['title']}")
    return Screen("\n".join(lines), owner_daily_checklist_menu())

def render_team_onboarding_activation_page(session: Session) -> Screen:
    data = team_onboarding_activation(session)
    pending = data["pending_users"]
    lines = [
        "Team Onboarding Activation",
        "",
        f"Active Team Members: {data['active_team_count']}",
        f"Pending Users: {len(pending)}",
        f"Users Missing Timezone/Country: {data['missing_localization']}",
        "",
    ]
    if data["active_team_count"] == 0:
        lines.extend(
            [
                "No real team users are active yet.",
                "",
                "Invite packet:",
            ]
        )
        for role, message in data["invite_packet"].items():
            first_line = message.splitlines()[0]
            lines.append(f"- {role.title()}: {first_line}")
        lines.extend(
            [
                "",
                "Owner copy path: send the role-specific invite text from docs/team_invite_packet.md or Help Center. Team members press /start, finish language/timezone, then wait for approval.",
            ]
        )
    elif pending:
        lines.append("Pending users are waiting for approval. Approve only known team members, then assign a role immediately.")
        for user_item in pending[:8]:
            lines.append(f"- {user_item.display_name or user_item.username or 'Telegram user'}")
    else:
        lines.append("Team activation is started. Keep checking timezone, availability, and assigned work.")
    return Screen("\n".join(lines), team_onboarding_activation_menu(bool(pending)))

def render_fortuna_action_log_page(session: Session, window: str = "today") -> Screen:
    log = autonomous_action_log(session, window=window)
    lines = [
        "What Fortuna Did",
        "",
        f"Window: {log['window']}",
        f"Actions Created: {log['actions_created']}",
        f"Tasks Created: {log['tasks_created']}",
        f"Recommendations Created: {log['recommendations_created']}",
        f"Follow-Ups Created: {log['followups_created']}",
        f"Automations Run: {log['automations_run']}",
        f"Errors Detected: {log['errors_detected']}",
        "",
        "Recent Actions:",
    ]
    if not log["recent_actions"]:
        lines.append("- No autonomous actions in this window.")
    for action in log["recent_actions"][:8]:
        lines.append(f"- {action['status']}: {action['type']}")
        if action.get("summary"):
            lines.append(f"  {action['summary']}")
    return Screen("\n".join(lines), fortuna_action_log_menu(window))

