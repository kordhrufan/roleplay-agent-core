"""Outbound-only Discord webhook transport; no redirects, proxies or raw logging."""

from dataclasses import dataclass
import http.client
import json
import math
import re
import ssl

from .models import WatchError
from .discord_secret import read_webhook, webhook_path

TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class Delivery:
    status: str
    error: str | None = None
    remote_message_id: str | None = None
    retry_after: float = 0
    uncertain: bool = False
    stop_batch: bool = False


def seconds(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and 0 <= result <= 31_536_000 else None
    except (ValueError, TypeError, OverflowError):
        return None


def response_result(status, headers, body):
    """Never persist response body, Location, URL or arbitrary Discord error text."""
    headers = {k.lower(): v for k, v in headers.items()}
    try:
        parsed = json.loads(body)
        parsed = parsed if isinstance(parsed, dict) else {}
    except (ValueError, UnicodeError):
        parsed = {}
    header_delay = seconds(headers.get("retry-after"))
    reset_delay = seconds(headers.get("x-ratelimit-reset-after")) if headers.get("x-ratelimit-remaining") == "0" else 0
    body_delay = seconds(parsed.get("retry_after"))
    delay = max(header_delay or 0, reset_delay or 0, body_delay or 0)
    if 200 <= status < 300:
        message_id = parsed.get("id")
        if isinstance(message_id, str) and re.fullmatch(r"[0-9]{1,30}", message_id):
            return Delivery("SENT", remote_message_id=message_id, retry_after=delay)
        return Delivery("FAILED_FINAL", "CONFIRMATION_MISSING", uncertain=True, stop_batch=True)
    if status == 429:
        if header_delay is None and body_delay is None:
            return Delivery("FAILED_FINAL", "INVALID_RETRY_AFTER", stop_batch=True)
        return Delivery("FAILED_RETRYABLE", "DISCORD_RATE_LIMIT", retry_after=delay, stop_batch=True)
    if 500 <= status <= 599:
        # A webhook has no client idempotency key. An upstream failure does not
        # prove that its underlying message creation was rolled back.
        return Delivery("FAILED_FINAL", "REMOTE_RESULT_UNCERTAIN", uncertain=True, stop_batch=True)
    if 300 <= status <= 399:
        return Delivery("FAILED_FINAL", "DISCORD_REDIRECT_REJECTED", stop_batch=True)
    return Delivery("FAILED_FINAL", f"DISCORD_HTTP_{status}", stop_batch=True)


class DiscordTransport:
    def __init__(self, secret_loader=read_webhook, connection_factory=http.client.HTTPSConnection):
        self.secret_loader = secret_loader
        self.connection_factory = connection_factory

    def send(self, payload):
        # Projection is rebuilt by notifications.py. The transport accepts no
        # endpoint, username, upload, button or thread field from event data.
        if (not isinstance(payload, dict) or set(payload) != {"content", "allowed_mentions", "flags"}
                or payload.get("allowed_mentions") != {"parse": []} or payload.get("flags") != 4
                or not isinstance(payload.get("content"), str)
                or not 0 < len(payload["content"].encode("utf-16-le")) // 2 <= 2000):
            return Delivery("FAILED_FINAL", "INVALID_NOTIFICATION_PAYLOAD", stop_batch=True)
        try:
            path = webhook_path(self.secret_loader())
        except Exception:
            return Delivery("FAILED_FINAL", "DISCORD_SECRET_UNAVAILABLE", stop_batch=True)
        connection = None
        connected = False
        try:
            connection = self.connection_factory("discord.com", timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
            # Before connect succeeds no HTTP request has been sent.
            connection.connect()
            connected = True
            raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            connection.request("POST", path, body=raw,
                               headers={"Content-Type": "application/json", "Accept": "application/json",
                                        "User-Agent": "NozomuForumWatch/4 (manual notifications)"})
            response = connection.getresponse()
            body = response.read(65537)
            if len(body) > 65536:
                return Delivery("FAILED_FINAL", "RESPONSE_TOO_LARGE", uncertain=True, stop_batch=True)
            return response_result(response.status, dict(response.getheaders()), body)
        except ssl.SSLCertVerificationError:
            return Delivery("FAILED_FINAL", "TLS_VERIFICATION_FAILED", stop_batch=True)
        except (OSError, http.client.HTTPException):
            if connected:
                return Delivery("FAILED_FINAL", "DELIVERY_UNCERTAIN", uncertain=True, stop_batch=True)
            return Delivery("FAILED_RETRYABLE", "CONNECTION_NOT_SENT", stop_batch=True)
        except Exception:
            # No exception object is interpolated; it may contain the webhook.
            return Delivery("FAILED_FINAL", "TRANSPORT_FAILURE_UNCERTAIN", uncertain=True, stop_batch=True)
        finally:
            path = None
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass
