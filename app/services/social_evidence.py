from __future__ import annotations

from app.models.social import SocialComment, SocialCommentProfile


def comment_evidence(comment: SocialComment) -> dict:
    return {
        "post_reference": comment.post_reference,
        "author": f"@{comment.author_username}",
        "reply_count": comment.reply_count,
        "like_count": comment.like_count,
        "quality_score": comment.quality_score,
        "engagement_score": comment.engagement_score,
        "detected_angle": comment.detected_angle,
        "human_summary": (
            f"@{comment.author_username} received {comment.reply_count} replies and {comment.like_count} likes "
            f"with a {comment.quality_score}/100 quality score."
        ),
    }


def profile_evidence(profile: SocialCommentProfile) -> dict:
    return {
        "username": f"@{profile.username}",
        "observed_comment_count": profile.observed_comment_count,
        "repeated_appearance_count": profile.repeated_appearance_count,
        "avg_comment_quality": profile.avg_comment_quality,
        "avg_engagement": profile.avg_engagement,
        "potential_value_score": profile.potential_value_score,
        "human_summary": profile_evidence_summary(profile),
    }


def profile_evidence_summary(profile: SocialCommentProfile) -> str:
    if profile.observed_comment_count <= 0:
        return f"Fortuna has not seen enough public comment activity from @{profile.username} yet."
    reasons: list[str] = []
    if profile.repeated_appearance_count >= 2:
        reasons.append("appears repeatedly in relevant conversations")
    if profile.avg_engagement >= 60:
        reasons.append("gets replies or likes")
    if profile.avg_comment_quality >= 60:
        reasons.append("writes useful comments")
    if not reasons:
        reasons.append("has early public comment evidence")
    return f"Fortuna noticed @{profile.username} " + ", ".join(reasons) + "."
