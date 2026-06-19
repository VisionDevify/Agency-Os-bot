from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.menu import callback_for, page_controls

from .formatting import *
from app.models.opportunity import CreatorPostAlert, OwnPostAlert
from app.models.social import SocialOpportunityScore
from app.services.social_intelligence import (
    best_social_opportunities,
    create_opportunity_from_social_score,
    engagement_strategies_for_score,
    official_api_adapter_status,
    record_social_outcome,
    social_notification_framework_status,
)

def render_opportunities_home(session: Session | None = None) -> Screen:
    opportunities = list_opportunities(session, limit=5) if session is not None else []
    lines = [
        "Opportunities",
        "",
        "Manual, human-approved opportunity command center.",
        "Use it to decide what deserves attention next. No posting is automated.",
        "",
    ]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet. Add a creator, watch one of your own posts, or create a manual opportunity.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Platform: {opportunity.platform} | Score: {opportunity.score} | Status: {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))


def _social_score_buttons(score: SocialOpportunityScore | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if score is not None:
        rows.extend(
            [
                [InlineKeyboardButton(text="Create Opportunity", callback_data=callback_for(f"social_score:{score.id}:create_opportunity"))],
                [InlineKeyboardButton(text="Generate Comment Ideas", callback_data=callback_for(f"social_score:{score.id}:strategies"))],
                [InlineKeyboardButton(text="Assign Chatter", callback_data=callback_for(f"social_score:{score.id}:assign"))],
                [
                    InlineKeyboardButton(text="Mark Skipped", callback_data=callback_for(f"social_score:{score.id}:skipped")),
                    InlineKeyboardButton(text="Record Result", callback_data=callback_for(f"social_score:{score.id}:record_result")),
                ],
            ]
        )
    rows.extend(page_controls(back_to="opportunities"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_social_opportunity_intelligence_page(session: Session) -> Screen:
    scores = best_social_opportunities(session, limit=5)
    best = scores[0] if scores else None
    framework = social_notification_framework_status(session)
    adapter = official_api_adapter_status()
    lines = [
        "Social Opportunity Intelligence",
        "",
        f"Fortuna found {len(scores)} possible engagement opportunit{'y' if len(scores) == 1 else 'ies'}.",
        "",
    ]
    if best is None:
        lines.extend(
            [
                "Best Opportunity",
                "Nothing scored yet.",
                "",
                "Next Best Move",
                "Add a manual public URL/reference or import an approved export later.",
                "",
                "Compliance",
                "Manual entry, official APIs, and approved exports only. No scraping or auto-posting.",
            ]
        )
    else:
        post = best.post
        source = post.source
        creator = f"@{source.creator_username}" if source else "Manual source"
        lines.extend(
            [
                "Best Opportunity",
                post.content_summary or post.post_reference,
                "",
                "Why it matters",
                f"{creator} matched {post.niche or 'the selected niche'} with a score of {best.score}/100.",
                "",
                "Suggested angle",
                best.suggested_engagement_angle or "curiosity",
                "",
                "Confidence",
                best.confidence_summary or f"{best.confidence_score}/100",
                "",
                "Next Best Move",
                "Assign for human review. Fortuna will not post.",
            ]
        )
        if best.compliance_warning:
            lines.extend(["", "Compliance warning", best.compliance_warning])
    lines.extend(
        [
            "",
            "Future data inputs",
            f"- X official/API adapter: {adapter['x_official_api'].replace('_', ' ')}",
            f"- Instagram official/API adapter: {adapter['instagram_official_api'].replace('_', ' ')}",
            "- CSV/import: planned",
            "- Approved manual capture: planned",
            "",
            "Notifications",
            f"Social alert status: {framework['last_social_alert_status']}",
        ]
    )
    return Screen("\n".join(lines), _social_score_buttons(best))


def render_social_score_strategies_page(session: Session, score_id: int) -> Screen:
    score = session.get(SocialOpportunityScore, score_id)
    if score is None:
        return Screen("Social opportunity not found.", page_menu(back_to="opportunities:score"))
    strategies = engagement_strategies_for_score(score)
    lines = [
        "Comment Ideas",
        "",
        "Human review only. Fortuna will never post these automatically.",
        "",
    ]
    for strategy in strategies:
        lines.append(strategy.angle.title())
        lines.append(strategy.sample)
        lines.append(f"Why: {strategy.why}")
        lines.append(f"Risk: {strategy.risk}")
        lines.append("")
    return Screen("\n".join(lines).strip(), page_menu(back_to="opportunities:score"))


def render_social_score_action_page(session: Session, score_id: int, action: str, user: User | None = None) -> Screen:
    score = session.get(SocialOpportunityScore, score_id)
    if score is None:
        return Screen("Social opportunity not found.", page_menu(back_to="opportunities:score"))
    if action == "create_opportunity":
        opportunity = create_opportunity_from_social_score(session, score, actor=user)
        return render_opportunity_detail_page(session, opportunity.id)
    if action == "strategies":
        return render_social_score_strategies_page(session, score_id)
    if action == "assign":
        if score.opportunity_id is None:
            return Screen(
                "Create the opportunity first, then assign it to a chatter for human review.",
                page_menu(back_to="opportunities:score"),
            )
        return render_opportunity_assignment_page(session, score.opportunity_id)
    if action == "skipped":
        record_social_outcome(session, score, actor=user, outcome="skipped", notes="Skipped from Telegram dashboard.")
        return Screen(
            "Skipped\n\nFortuna recorded this outcome and will learn from it.",
            page_menu(back_to="opportunities:score"),
        )
    if action == "record_result":
        if score.opportunity_id is None:
            return Screen(
                "Create the opportunity first, then record the result after human review.",
                page_menu(back_to="opportunities:score"),
            )
        return render_opportunity_result_status_page(session, score.opportunity_id)
    return render_social_opportunity_intelligence_page(session)

def render_creator_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:creators:add":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:opportunities:creators:add:platform:{platform}") for platform in CREATOR_WATCH_PLATFORMS]
        return Screen(
            text="Add Creator\n\nStep 1 of 9\nChoose platform.",
            reply_markup=choice_menu(choices, back_to="opportunities:creators"),
        )
    if len(parts) >= 5 and parts[3] == "platform":
        return Screen(
            text="Add Creator\n\nStep 2 of 9\nSend the creator username in chat. Do not include passwords or private data.",
            reply_markup=page_menu(back_to="opportunities:creators:add"),
        )
    if len(parts) >= 5 and parts[3] == "priority":
        models = list_models_for_opportunity_assignment(session)
        choices = [("Skip Model", "nav:opportunities:creators:add:model:skip")]
        choices.extend((model.display_name[:40], f"nav:opportunities:creators:add:model:{model.id}") for model in models)
        return Screen("Add Creator\n\nStep 6 of 9\nAssign a model/brand or skip.", choice_menu(choices, back_to="opportunities:creators:add"))
    if len(parts) >= 5 and parts[3] == "model":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:creators:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:creators:add:chatter:{user.id}") for user in users)
        return Screen("Add Creator\n\nStep 7 of 9\nAssign a chatter/team member or skip.", choice_menu(choices, back_to="opportunities:creators:add"))
    if len(parts) >= 5 and parts[3] == "chatter":
        return Screen(
            text="Add Creator\n\nStep 8 of 9\nSend optional notes, or type skip to create the creator watch item.",
            reply_markup=page_menu(back_to="opportunities:creators:add"),
        )
    return Screen("Add Creator\n\nContinue the guided creator intake.", page_menu(back_to="opportunities:creators"))

def render_opportunity_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:add":
        choices = [
            ("Creator Watch", "nav:opportunities:add:source:creator_watch"),
            ("Own Post", "nav:opportunities:add:source:own_post"),
            ("Manual", "nav:opportunities:add:source:manual"),
        ]
        return Screen("Add Opportunity\n\nStep 1 of 10\nChoose the source.", choice_menu(choices, back_to="opportunities:command"))
    if page == "opportunities:add:source:creator_watch":
        creators = list_creator_watches(session, active_only=True, limit=20)
        choices = [(f"{creator.creator_name[:32]}", f"nav:opportunities:add:source:creator_watch:{creator.id}") for creator in creators]
        if not choices:
            choices = [("No creators yet", "nav:opportunities:creators")]
        return Screen("Add Opportunity\n\nChoose the creator source.", choice_menu(choices, back_to="opportunities:add"))
    if page == "opportunities:add:source:own_post":
        posts = list_post_watches(session, limit=20)
        choices = [(f"{post.post_reference[:32]}", f"nav:opportunities:add:source:own_post:{post.id}") for post in posts]
        if not choices:
            choices = [("No watched posts yet", "nav:opportunities:posts")]
        return Screen("Add Opportunity\n\nChoose the own post source.", choice_menu(choices, back_to="opportunities:add"))
    if "platform" in parts:
        return Screen(
            text="Add Opportunity\n\nStep 3 of 10\nSend the title or short description in chat.",
            reply_markup=page_menu(back_to="opportunities:add"),
        )
    if len(parts) >= 4 and parts[2] == "source":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:{page}:platform:{platform}") for platform in OPPORTUNITY_PLATFORMS if platform != "reddit"]
        return Screen("Add Opportunity\n\nStep 2 of 10\nChoose platform.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "priority":
        models = list_models_for_opportunity_assignment(session)
        choices = [("Skip Model", "nav:opportunities:add:model:skip")]
        choices.extend((model.display_name[:40], f"nav:opportunities:add:model:{model.id}") for model in models)
        return Screen("Add Opportunity\n\nStep 6 of 10\nAssign a model/brand or skip.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "model":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:add:chatter:{user.id}") for user in users)
        return Screen("Add Opportunity\n\nStep 8 of 10\nAssign a chatter or skip.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "chatter":
        return Screen(
            text="Add Opportunity\n\nStep 9 of 10\nSend optional notes, or type skip to confirm and create.",
            reply_markup=page_menu(back_to="opportunities:add"),
        )
    return Screen("Add Opportunity\n\nContinue the guided intake.", page_menu(back_to="opportunities"))

def render_post_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:posts:add":
        models = list_models_for_opportunity_assignment(session)
        choices = [(model.display_name[:40], f"nav:opportunities:posts:add:model:{model.id}") for model in models]
        if not choices:
            choices = [("Create a Model First", "nav:models:create")]
        return Screen("Add Own Post\n\nStep 1 of 8\nChoose model/brand.", choice_menu(choices, back_to="opportunities:posts"))
    if "platform" in parts:
        return Screen(
            text="Add Own Post\n\nStep 4 of 8\nSend the post reference or URL in chat.",
            reply_markup=page_menu(back_to="opportunities:posts:add"),
        )
    if len(parts) >= 5 and parts[3] == "model":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:{page}:platform:{platform}") for platform in POST_WATCH_PLATFORMS]
        return Screen("Add Own Post\n\nStep 2 of 8\nChoose platform.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "type":
        choices = [(level.title(), f"nav:opportunities:posts:add:attention:{level}") for level in POST_WATCH_ATTENTION_LEVELS]
        return Screen("Add Own Post\n\nStep 6 of 8\nChoose attention level.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "attention":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:posts:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:posts:add:chatter:{user.id}") for user in users)
        return Screen("Add Own Post\n\nStep 7 of 8\nAssign chatter/team member or skip.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "chatter":
        return Screen(
            text="Add Own Post\n\nStep 8 of 8\nSend optional notes, or type skip to confirm and create.",
            reply_markup=page_menu(back_to="opportunities:posts:add"),
        )
    return Screen("Add Own Post\n\nContinue the guided post intake.", page_menu(back_to="opportunities:posts"))

def render_opportunity_command_center_page(session: Session, user: User | None = None) -> Screen:
    summary = opportunity_queue_summary(session, user=user)
    counts = summary["counts"]
    lines = [
        "Opportunity Command Center",
        "",
        f"New: {counts['discovered']}",
        f"Reviewing: {counts['reviewing']}",
        f"Assigned: {counts['assigned']}",
        f"Completed: {counts['completed']}",
        f"Rejected: {counts['rejected']}",
        f"Archived: {counts['archived']}",
        "",
        "Top Opportunities:",
    ]
    buttons: list[tuple[str, str]] = []
    if not summary["top"]:
        lines.append("- None yet")
    for opportunity in summary["top"][:5]:
        lines.append(f"- {opportunity.title} | {opportunity.score}/100 | {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:32]}", f"nav:opportunity:{opportunity.id}"))
    lines.append("")
    lines.append("High Priority:")
    if not summary["high_priority"]:
        lines.append("- None")
    for opportunity in summary["high_priority"][:5]:
        lines.append(f"- {_status_marker('warning')} {opportunity.title} | {opportunity.score}/100")
    lines.append("")
    lines.append("Recent Results:")
    if not summary["recent_results"]:
        lines.append("- No results recorded yet")
    for result in summary["recent_results"][:5]:
        opportunity = session.get(Opportunity, result.opportunity_id)
        lines.append(f"- {opportunity.title if opportunity else 'Opportunity'}: {result.status}")
    return Screen(text="\n".join(lines), reply_markup=opportunity_command_menu())

def render_creator_watchlist_page(session: Session) -> Screen:
    creators = list_creator_watches(session, active_only=True, limit=20)
    lines = ["Creator Watchlist", "", "Creators worth watching. Human review only.", ""]
    buttons: list[tuple[str, str]] = []
    if not creators:
        lines.append("No creators watched yet.")
    for creator in creators:
        chatter = creator.assigned_chatter
        model = creator.assigned_model
        lines.append(f"{creator.id}. {creator.creator_name} (@{creator.creator_username})")
        lines.append(f"   Platform: {creator.platform} | Priority: {creator.priority} | Niche: {creator.niche or 'not set'}")
        lines.append(f"   Model: {model.display_name if model else 'Unassigned'} | Chatter: {_identity(chatter)}")
        buttons.append((f"{creator.id}. {creator.creator_name[:34]}", f"nav:creator:{creator.id}"))
    return Screen(text="\n".join(lines), reply_markup=creator_watch_menu(buttons))

def render_creator_watch_detail_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen(text="Creator watch item not found.", reply_markup=page_menu(back_to="opportunities:creators"))
    lines = [
        "Creator Watch",
        "",
        f"Name: {creator.creator_name}",
        f"Display Name: {creator.display_name or creator.creator_name}",
        f"Username: @{creator.creator_username}",
        f"Platform: {creator.platform}",
        f"Priority: {creator.priority}",
        f"Alerts: {'On' if creator.alert_enabled else 'Off'}",
        f"Alert Route: {_notification_purpose_label(creator.assigned_group)}",
        f"Niche: {creator.niche or 'Not set'}",
        f"Profile: {creator.profile_url or 'Not set'}",
        f"Assigned Model: {creator.assigned_model.display_name if creator.assigned_model else 'Unassigned'}",
        f"Assigned Chatter: {_identity(creator.assigned_chatter)}",
        f"Team ID: {creator.assigned_team_id or 'Unassigned'}",
        f"Why Watch: {creator.watch_reason or 'Not set'}",
        f"Historical Score: {creator.historical_score}/100",
        f"Last Useful Post: {format_user_datetime(None, creator.last_useful_post_at) if creator.last_useful_post_at else 'Not yet'}",
        f"Status: {creator.status}",
        f"Active: {creator.is_active}",
        f"Created: {format_user_datetime(None, creator.created_at) if creator.created_at else 'Not set'}",
        f"Updated: {format_user_datetime(None, creator.updated_at) if creator.updated_at else 'Not set'}",
        f"Notes: {creator.notes or 'None'}",
        "",
        "Use this to focus human attention. No platform actions are automated.",
    ]
    return Screen(text="\n".join(lines), reply_markup=creator_watch_detail_menu(creator.id))

def render_creator_post_alert_prompt_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen(text="Creator watch item not found.", reply_markup=page_menu(back_to="opportunities:creators"))
    return Screen(
        text="\n".join(
            [
                "New Creator Post Alert",
                "",
                f"Creator: @{creator.creator_username}",
                f"Route: {_notification_purpose_label(creator.assigned_group)}",
                "",
                "Send the post URL or reference in chat.",
                "Optional: add notes after a pipe.",
                "",
                "Example:",
                "https://x.com/name/status/123 | fast timing window",
                "",
                "Fortuna will create an opportunity, generate comment strategies, and route the alert for human review only.",
            ]
        ),
        reply_markup=page_menu(back_to=f"creator:{creator.id}"),
    )

def render_creator_post_alert_detail_page(session: Session, alert_id: int) -> Screen:
    alert = session.get(CreatorPostAlert, alert_id)
    if alert is None:
        return Screen(text="Creator alert not found.", reply_markup=page_menu(back_to="opportunities:creators"))
    creator = alert.creator_watch
    opportunity = alert.opportunity
    lines = [
        "Creator Alert",
        "",
        f"Creator: @{creator.creator_username if creator else 'unknown'}",
        f"Platform: {alert.platform.upper() if alert.platform == 'x' else alert.platform.title()}",
        f"Priority: {alert.priority.title()}",
        f"Route: {_notification_purpose_label(alert.assigned_group)}",
        f"Status: {alert.status.title()}",
        f"Reference: {alert.post_reference}",
        f"Assigned Chatter: {_identity(alert.assigned_chatter)}",
        f"Opportunity: {opportunity.title if opportunity else 'Not created'}",
        "",
        "Why it matters:",
        "High-value comment opportunity.",
        "",
        "Suggested angle:",
        alert.suggested_angle or "Curiosity / relatable reply",
        "",
        "Next move:",
        "Review the opportunity and post manually if it makes sense. Fortuna will not post for you.",
    ]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            *(
                [[InlineKeyboardButton(text="Open Opportunity", callback_data=f"nav:opportunity:{opportunity.id}")]]
                if opportunity
                else []
            ),
            [InlineKeyboardButton(text="Generate Comments", callback_data=f"nav:opportunity:{opportunity.id}:strategies" if opportunity else "nav:opportunities")],
            [InlineKeyboardButton(text="Mark Reviewed", callback_data=f"nav:creator_alert:{alert.id}:reviewed")],
            *page_controls(back_to=f"creator:{alert.creator_watch_id}"),
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=markup)

def render_post_watch_page(session: Session, *, status: str | None = None) -> Screen:
    posts = list_post_watches(session, status=status, limit=20)
    title = "Own Post Watch" if status is None else "Own Post Watch - Attention Needed"
    lines = [title, "", "Track important posts that may need human attention.", ""]
    buttons: list[tuple[str, str]] = []
    if not posts:
        lines.append("No watched posts yet.")
    for post in posts:
        model = post.model_brand
        lines.append(f"{post.id}. {post.post_reference}")
        lines.append(f"   Platform: {post.platform} | Type: {post.post_type} | Status: {post.status}")
        lines.append(f"   Model: {model.display_name if model else 'Unknown'} | Notes: {post.notes or 'None'}")
        buttons.append((f"{post.id}. {post.post_reference[:34]}", f"nav:post:{post.id}"))
    return Screen(text="\n".join(lines), reply_markup=post_watch_menu(buttons))

def render_post_watch_detail_page(session: Session, post_id: int) -> Screen:
    post = get_post_watch(session, post_id)
    if post is None:
        return Screen(text="Post watch item not found.", reply_markup=page_menu(back_to="opportunities:posts"))
    lines = [
        "Own Post Watch",
        "",
        f"Post: {post.post_reference}",
        f"Platform: {post.platform}",
        f"Type: {post.post_type}",
        f"Status: {post.status}",
        f"Attention: {post.attention_level}",
        f"Priority: {post.priority.title()}",
        f"Alerts: {'On' if post.alert_enabled else 'Off'}",
        f"Alert Route: {_notification_purpose_label(post.assigned_group)}",
        f"Model/Brand: {post.model_brand.display_name if post.model_brand else 'Unknown'}",
        f"Account ID: {post.account_id or 'None'}",
        f"Assigned Chatter: {_identity(post.assigned_chatter)}",
        f"Team ID: {post.assigned_team_id or 'Unassigned'}",
        f"Notes: {post.notes or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=post_watch_detail_menu(post.id))

def render_own_post_alert_prompt_page(session: Session, post_id: int) -> Screen:
    post = get_post_watch(session, post_id)
    if post is None:
        return Screen(text="Post watch item not found.", reply_markup=page_menu(back_to="opportunities:posts"))
    return Screen(
        text="\n".join(
            [
                "New Own Post Alert",
                "",
                f"Post: {post.post_reference}",
                f"Route: {_notification_purpose_label(post.assigned_group)}",
                "",
                "Send a post URL/reference, or type same to use the saved reference.",
                "Optional: add notes after a pipe.",
                "",
                "Example:",
                "same | needs quick team review",
                "",
                "Fortuna will route the alert, create a follow-up task, and keep all platform action manual.",
            ]
        ),
        reply_markup=page_menu(back_to=f"post:{post.id}"),
    )

def render_own_post_alert_detail_page(session: Session, alert_id: int) -> Screen:
    alert = session.get(OwnPostAlert, alert_id)
    if alert is None:
        return Screen(text="Own post alert not found.", reply_markup=page_menu(back_to="opportunities:posts"))
    opportunity = alert.opportunity
    lines = [
        "Own Post Alert",
        "",
        f"Post: {alert.post_reference}",
        f"Platform: {alert.platform.upper() if alert.platform == 'x' else alert.platform.title()}",
        f"Priority: {alert.priority.title()}",
        f"Route: {_notification_purpose_label(alert.assigned_group)}",
        f"Status: {alert.status.title()}",
        f"Assigned Chatter: {_identity(alert.assigned_chatter)}",
        f"Opportunity: {opportunity.title if opportunity else 'Not created'}",
        f"Follow-up Task: {alert.follow_up_task_id or 'Not created'}",
        "",
        "Safety:",
        "All platform action manual. Fortuna does not post for you.",
        "",
        "Next move:",
        "Team should review timing and act manually if useful.",
    ]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            *(
                [[InlineKeyboardButton(text="Open Opportunity", callback_data=f"nav:opportunity:{opportunity.id}")]]
                if opportunity
                else []
            ),
            [InlineKeyboardButton(text="Mark Reviewed", callback_data=f"nav:own_post_alert:{alert.id}:reviewed")],
            *page_controls(back_to=f"post:{alert.post_watch_id}"),
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=markup)

def render_opportunity_list_page(session: Session) -> Screen:
    opportunities = list_opportunities(session, limit=20)
    lines = ["Opportunities", ""]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Platform: {opportunity.platform} | Score: {opportunity.score} | Status: {opportunity.status}")
        lines.append(f"   Niche: {opportunity.niche or 'not set'}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))

def render_opportunity_detail_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen(text="Opportunity not found.", reply_markup=page_menu(back_to="opportunities:list"))
    assignee = session.get(User, opportunity.assigned_to_user_id) if opportunity.assigned_to_user_id else None
    model = session.get(ModelBrand, opportunity.model_brand_id) if opportunity.model_brand_id else None
    strategies = comment_strategies_for_opportunity(session, opportunity)[:2]
    latest_result = opportunity_results(session, opportunity, limit=1)
    lines = [
        "Opportunity",
        "",
        f"Title: {opportunity.title}",
        f"Platform: {opportunity.platform}",
        f"Source: {opportunity.source_type or 'manual'}",
        f"Status: {opportunity.status}",
        f"Score: {opportunity.score}/100",
        f"Priority: {opportunity.priority}",
        f"Niche: {opportunity.niche or 'Not set'}",
        f"Model/Brand: {model.display_name if model else 'Unassigned'}",
        f"Assigned To: {_identity(assignee)}",
        f"Assigned At: {format_user_datetime(None, opportunity.assigned_at) if opportunity.assigned_at else 'Not set'}",
        f"Due: {format_user_datetime(None, opportunity.due_at) if opportunity.due_at else 'Not set'}",
        f"Completed: {format_user_datetime(None, opportunity.completed_at) if opportunity.completed_at else 'Not set'}",
        f"URL: {opportunity.url or 'Not set'}",
        f"Reason: {opportunity.reason or 'None'}",
        f"Suggested Angle: {opportunity.suggested_angle or 'None'}",
        f"Latest Result: {latest_result[0].status if latest_result else 'None'}",
        "",
        "Suggested Strategies:",
    ]
    if not strategies:
        lines.append("- No strategy suggestions yet.")
    for strategy in strategies:
        lines.append(f"- {strategy.angle.replace('_', ' ').title()} | Risk: {strategy.risk_score}/100 | Engagement: {strategy.engagement_score}/100")
        if strategy.sample_comment:
            lines.append(f"  Draft: {strategy.sample_comment}")
    lines.extend(
        [
            "",
            "Safety: posting remains manual and human-approved.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=opportunity_detail_menu(opportunity.id))

def render_opportunity_strategies_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen(text="Opportunity not found.", reply_markup=page_menu(back_to="opportunities:list"))
    strategies = comment_strategies_for_opportunity(session, opportunity)
    lines = [
        "Suggested Strategies",
        "",
        f"Opportunity: {opportunity.title}",
        "These are human review prompts, not automated comments.",
        "",
    ]
    if not strategies:
        lines.append("No strategies generated yet.")
    for strategy in strategies:
        lines.append(f"{strategy.angle.replace('_', ' ').title()} ({strategy.tone})")
        lines.append(
            f"   Curiosity: {strategy.curiosity_score}/100 | Engagement: {strategy.engagement_score}/100 | Risk: {strategy.risk_score}/100"
        )
        lines.append(f"   Draft: {strategy.sample_comment or 'Write a short human-approved comment.'}")
        lines.append(f"   Why: {strategy.reasoning or 'Suggested for human review.'}")
        lines.append(f"   Might Work Because: {strategy.why_it_might_work or 'It gives the chatter a safe angle.'}")
        lines.append(f"   Use Case: {strategy.suggested_use_case or 'Use only when context fits.'}")
    return Screen(
        text="\n".join(lines),
        reply_markup=choice_menu(
            [("Regenerate Strategies", f"nav:opportunity:{opportunity.id}:strategies:regenerate")],
            back_to=f"opportunity:{opportunity.id}",
        ),
    )

def render_opportunity_assignment_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:opportunity:{opportunity.id}:assign:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:opportunity:{opportunity.id}")]
    return Screen(
        text=f"Assign Chatter\n\nOpportunity: {opportunity.title}\nChoose who should own this.",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )

def render_opportunity_status_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    statuses = [status for status in OPPORTUNITY_STATUSES if status != "archived"]
    choices = [(status.replace("_", " ").title(), f"nav:opportunity:{opportunity.id}:status:{status}") for status in statuses]
    return Screen(
        text=f"Change Opportunity Status\n\nCurrent: {opportunity.status}",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )

def render_opportunity_result_status_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    choices = [
        ("Posted", f"nav:opportunity:{opportunity.id}:result:posted"),
        ("Skipped", f"nav:opportunity:{opportunity.id}:result:skipped"),
        ("Rejected", f"nav:opportunity:{opportunity.id}:result:rejected"),
        ("Failed", f"nav:opportunity:{opportunity.id}:result:failed"),
    ]
    return Screen(
        text="Record Result\n\nChoose the human-recorded result. Fortuna OS will ask for notes next.",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )

def render_creator_model_assignment_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    models = list_models_for_opportunity_assignment(session)
    choices = [(model.display_name[:40], f"nav:creator:{creator.id}:assign_model:{model.id}") for model in models]
    if not choices:
        choices = [("No models yet", "nav:models:create")]
    return Screen(
        text=f"Assign Model\n\nCreator: {creator.creator_name}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )

def render_creator_chatter_assignment_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:creator:{creator.id}:assign_chatter:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:creator:{creator.id}")]
    return Screen(
        text=f"Assign Chatter\n\nCreator: {creator.creator_name}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )

def render_creator_priority_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    choices = [(priority.title(), f"nav:creator:{creator.id}:priority:{priority}") for priority in CREATOR_WATCH_PRIORITIES]
    return Screen(
        text=f"Edit Priority\n\nCreator: {creator.creator_name}\nCurrent: {creator.priority}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )

def render_post_chatter_assignment_page(session: Session, post_id: int) -> Screen:
    post = get_post_watch(session, post_id)
    if post is None:
        return Screen("Post watch item not found.", page_menu(back_to="opportunities:posts"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:post:{post.id}:assign_chatter:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:post:{post.id}")]
    return Screen(
        text=f"Assign Chatter\n\nPost: {post.post_reference}",
        reply_markup=choice_menu(choices, back_to=f"post:{post.id}"),
    )

def render_manager_opportunity_page(session: Session) -> Screen:
    view = manager_opportunity_view(session)
    counts = view["counts"]
    lines = [
        "Manager Opportunity View",
        "",
        f"Team Opportunities: {counts['assigned']}",
        f"Unassigned Opportunities: {len(view['unassigned'])}",
        f"Overdue: {len(view['overdue'])}",
        f"Completed Today: {len(view['completed_today'])}",
        f"High Priority: {len(view['high_priority'])}",
        "",
        "Top Performing Angles:",
    ]
    if not view["top_angles"]:
        lines.append("- Not enough results yet")
    for angle, count in view["top_angles"]:
        lines.append(f"- {angle}: {count} win(s)")
    lines.append("")
    lines.append("By Chatter:")
    if not view["most_active_chatters"]:
        lines.append("- Not enough chatter activity yet")
    for chatter, count in view["most_active_chatters"]:
        lines.append(f"- {chatter}: {count} result(s)")
    lines.append("")
    lines.append("By Model:")
    if not view["by_model"]:
        lines.append("- No model distribution yet")
    for model, count in view["by_model"]:
        lines.append(f"- {model}: {count}")
    lines.append("")
    lines.append("By Niche:")
    if not view["by_niche"]:
        lines.append("- No niche distribution yet")
    for niche, count in view["by_niche"]:
        lines.append(f"- {niche}: {count}")
    lines.append("")
    lines.append("Unassigned Opportunities:")
    if not view["unassigned"]:
        lines.append("- None")
    for opportunity in view["unassigned"][:5]:
        lines.append(f"- {opportunity.title} | {opportunity.score}/100")
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu())

def render_opportunity_learning_v2_page(session: Session) -> Screen:
    summary = opportunity_learning_overview(session)
    lines = ["Opportunity Learning", "", "What Fortuna OS is learning from human-recorded outcomes.", ""]
    lines.append("Best Niches:")
    if not summary["best_niches"]:
        lines.append("- No opportunity outcomes yet.")
    for niche, stats in summary["best_niches"][:5]:
        lines.append(f"- {niche}: {stats['success']}/{stats['total']} positive")
    lines.append("")
    lines.append("Best Angles:")
    if not summary["best_angles"]:
        lines.append("- No angles recorded yet.")
    for angle, stats in summary["best_angles"][:5]:
        lines.append(f"- {angle}: {stats['success']}/{stats['total']} positive")
    lines.append("")
    lines.append("Most Successful Teams:")
    if not summary["most_successful_teams"]:
        lines.append("- Not enough team results yet.")
    for team, count in summary["most_successful_teams"][:5]:
        lines.append(f"- {team}: {count} win(s)")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="opportunities"))

def render_chatter_workspace_page(session: Session, user: User) -> Screen:
    workspace = chatter_workspace(session, user)
    lines = [
        "Chatter Workspace",
        "",
        f"New: {len(workspace['opportunity_tabs']['new'])}",
        f"In Progress: {len(workspace['opportunity_tabs']['in_progress'])}",
        f"Needs Result: {len(workspace['opportunity_tabs']['needs_result'])}",
        f"Completed: {len(workspace['opportunity_tabs']['completed'])}",
        "",
        "Today's Opportunities:",
    ]
    if not workspace["today_opportunities"]:
        lines.append("- No opportunities assigned today.")
    for opportunity in workspace["today_opportunities"]:
        lines.append(f"- {opportunity.title} | {opportunity.priority} | {opportunity.status}")
    lines.append("")
    lines.append("Assigned Models:")
    if not workspace["assigned_models"]:
        lines.append("- No models assigned yet.")
    for model in workspace["assigned_models"]:
        lines.append(f"- {_model_identity(model)}")
    lines.append("")
    lines.append("Assigned Tasks:")
    if not workspace["assigned_tasks"]:
        lines.append("- No open tasks assigned.")
    for task in workspace["assigned_tasks"]:
        lines.append(f"- {task.title} | {task.status} | {task.priority}")
    lines.append("")
    lines.append("Recent Results:")
    if not workspace["recent_results"]:
        lines.append("- No results recorded yet.")
    for result in workspace["recent_results"]:
        lines.append(f"- Opportunity {result.opportunity_id}: {result.status}")
    lines.extend(["", "Recommended Next Action:", workspace["recommended_next_action"]])
    return Screen(text="\n".join(lines), reply_markup=chatter_workspace_menu())

def render_team_activation_page(session: Session) -> Screen:
    summaries = team_activation_qa(session)
    lines = ["Team Activation QA", "", "Friendly rollout readiness. Not punitive.", ""]
    buttons: list[tuple[str, str]] = []
    if not summaries:
        lines.append("No active users yet.")
    for item in summaries[:20]:
        user = item["user"]
        lines.append(f"{user.id}. {_identity(user)}")
        lines.append(f"   Status: {user.status}")
        lines.append(f"   Activation Score: {item['score']}%")
        lines.append(f"   Needs: {', '.join(item['flags'][:4]) if item['flags'] else 'ready'}")
        lines.append(
            f"   Work: {item['assigned_tasks']} task(s), {item['assigned_opportunities']} opportunit(y/ies), {item['assigned_models']} model(s)"
        )
        buttons.append((f"{user.id}. {_identity(user)[:32]}", f"nav:user:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=team_activation_menu(buttons))

def render_opportunity_results_page(session: Session) -> Screen:
    results = opportunity_results(session, limit=20)
    lines = ["Opportunity Results", ""]
    if not results:
        lines.append("No opportunity results yet.")
    for result in results:
        opportunity = session.get(Opportunity, result.opportunity_id)
        posted_by = session.get(User, result.posted_by_user_id) if result.posted_by_user_id else None
        lines.append(f"{result.id}. {opportunity.title if opportunity else 'Opportunity'}")
        lines.append(f"   Status: {result.status} | Posted By: {_identity(posted_by)}")
        lines.append(f"   Clicks: {result.clicks or 0} | Conversions: {result.conversions or 0}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="opportunities"))

