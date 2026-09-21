import json
from datetime import datetime, UTC
from unittest.mock import MagicMock

from app.jobs.collector import JetstreamConsumer


def test_jetstream_parse_message_valid():
    repo = MagicMock()
    consumer = JetstreamConsumer(repo)
    
    fixture = {
        "did": "did:plc:x",
        "time_us": 123456789,
        "kind": "commit",
        "commit": {
            "rev": "rev",
            "operation": "create",
            "collection": "app.bsky.feed.post",
            "rkey": "rkey123",
            "record": {
                "text": "Teste política no governo",
                "createdAt": "2023-11-20T12:00:00Z",
                "langs": ["pt"]
            },
            "cid": "cid123"
        }
    }
    
    msg = json.dumps(fixture)
    post_data = consumer.parse_message(msg)
    
    assert post_data is not None
    assert post_data["uri"] == "at://did:plc:x/app.bsky.feed.post/rkey123"
    assert post_data["cid"] == "cid123"
    assert post_data["author_did"] == "did:plc:x"
    assert post_data["text"] == "Teste política no governo"
    assert post_data["langs"] == ["pt"]
    assert post_data["source"] == "jetstream"
    assert post_data["time_us"] == 123456789
    assert post_data["created_at"] == datetime(2023, 11, 20, 12, 0, tzinfo=UTC)

def test_jetstream_parse_message_irrelevant_lang():
    repo = MagicMock()
    consumer = JetstreamConsumer(repo)
    
    fixture = {
        "did": "did:plc:x",
        "time_us": 123456789,
        "kind": "commit",
        "commit": {
            "operation": "create",
            "rkey": "rkey123",
            "record": {
                "text": "Teste política no governo",
                "langs": ["en"]
            }
        }
    }
    
    msg = json.dumps(fixture)
    post_data = consumer.parse_message(msg)
    assert post_data is None

def test_jetstream_parse_message_irrelevant_text():
    repo = MagicMock()
    consumer = JetstreamConsumer(repo)
    
    fixture = {
        "did": "did:plc:x",
        "time_us": 123456789,
        "kind": "commit",
        "commit": {
            "operation": "create",
            "rkey": "rkey123",
            "record": {
                "text": "Apenas um post normal",
                "langs": ["pt"]
            }
        }
    }
    
    msg = json.dumps(fixture)
    post_data = consumer.parse_message(msg)
    assert post_data is None
