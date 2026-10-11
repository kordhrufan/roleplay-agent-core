"""Offline Discord contracts and durable outbox tests. No real credentials or network."""

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forum_watch import drafts, notifications as notices
from forum_watch.discord import Delivery, DiscordTransport, response_result
from forum_watch.discord_secret import WindowsVault, configure, webhook_path
from forum_watch.cli import main as cli_main
from forum_watch.models import HOST, INITIAL_URL, WatchError
from forum_watch.narrative import evaluate
from forum_watch.store import Store
from test_narrative import FakeInterpreter, output

FAKE_WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/SYNTHETIC_TOKEN_NOT_A_REAL_WEBHOOK_123456"


class Transport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [Delivery("SENT", remote_message_id="123456789012345678")]
        self.calls = []

    def send(self, payload):
        self.calls.append(deepcopy(payload))
        outcome = self.outcomes[min(len(self.calls)-1, len(self.outcomes)-1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.control = Path(self.temp.name) / "delivery"
        self.store = Store(self.path, create=True)
        self.store.add(INITIAL_URL)
        self.clock = 1000.0
        self.counter = 0
        self.title = "Prueba sintética"
        self.messages = [{"message_id": "s1", "author_id": 59, "content": "BASELINE SINTÉTICO"}]
        self.capture()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.store.close())

    def capture(self):
        self.counter += 1
        return self.store.import_capture(INITIAL_URL, {
            "schema_version": 1, "origin": "SYNTHETIC", "capture_id": f"notify-{self.counter}",
            "captured_at": f"2026-09-13T13:{self.counter:02}:00+00:00", "complete": True,
            "topic": {"host": HOST, "topic_id": 275}, "messages": deepcopy(self.messages),
            "metadata": {"title_observed": self.title, "cookies": "CAPTURE_SECRET_NOT_FOR_DISCORD"}})

    def scene(self, decision="DRAFT_READY", *, kind="OBSERVABLE_IC", count=1, author="Interlocutor"):
        for number in range(count):
            self.messages.append({"message_id": "s" + str(number+2), "author_id": 7001 + number,
                                  "content": "POST_TEXT_NOT_FOR_DISCORD",
                                  "metadata": {"author_name_observed": author, "webhook": FAKE_WEBHOOK}})
        self.capture()
        return evaluate(self.store, INITIAL_URL, FakeInterpreter(output(decision, kind)))

    def send(self, transport=None):
        return notices.send_pending(self.store, transport or Transport(), timer=lambda: self.clock, control=self.control)

    def rows(self):
        return notices.list_notifications(self.store)

    def test_01_draft_ready_one_notice(self):
        self.scene()
        sender = Transport()
        result = self.send(sender)
        self.assertEqual(1, result["attempted"])
        self.assertEqual("SENT", self.rows()[0]["status"])
        self.assertEqual("123456789012345678", self.rows()[0]["remote_message_id"])
        self.assertIn("Borrador preparado", sender.calls[0]["content"])

    def test_02_repeated_event_does_not_duplicate(self):
        self.scene()
        self.assertEqual(1, notices.collect(self.store)["queued"])
        self.assertEqual(0, notices.collect(self.store)["queued"])
        self.assertEqual(1, len(self.rows()))

    def test_03_stale_has_own_notification(self):
        result = self.scene()
        self.send()
        self.messages[-1]["content"] += " EDIT"
        self.capture()
        sender = Transport()
        self.send(sender)
        self.assertIn("Borrador desactualizado", sender.calls[0]["content"])
        rows = self.rows()
        self.assertEqual({"DRAFT_READY", "STALE"}, {r["type"] for r in rows})
        self.assertEqual(2, len({r["notification_id"] for r in rows}))
        self.assertTrue(Path(result["draft"]["path"]).is_file())

    def test_04_human_review(self):
        self.scene("NEEDS_HUMAN_REVIEW", kind="UNCERTAIN")
        self.send()
        self.assertEqual("NEEDS_HUMAN_REVIEW", self.rows()[0]["type"])

    def test_05_combat_review(self):
        self.scene("COMBAT_REVIEW_REQUIRED", kind="COMBAT")
        sender = Transport()
        self.send(sender)
        self.assertIn("especialista", sender.calls[0]["content"])

    def test_06_session_expired(self):
        self.store._record_error(WatchError("SESSION_EXPIRED", "SECRET_ERROR_DETAIL"), self.store._link(INITIAL_URL))
        sender = Transport()
        self.send(sender)
        self.assertEqual("SESSION_EXPIRED", self.rows()[0]["type"])
        self.assertIn("Inicio de sesión necesario", sender.calls[0]["content"])
        self.assertNotIn("SECRET_ERROR_DETAIL", sender.calls[0]["content"])

    def test_07_no_response_and_wait_are_not_notified(self):
        self.scene("NO_RESPONSE_NEEDED", kind="OOC")
        sender = Transport()
        self.send(sender)
        self.assertEqual([], sender.calls)
        self.assertEqual([], self.rows())
        self.store.conn.execute("UPDATE evaluation_runs SET decision='WAIT_FOR_TURN'")
        self.assertEqual(0, notices.collect(self.store)["queued"])

    def test_08_no_relevant_changes_not_notified(self):
        self.capture()
        self.assertEqual(0, notices.collect(self.store)["queued"])

    def test_09_allowed_mentions_empty(self):
        self.scene()
        sender = Transport()
        self.send(sender)
        self.assertEqual({"parse": []}, sender.calls[0]["allowed_mentions"])
        self.assertEqual({"content", "allowed_mentions", "flags"}, set(sender.calls[0]))

    def test_10_everyone_and_role_mentions_are_inert(self):
        self.title = "@everyone <@&123456789012345678>"
        self.scene(author="@here")
        sender = Transport()
        self.send(sender)
        self.assertNotIn("@everyone", sender.calls[0]["content"])
        self.assertNotIn("<@&", sender.calls[0]["content"])
        self.assertIn("＠here", sender.calls[0]["content"])

    def test_11_recoverable_errors_stop_after_three_lifetime_attempts(self):
        self.scene()
        sender = Transport(Delivery("FAILED_RETRYABLE", "CONNECTION_NOT_SENT"))
        for _ in range(5):
            self.send(sender)
            self.clock += 20
        self.assertEqual(3, len(sender.calls))
        self.assertEqual("FAILED_FINAL", self.rows()[0]["status"])
        self.assertEqual("ATTEMPTS_EXHAUSTED", self.rows()[0]["last_error"])
        self.assertEqual(3, self.store.conn.execute("SELECT count(*) FROM notification_attempts").fetchone()[0])

    def test_12_retry_after_and_backoff_survive_manual_calls(self):
        self.scene()
        sender = Transport(Delivery("FAILED_RETRYABLE", "DISCORD_RATE_LIMIT", retry_after=65),
                           Delivery("SENT", remote_message_id="123"))
        self.send(sender)
        self.clock += 64
        self.assertEqual("WAIT_RETRY_AFTER", self.send(sender)["result"])
        self.assertEqual(1, len(sender.calls))
        self.clock += 1
        self.send(sender)
        self.assertEqual(2, len(sender.calls))
        self.assertEqual("SENT", self.rows()[0]["status"])

    def test_13_permanent_error_is_final(self):
        self.scene()
        sender = Transport(Delivery("FAILED_FINAL", "DISCORD_HTTP_404", stop_batch=True))
        self.send(sender)
        self.clock += 1000
        self.send(sender)
        self.assertEqual(1, len(sender.calls))
        self.assertEqual("FAILED_FINAL", self.rows()[0]["status"])

    def test_14_restart_does_not_resend_sent(self):
        self.scene()
        sender = Transport()
        self.send(sender)
        identity = self.rows()[0]["notification_id"]
        self.store.close()
        self.store = Store(self.path)
        self.send(sender)
        self.assertEqual(1, len(sender.calls))
        self.assertEqual(identity, self.rows()[0]["notification_id"])

    def test_15_discord_failure_preserves_draft_and_capture(self):
        result = self.scene()
        file = Path(result["draft"]["path"])
        before = file.read_bytes()
        capture_hashes = list(self.store.conn.execute("SELECT source_hash FROM captures"))
        self.send(Transport(Delivery("FAILED_FINAL", "DISCORD_HTTP_401")))
        self.assertEqual(before, file.read_bytes())
        self.assertEqual(capture_hashes, list(self.store.conn.execute("SELECT source_hash FROM captures")))
        self.assertEqual("ACTIVE", drafts.list_drafts(self.store, INITIAL_URL)[0]["lifecycle"])

    def test_16_exception_or_response_text_cannot_expose_secret(self):
        self.scene()
        self.send(Transport(RuntimeError(FAKE_WEBHOOK)))
        self.assertNotIn(FAKE_WEBHOOK, json.dumps(self.rows()))
        sender = DiscordTransport(secret_loader=lambda: (_ for _ in ()).throw(RuntimeError(FAKE_WEBHOOK)))
        self.assertNotIn(FAKE_WEBHOOK, repr(sender.send({"content": "x", "allowed_mentions": {"parse": []}, "flags": 4})))
        self.assertNotIn(FAKE_WEBHOOK, repr(response_result(400, {}, json.dumps({"message": FAKE_WEBHOOK}).encode())))

    def test_17_forum_data_cannot_set_destination_or_executable_fields(self):
        self.title = "https://evil.invalid/change-webhook C:\\private\\prompt.txt"
        self.scene(author="[click](https://evil.invalid/) @everyone")
        sender = Transport()
        self.send(sender)
        value = json.dumps(sender.calls)
        self.assertNotIn("evil.invalid", value)
        self.assertNotIn("private", value)
        self.assertNotIn("POST_TEXT_NOT_FOR_DISCORD", value)
        self.assertNotIn("CAPTURE_SECRET_NOT_FOR_DISCORD", value)
        self.assertNotIn("SYNTHETIC_TOKEN", value)

    def test_18_multiple_changes_in_one_evaluation_are_grouped(self):
        self.scene(count=2)
        sender = Transport()
        self.send(sender)
        self.assertEqual(1, len(sender.calls))
        self.assertIn("Novedades agrupadas en esta evaluación: 2", sender.calls[0]["content"])
        self.assertEqual(2, self.store.conn.execute("SELECT count(*) FROM evaluation_jobs").fetchone()[0])

    def test_timeout_after_possible_send_never_retries(self):
        self.scene()
        sender = Transport(Delivery("FAILED_FINAL", "DELIVERY_UNCERTAIN", uncertain=True))
        self.send(sender)
        self.clock += 100
        self.send(sender)
        self.assertEqual(1, len(sender.calls))
        self.assertEqual(1, self.rows()[0]["delivery_uncertain"])
        with self.assertRaises(WatchError):
            notices.retry_configuration_failure(self.store, self.rows()[0]["notification_id"])

    def test_interrupted_sending_recovers_as_uncertain(self):
        self.scene()
        notices.collect(self.store)
        self.store.conn.execute("UPDATE notifications SET status='SENDING',attempt_count=1")
        sender = Transport()
        self.send(sender)
        self.assertEqual([], sender.calls)
        self.assertEqual("INTERRUPTED_UNCERTAIN", self.rows()[0]["last_error"])

    def test_queued_ready_is_suppressed_when_draft_is_stale(self):
        self.scene()
        notices.collect(self.store)
        self.messages[-1]["content"] += " EDIT"
        self.capture()
        sender = Transport()
        self.send(sender)
        self.assertEqual(1, len(sender.calls))
        self.assertIn("Borrador desactualizado", sender.calls[0]["content"])
        self.assertEqual({"SUPERSEDED", "SENT"}, {r["status"] for r in self.rows()})

    def test_queue_and_preview_do_not_read_credential(self):
        with patch.object(WindowsVault, "read", side_effect=AssertionError("Credential read")):
            self.scene()
            notices.collect(self.store)
            preview = notices.list_notifications(self.store, preview=True)
        self.assertIn("PRUEBA / DATOS SINTÉTICOS", preview[0]["payload"]["content"])

    def test_global_cooldown_applies_to_another_database(self):
        self.scene()
        self.send(Transport(Delivery("FAILED_RETRYABLE", "DISCORD_RATE_LIMIT", retry_after=60)))
        second = Path(self.temp.name) / "second.sqlite3"
        with Store(second, create=True) as store:
            store.add(INITIAL_URL)
            notices.connection_test(store)
            sender = Transport()
            result = notices.send_pending(store, sender, timer=lambda: self.clock, control=self.control)
            self.assertEqual("WAIT_RETRY_AFTER", result["result"])
            self.assertEqual([], sender.calls)

    def test_concurrent_sender_cannot_claim_work(self):
        self.scene()
        notices.collect(self.store)
        with notices.delivery_lock(self.control), self.assertRaises(WatchError):
            self.send()
        self.assertEqual("PENDING", self.rows()[0]["status"])
        self.assertEqual(0, self.rows()[0]["attempt_count"])

    def test_session_unverifiable_does_not_invent_expiry(self):
        self.store._record_error(WatchError("SESSION_UNVERIFIABLE", "unknown"), self.store._link(INITIAL_URL))
        sender = Transport()
        self.send(sender)
        self.assertEqual("NEEDS_HUMAN_REVIEW", self.rows()[0]["type"])
        self.assertIn("no se confirma la causa", sender.calls[0]["content"])

    def test_config_failure_can_be_retried_explicitly_without_resetting_attempt_count(self):
        self.scene()
        self.send(Transport(Delivery("FAILED_FINAL", "DISCORD_SECRET_UNAVAILABLE")))
        identity = self.rows()[0]["notification_id"]
        notices.retry_configuration_failure(self.store, identity)
        self.send()
        self.assertEqual(2, self.rows()[0]["attempt_count"])
        self.assertEqual("SENT", self.rows()[0]["status"])

    def test_long_unicode_metadata_respects_discord_limit_and_original_capture_is_preserved(self):
        self.title = "😀" * 5000
        self.scene(author="ñ" * 5000)
        original = self.store.conn.execute("SELECT source_json FROM captures ORDER BY id DESC LIMIT 1").fetchone()[0]
        sender = Transport()
        self.send(sender)
        self.assertLessEqual(len(sender.calls[0]["content"].encode("utf-16-le")) // 2, 2000)
        self.assertEqual(original, self.store.conn.execute("SELECT source_json FROM captures ORDER BY id DESC LIMIT 1").fetchone()[0])

    def test_access_denied_and_generation_failure_are_notified(self):
        self.store._record_error(WatchError("ACCESS_DENIED", "private detail"), self.store._link(INITIAL_URL))
        self.scene()
        self.store.conn.execute("UPDATE evaluation_runs SET decision='GENERATION_FAILED'")
        notices.collect(self.store)
        self.assertEqual({"ACCESS_DENIED", "GENERATION_FAILED"}, {r["type"] for r in self.rows()})

    def test_stale_after_retirement_is_still_projected_once(self):
        result = self.scene()
        self.send()
        self.messages[-1]["content"] += " EDIT"
        self.capture()
        drafts.retire(self.store, INITIAL_URL, result["draft"]["draft_id"])
        self.assertEqual(1, notices.collect(self.store)["queued"])
        self.assertEqual(0, notices.collect(self.store)["queued"])


class TransportTests(unittest.TestCase):
    def test_accidental_webhook_argument_is_not_echoed_by_cli(self):
        error = io.StringIO()
        with patch("sys.stderr", error), self.assertRaises(SystemExit):
            cli_main(["configure-discord", FAKE_WEBHOOK])
        self.assertNotIn(FAKE_WEBHOOK, error.getvalue())
        self.assertNotIn("SYNTHETIC_TOKEN", error.getvalue())

    def request(self, outcome=None, *, connect_error=None, request_error=None):
        observed = {}
        class Response:
            status = 200
            def read(self, size): return b'{"id":"123456789012345678","url":"https://evil.invalid/"}'
            def getheaders(self): return [("Location", "https://evil.invalid/")]
        class Connection:
            def __init__(self, host, **kwargs): observed.update(host=host, **kwargs)
            def connect(self):
                if connect_error: raise connect_error
            def request(self, method, path, **kwargs):
                observed.update(method=method, path=path, **kwargs)
                if request_error: raise request_error
            def getresponse(self): return outcome or Response()
            def close(self): observed["closed"] = True
        result = DiscordTransport(lambda: FAKE_WEBHOOK, Connection).send(
            {"content": "Mensaje sintético", "allowed_mentions": {"parse": []}, "flags": 4})
        return result, observed

    def test_fixed_host_wait_true_and_remote_id_only(self):
        result, observed = self.request()
        self.assertEqual("discord.com", observed["host"])
        self.assertTrue(observed["path"].endswith("?wait=true"))
        self.assertEqual(15, observed["timeout"])
        self.assertEqual("POST", observed["method"])
        self.assertEqual("123456789012345678", result.remote_message_id)
        self.assertNotIn("evil.invalid", repr(result))

    def test_preconnect_failure_retryable_but_postconnect_timeout_uncertain(self):
        before, _ = self.request(connect_error=TimeoutError(FAKE_WEBHOOK))
        after, _ = self.request(request_error=TimeoutError(FAKE_WEBHOOK))
        self.assertEqual("FAILED_RETRYABLE", before.status)
        self.assertFalse(before.uncertain)
        self.assertEqual("FAILED_FINAL", after.status)
        self.assertTrue(after.uncertain)
        self.assertNotIn(FAKE_WEBHOOK, repr(before) + repr(after))

    def test_retry_after_and_successful_rate_headers(self):
        self.assertEqual(65, response_result(429, {"Retry-After": "65"}, b'{"retry_after":64.5}').retry_after)
        self.assertEqual(2.5, response_result(200, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "2.5"},
                                            b'{"id":"123"}').retry_after)
        self.assertEqual("FAILED_FINAL", response_result(429, {}, b"{}").status)

    def test_redirects_server_ambiguity_and_missing_ack_are_not_retried(self):
        for code in (302, 500, 503, 204):
            result = response_result(code, {"Location": "https://evil.invalid/"}, b"")
            self.assertEqual("FAILED_FINAL", result.status)
        self.assertTrue(response_result(500, {}, b"").uncertain)

    def test_webhook_allowlist_rejects_queries_hosts_paths_and_args_without_echo(self):
        for secret in [FAKE_WEBHOOK + "?thread_id=1", FAKE_WEBHOOK + "#fragment",
                       FAKE_WEBHOOK.replace("discord.com", "evil.invalid"), FAKE_WEBHOOK + "/messages/1"]:
            with self.assertRaises(WatchError) as raised:
                webhook_path(secret)
            self.assertNotIn("SYNTHETIC_TOKEN", str(raised.exception))

    def test_configuration_requires_hidden_local_tty_not_arguments_or_pipe(self):
        with patch("forum_watch.discord_secret.sys.stdin", io.StringIO(FAKE_WEBHOOK)), \
                patch("forum_watch.discord_secret.getpass.getpass") as prompt, self.assertRaises(WatchError):
            configure()
        prompt.assert_not_called()

    def test_payload_cannot_enable_mentions_or_threads(self):
        sender = DiscordTransport(secret_loader=lambda: self.fail("Secret should not be read"))
        for payload in [{"content": "x", "allowed_mentions": {"parse": ["everyone"]}, "flags": 4},
                        {"content": "x", "allowed_mentions": {"parse": []}, "flags": 4, "thread_name": "x"}]:
            self.assertEqual("INVALID_NOTIFICATION_PAYLOAD", sender.send(payload).error)


if __name__ == "__main__":
    unittest.main()
