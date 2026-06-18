from .formatting import *

def render_help_center_page(user: User | None = None) -> Screen:
    buttons = [(label, f"nav:help:{topic}") for topic, label in help_topics_for_role(user)]
    lines = [
        "Help Center",
        "",
        "Quick answers for day-to-day work.",
        "Pick a topic when you need a reminder or a clean next step.",
    ]
    return Screen(text="\n".join(lines), reply_markup=help_center_menu(buttons))

def render_help_topic_page(topic: str, user: User | None = None) -> Screen:
    title = dict(help_topics_for_role(user)).get(topic, topic.replace("_", " ").title())
    return Screen(
        text=f"{title}\n\n{help_text(topic, user)}",
        reply_markup=page_menu(back_to="help"),
    )

def render_help_copilot_page(session: Session, user: User | None = None, *, question: str | None = None) -> Screen:
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
        "activation": "What's stopping my agency from being ready?",
        "readiness_low": "Why is readiness low?",
        "finish_setup": "How do I finish setup?",
        "model_unhealthy": "Why is this model unhealthy?",
        "record_results": "How do I record results?",
        "opportunity": "How do I complete an opportunity?",
        "where": "Where do I go?",
        "availability": "How does Availability work?",
        "screen:creator_detail": "Explain this Creator Detail screen.",
        "screen:opportunity_detail": "Explain this Opportunity Detail screen.",
        "screen:chatter_workspace": "Explain this Chatter Workspace screen.",
        "screen:manager_opportunity": "Explain this Manager Opportunity View screen.",
        "screen:post_watch": "Explain this Own Post Watch screen.",
    }
    if question:
        result = help_copilot_answer(session, user, question=prompts.get(question, question), current_page="help")
        lines = [
            "Help Copilot",
            "",
            f"Role Context: {result['role']}",
            "",
            result["answer"],
            "",
            f"Next Action: {result['next_action']}",
        ]
    else:
        lines = [
            "Help Copilot",
            "",
            "Ask simple workflow questions like:",
            "- Where do I start?",
            "- How do I create the first model?",
            "- What does this mean?",
            "- How do I complete an opportunity?",
            "- Where do I go?",
            "",
            "Choose a prompt below for a role-aware answer.",
        ]
    return Screen(text="\n".join(lines), reply_markup=help_copilot_menu())

