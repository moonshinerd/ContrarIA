from datetime import UTC, datetime, timedelta

from app.domain.bot_features import compute_all_features
from app.domain.entities import Account, Post


def test_bot_features_demographic_young():
    # Less than 30 days
    created = datetime.now(UTC) - timedelta(days=5)
    acc = Account(did="did:1", handle="bot123", created_at=created)
    feats = compute_all_features(acc, [])
    assert feats["demographic_young_account"] > 0
    assert feats["demographic_digits_handle"] == 3 / 6  # 0.5
    assert feats["demographic_no_avatar"] == 1.0


def test_bot_features_network():
    acc = Account(did="did:1", handle="user", follows_count=2000, followers_count=100)
    feats = compute_all_features(acc, [])
    # ratio = 2000 / 100 = 20 -> normalized max 1.0
    assert feats["network_follower_ratio"] == 1.0


def test_bot_features_content_duplicate():
    acc = Account(did="did:1", handle="user")
    posts = [
        Post(
            uri="1",
            cid="1",
            author_did="did",
            text="Spam link https://x.com",
            created_at=datetime.now(UTC),
        ),
        Post(
            uri="2",
            cid="2",
            author_did="did",
            text="Spam link https://x.com",
            created_at=datetime.now(UTC),
        ),
        Post(uri="3", cid="3", author_did="did", text="Other text", created_at=datetime.now(UTC)),
    ]
    feats = compute_all_features(acc, posts)
    # 2 duplicate texts, 3 total texts. Unique = 2. 1 - (2/3) = 0.333
    assert abs(feats["content_duplicate_ratio"] - 0.333) < 0.01


def test_handcrafted_bot_vs_human():
    from app.services.bot_scoring import BotScoringService

    # We can mock the service just to check the score
    class MockService(BotScoringService):
        def __init__(self):
            # inject some weights directly
            self.weights = {
                "demographic_young_account": 1.0,
                "demographic_digits_handle": 0.5,
                "demographic_self_label_bot": 5.0,
                "bias": -2.0,
            }

    service = MockService()

    human = Account(
        did="did:human", handle="john_doe", created_at=datetime.now(UTC) - timedelta(days=365)
    )
    human_feats = compute_all_features(human, [])
    human_score = service._compute_score(human_feats)

    bot = Account(
        did="did:bot",
        handle="bot12345",
        created_at=datetime.now(UTC) - timedelta(days=1),
        self_labels=["bot"],
    )
    bot_feats = compute_all_features(bot, [])
    bot_score = service._compute_score(bot_feats)

    assert bot_score > human_score
