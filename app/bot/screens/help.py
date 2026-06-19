from .formatting import *
from app.services.help_brain import help_brain_answer, seed_help_knowledge_base

def render_help_center_page(user: User | None = None) -> Screen:
    buttons = [(label, f"nav:help:{topic}") for topic, label in help_topics_for_role(user)]
    lines = [
        "\u2753 Ask Fortuna",
        "",
        "What do you need?",
        "",
        "- What should I do next?",
        "- Help me finish setup",
        "- Help me add a proxy",
        "- Explain this screen",
        "- I\u2019m stuck",
        "",
        "Fortuna will keep it short and point you to the next button.",
    ]
    return Screen(text="\n".join(lines), reply_markup=help_center_menu(buttons))

def render_help_topic_page(topic: str, user: User | None = None) -> Screen:
    title = dict(help_topics_for_role(user)).get(topic, topic.replace("_", " ").title())
    return Screen(
        text=f"{title}\n\n{help_text(topic, user)}",
        reply_markup=page_menu(back_to="help"),
    )

def render_help_copilot_page(session: Session, user: User | None = None, *, question: str | None = None) -> Screen:
    seed_help_knowledge_base(session)
    prompts = {
        "where_start": "Where do I start?",
        "create_first_model": "How do I create the first model?",
        "edit_model": "How do I edit a model?",
        "add_accounts": "How do I add accounts?",
        "assign_chatter": "How do I assign a chatter?",
        "create_opportunity": "How do I create an opportunity?",
        "add_creator": "How do I add a creator?",
        "assign_opportunity": "How do I assign an opportunity?",
        "my_opportunities": "Where do I see my opportunities?",
        "access": "Why can't I access this?",
        "next": "What should I do next?",
        "add_proxy": "How do I add my proxy?",
        "where_proxy": "Where is Proxy Vault?",
        "why_broken": "Why is this broken?",
        "postgres": "Why do I need Postgres?",
        "safe_next": "What is safe to do next?",
        "activation": "What's stopping my agency from being ready?",
        "readiness_low": "Why is readiness low?",
        "finish_setup": "How do I finish setup?",
        "model_unhealthy": "Why is this model unhealthy?",
        "record_results": "How do I record results?",
        "opportunity": "How do I complete an opportunity?",
        "where": "Explain this screen.",
        "availability": "How does Availability work?",
        "screen:creator_detail": "Explain this Creator Detail screen.",
        "screen:opportunity_detail": "Explain this Opportunity Detail screen.",
        "screen:chatter_workspace": "Explain this Chatter Workspace screen.",
        "screen:manager_opportunity": "Explain this Manager Opportunity View screen.",
        "screen:post_watch": "Explain this Own Post Watch screen.",
        "notification_groups": "How do I register notification groups?",
        "proxy_setup": "How do I assign a proxy?",
        "what_fortuna_did": "What did Fortuna do today?",
        "warning": "What does this warning mean?",
        "help_person": "Who should I ask for help?",
        "comment_profile_leads": "What are comment profile leads?",
        "comment_section_review": "How do I use Comment Section Review?",
        "safe_social_data": "What data is safe to enter?",
        "no_auto_posting": "Does Fortuna comment or follow automatically?",
    }
    if question:
        result = help_brain_answer(session, user, question=prompts.get(question, question), current_page="help")
        lines = [
            "\u2753 Ask Fortuna",
            "",
            result.answer,
            "",
            "Next Button",
            "Open Next Step",
        ]
        return Screen(text="\n".join(lines), reply_markup=help_feedback_menu(result.log_id, next_action=result.next_action))
    else:
        lines = [
            "\u2753 Ask Fortuna",
            "",
            "Choose one:",
            "- Where do I start?",
            "- What should I do next?",
            "- Help me add a proxy",
            "- Why is readiness low?",
            "",
            "Ready when you are.",
        ]
    return Screen(text="\n".join(lines), reply_markup=help_copilot_menu())

