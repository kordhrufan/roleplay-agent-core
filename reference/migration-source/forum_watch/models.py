"""Strict data validation; imported text is never interpreted as instructions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlsplit


HOST = "narutorol.jcink.net"
STORAGE_MODE = "SYNTHETIC_ONLY"
REAL_STORAGE_MODE = "AUTHENTICATED_ONLY"
SCHEMA_VERSION = 1
INITIAL_URL = "https://narutorol.jcink.net/index.php?showtopic=275&st=0#entry1144"


class WatchError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def require(condition, code, message):
    if not condition:
        raise WatchError(code, message)


def positive_int(value, field):
    require(type(value) is int and 0 < value <= 2**63 - 1,
            "INVALID_DATA", f"{field} must be a positive 64-bit integer.")
    return value


def identifier(value, field):
    require(isinstance(value, str) and
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None,
            "INVALID_DATA", f"{field} must be a short data identifier, not a path.")
    return value


def keys(value, required, optional=()):
    require(isinstance(value, dict), "INVALID_DATA", "Expected a JSON object.")
    require(set(required) <= value.keys() and value.keys() <= set(required) | set(optional),
            "INVALID_DATA", "Missing or unsupported fields in JSON object.")


def json_text(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WatchError("INVALID_JSON", "Data must be finite JSON values.") from exc


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_JSON", "Duplicate JSON object key.")
        result[key] = value
    return result


def load_json(text):
    def reject_constant(_):
        raise WatchError("INVALID_JSON", "Non-finite JSON number.")
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=reject_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise WatchError("INVALID_JSON", "Malformed JSON document.") from exc


def digest(text):
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise WatchError("INVALID_DATA", "Text must contain valid Unicode.") from exc


def normalize_content(content):
    require(isinstance(content, str), "INVALID_DATA", "content must be text.")
    # Only line-ending representation is normalized. No stripping or HTML parsing.
    return content.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True)
class TopicLink:
    host: str
    topic_id: int
    original_url: str

    @property
    def canonical_url(self):
        return f"https://{self.host}/index.php?showtopic={self.topic_id}"


def normalize_url(url, authorized_host=HOST):
    require(isinstance(url, str) and bool(url) and
            not any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url),
            "INVALID_URL", "Expected an HTTPS topic URL without whitespace.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise WatchError("INVALID_URL", "Malformed topic URL.") from exc
    require(parsed.scheme == "https" and parsed.username is None and
            parsed.password is None and port in (None, 443) and
            parsed.path == "/index.php", "INVALID_URL", "Unsupported topic URL shape.")
    require(parsed.hostname == authorized_host, "UNAUTHORIZED_HOST", "Host is not authorized.")
    require(all(key in {"showtopic", "st"} for key, _ in pairs),
            "INVALID_URL", "Only showtopic and st query parameters are supported.")
    values = {}
    for key, value in pairs:
        require(re.fullmatch(r"[0-9]{1,19}", value) is not None,
                "INVALID_URL", "Topic and page identifiers must be decimal integers.")
        number = int(value)
        require(number <= 2**63 - 1 and (key != "showtopic" or number > 0),
                "INVALID_URL", "Topic or page identifier is out of range.")
        require(key not in values or values[key] == number,
                "CONTRADICTORY_URL", "Contradictory topic or page parameters.")
        values[key] = number
    require("showtopic" in values, "INVALID_URL", "Missing showtopic parameter.")
    return TopicLink(authorized_host, values["showtopic"], url)


@dataclass(frozen=True)
class Settings:
    authorized_host: str = HOST
    expected_account_id: int = 59
    poll_interval_seconds: int = 14400
    forum_permission: str = "USER_CONFIRMED"

    def __post_init__(self):
        require(self.authorized_host == HOST, "INVALID_CONFIG", "Unsupported authorized host.")
        positive_int(self.expected_account_id, "expected_account_id")
        positive_int(self.poll_interval_seconds, "poll_interval_seconds")
        require(self.forum_permission == "USER_CONFIRMED", "INVALID_CONFIG",
                "Forum permission must retain USER_CONFIRMED provenance.")

    def metadata(self):
        return {"storage_mode": STORAGE_MODE, "authorized_host": self.authorized_host,
                "expected_account_id": str(self.expected_account_id),
                "poll_interval_seconds": str(self.poll_interval_seconds),
                "forum_permission": self.forum_permission,
                "session_identity_status": "NOT_VERIFIED"}


def parse_config(value):
    keys(value, {"schema_version", "storage_mode", "authorized_host", "expected_account_id",
                 "poll_interval_seconds", "forum_permission", "initial_topic"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and
            value["storage_mode"] == STORAGE_MODE, "INVALID_CONFIG", "Unsupported example configuration.")
    settings = Settings(value["authorized_host"], value["expected_account_id"],
                        value["poll_interval_seconds"], value["forum_permission"])
    topic = value["initial_topic"]
    keys(topic, {"topic_id", "original_url", "state", "title", "participants",
                 "scene_classification", "memory_topic_path", "last_processed_message_id"})
    link = normalize_url(topic["original_url"], settings.authorized_host)
    require(positive_int(topic["topic_id"], "topic_id") == link.topic_id and
            topic["state"] == "PAUSED" and
            all(topic[key] is None for key in ("title", "participants", "scene_classification",
                                               "memory_topic_path", "last_processed_message_id")),
            "INVALID_CONFIG", "Initial topic must be paused with unconfirmed context and no cursor.")
    return settings, link


@dataclass(frozen=True)
class Message:
    message_id: str
    author_id: int
    content: str
    normalized_content: str
    content_hash: str
    metadata_json: str


@dataclass(frozen=True)
class Capture:
    capture_id: str
    host: str
    topic_id: int
    captured_at: str
    messages: tuple[Message, ...]
    source_json: str
    source_hash: str
    origin: str = "SYNTHETIC"

    @classmethod
    def parse(cls, value):
        return cls._parse(value, "SYNTHETIC")

    @classmethod
    def _parse(cls, value, origin):
        # Internal shared validation. External JSON always enters through parse().
        keys(value, {"schema_version", "origin", "capture_id", "captured_at", "complete",
                     "topic", "messages"}, {"metadata"})
        require(type(value["schema_version"]) is int and value["schema_version"] == (1 if origin == "SYNTHETIC" else 2),
                "INVALID_DATA", "Unsupported capture format version.")
        require(value["origin"] == origin, "NON_SYNTHETIC", "External capture files must be SYNTHETIC.")
        capture_id = identifier(value["capture_id"], "capture_id")
        require(type(value["complete"]) is bool, "INVALID_DATA", "complete must be a boolean.")
        require(value["complete"], "INCOMPLETE_CAPTURE", "Capture is incomplete; state was not advanced.")
        keys(value["topic"], {"host", "topic_id"})
        host = value["topic"]["host"]
        require(isinstance(host, str) and host == HOST, "UNAUTHORIZED_HOST", "Capture host is not authorized.")
        topic_id = positive_int(value["topic"]["topic_id"], "topic_id")
        try:
            require(isinstance(value["captured_at"], str), "INVALID_DATA", "captured_at must be ISO 8601 text.")
            captured_at = datetime.fromisoformat(value["captured_at"])
            require(captured_at.tzinfo is not None and "T" in value["captured_at"],
                    "INVALID_DATA", "captured_at requires time and timezone; it is not an IC date.")
            timestamp = captured_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
        except (ValueError, OverflowError) as exc:
            raise WatchError("INVALID_DATA", "Invalid capture timestamp.") from exc
        require(isinstance(value.get("metadata", {}), dict), "INVALID_DATA", "metadata must be an object.")
        require(isinstance(value["messages"], list), "INVALID_DATA", "messages must be an ordered array.")
        messages = []
        seen = set()
        for item in value["messages"]:
            keys(item, {"message_id", "author_id", "content"}, {"metadata"})
            message_id = identifier(item["message_id"], "message_id")
            require(message_id not in seen, "DUPLICATE_MESSAGE", "A capture cannot repeat a message ID.")
            seen.add(message_id)
            normalized = normalize_content(item["content"])
            require(isinstance(item.get("metadata", {}), dict), "INVALID_DATA", "Message metadata must be an object.")
            messages.append(Message(message_id, positive_int(item["author_id"], "author_id"),
                                    item["content"], normalized, digest(normalized),
                                    json_text(item.get("metadata", {}))))
        source = json_text(value)
        return cls(capture_id, host, topic_id, timestamp, tuple(messages), source, digest(source), origin)
