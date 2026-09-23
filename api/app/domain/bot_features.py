import math
import re
from collections import Counter
from datetime import UTC, datetime

from app.domain.entities import Account, Post


def compute_demographic_features(account: Account) -> dict[str, float]:
    now = datetime.now(UTC)

    # 1. Young account (age in days) -> feature is 1.0 if < 7 days, fading to 0
    age_days = (now - account.created_at).total_seconds() / 86400 if account.created_at else 0
    young_account = max(0.0, 1.0 - (age_days / 30.0)) if age_days < 30 else 0.0

    # 2. Handle with many digits
    digits_count = sum(1 for c in account.handle if c.isdigit())
    handle_len = len(account.handle) if account.handle else 1
    digits_handle = digits_count / handle_len

    # 3. No avatar / no description
    no_avatar = 1.0 if not account.avatar_url else 0.0
    no_desc = 1.0 if not account.description else 0.0

    # 4. Self label 'bot'
    # we assume labels or self_labels contains 'bot'
    is_bot_labeled = 1.0 if "bot" in (account.self_labels + account.labels) else 0.0

    # Fallback to checking description
    if not is_bot_labeled and account.description and "bot" in account.description.lower():
        is_bot_labeled = 1.0

    return {
        "demographic_young_account": young_account,
        "demographic_digits_handle": digits_handle,
        "demographic_no_avatar": no_avatar,
        "demographic_no_description": no_desc,
        "demographic_self_label_bot": is_bot_labeled,
    }


def compute_network_features(account: Account) -> dict[str, float]:
    follows = max(1, account.follows_count)
    followers = account.followers_count

    # follower/following ratio (inverted: high following, low followers = bad)
    # se segue 1000 e tem 10, ratio = 100
    ratio = follows / max(1, followers)
    # normalize to 0-1 (if ratio > 10, it's 1.0)
    normalized_ratio = min(1.0, ratio / 10.0)

    return {"network_follower_ratio": normalized_ratio}


def compute_temporal_features(account: Account, posts: list[Post]) -> dict[str, float]:
    now = datetime.now(UTC)
    age_days = max(
        1.0, (now - account.created_at).total_seconds() / 86400 if account.created_at else 1.0
    )

    # posts per day
    posts_per_day = account.posts_count / age_days
    # normalize: > 50 posts/day is 1.0
    norm_posts_per_day = min(1.0, posts_per_day / 50.0)

    if len(posts) < 2:
        return {
            "temporal_posts_per_day": norm_posts_per_day,
            "temporal_interval_cv": 0.0,
            "temporal_hour_entropy": 0.0,
        }

    # Intervals CV
    sorted_posts = sorted(posts, key=lambda p: p.created_at)
    intervals = [
        (sorted_posts[i].created_at - sorted_posts[i - 1].created_at).total_seconds()
        for i in range(1, len(sorted_posts))
    ]

    mean_interval = sum(intervals) / len(intervals)
    if mean_interval > 0:
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_interval
    else:
        cv = 0.0
    # Higher CV = more natural. We return CV directly, weight will be negative.
    # Let's cap at 3.0 to prevent massive outliers
    norm_cv = min(3.0, cv)

    # Hour entropy
    hours = [p.created_at.hour for p in posts]
    hour_counts = Counter(hours)
    entropy = 0.0
    total = len(hours)
    for count in hour_counts.values():
        p = count / total
        entropy -= p * math.log2(p)

    # Max entropy for 24 bins is log2(24) ~ 4.58
    norm_entropy = entropy / 4.58

    return {
        "temporal_posts_per_day": norm_posts_per_day,
        "temporal_interval_cv": norm_cv,
        "temporal_hour_entropy": norm_entropy,
    }


def compute_content_features(posts: list[Post]) -> dict[str, float]:
    if not posts:
        return {
            "content_duplicate_ratio": 0.0,
            "content_repost_ratio": 0.0,
            "content_repeated_links": 0.0,
        }

    total = len(posts)

    # Duplicate ratio, incluindo quase-duplicatas via Jaccard de shingles.
    texts = [p.text.strip().lower() for p in posts if p.text]
    fingerprints: list[set[str]] = []
    for text in texts:
        tokens = re.findall(r"\w+", text)
        fingerprints.append(
            {" ".join(tokens[index : index + 3]) for index in range(max(1, len(tokens) - 2))}
        )
    duplicate_count = 0
    for index, fingerprint in enumerate(fingerprints):
        is_duplicate = False
        for previous in fingerprints[:index]:
            union = fingerprint | previous
            similarity = len(fingerprint & previous) / len(union) if union else 1.0
            if similarity >= 0.8:
                is_duplicate = True
                break
        duplicate_count += int(is_duplicate)
    duplicate_ratio = duplicate_count / len(texts) if texts else 0.0

    # Repost ratio
    reposts = sum(1 for p in posts if getattr(p, "is_repost", False))
    repost_ratio = reposts / total

    # Repeated links
    link_pattern = re.compile(r"https?://[^\s]+")
    all_links = []
    for t in texts:
        all_links.extend(link_pattern.findall(t))

    if all_links:
        unique_links = set(all_links)
        repeated_links_ratio = 1.0 - (len(unique_links) / len(all_links))
    else:
        repeated_links_ratio = 0.0

    return {
        "content_duplicate_ratio": duplicate_ratio,
        "content_repost_ratio": repost_ratio,
        "content_repeated_links": repeated_links_ratio,
    }


def compute_all_features(account: Account, posts: list[Post]) -> dict[str, float]:
    feats = {}
    feats.update(compute_demographic_features(account))
    feats.update(compute_network_features(account))
    feats.update(compute_temporal_features(account, posts))
    feats.update(compute_content_features(posts))
    return feats
