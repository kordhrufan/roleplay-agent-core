"""Offline checks for the two explicitly authorized manual demo stages."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import discord_manual_smoke
from forum_watch import notifications
from forum_watch.discord import Delivery
from forum_watch.models import INITIAL_URL, WatchError
from forum_watch.store import Store
from test_notifications import Transport


class ManualDiscordDemoTests(unittest.TestCase):
    def test_two_stages_reuse_events_without_resending_or_real_forum_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "demo"
            sender = Transport(Delivery("SENT", remote_message_id="111"),
                               Delivery("SENT", remote_message_id="222"))
            original = notifications.send_pending
            def send(store, **kwargs):
                return original(store, sender, control=Path(temporary)/"control", **kwargs)
            with patch.object(notifications, "send_pending", side_effect=send), contextlib.redirect_stdout(io.StringIO()):
                for stage in ("connection", "connection", "pipeline", "pipeline"):
                    with patch("sys.argv", ["demo", "--output-root", str(folder), "--stage", stage]):
                        self.assertEqual(0, discord_manual_smoke.main())
            self.assertEqual(2, len(sender.calls))
            self.assertEqual(notifications.CONNECTION_TEST, sender.calls[0]["content"])
            self.assertIn("PRUEBA / DATOS SINTÉTICOS", sender.calls[1]["content"])
            self.assertNotIn("Me detuve a escuchar", sender.calls[1]["content"])
            with Store(folder/"discord-synthetic.sqlite3") as store:
                self.assertEqual("SYNTHETIC_ONLY", store.storage_mode)
                self.assertEqual({"SYNTHETIC"}, {r[0] for r in store.conn.execute("SELECT origin FROM captures")})
                self.assertEqual(1, store.conn.execute("SELECT count(*) FROM narrative_drafts").fetchone()[0])
                self.assertEqual(2, store.conn.execute("SELECT count(*) FROM notifications").fetchone()[0])
                self.assertEqual("PAUSED", store.inspect(INITIAL_URL)["state"])

    def test_preview_queues_without_secret_or_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "preview"
            with patch.object(notifications, "send_pending") as send, contextlib.redirect_stdout(io.StringIO()), \
                    patch("sys.argv", ["demo", "--output-root", str(folder), "--stage", "connection", "--prepare-only"]):
                self.assertEqual(0, discord_manual_smoke.main())
            send.assert_not_called()
            report = json.loads((folder/"connection-preview.json").read_text(encoding="utf-8"))
            self.assertEqual("PENDING", report["notifications"][0]["status"])

    def test_connection_test_cannot_modify_real_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"real.sqlite3"
            with Store(path, create=True, storage_mode="AUTHENTICATED_ONLY") as store:
                store.add(INITIAL_URL)
                before = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master")}
                with self.assertRaises(WatchError):
                    notifications.connection_test(store)
                self.assertEqual(before, {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master")})

    def test_pipeline_requires_confirmed_first_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "unconfirmed"
            with contextlib.redirect_stdout(io.StringIO()), patch("sys.argv", [
                    "demo", "--output-root", str(folder), "--stage", "connection", "--prepare-only"]):
                discord_manual_smoke.main()
            with patch("sys.argv", ["demo", "--output-root", str(folder), "--stage", "pipeline"]), self.assertRaises(WatchError):
                discord_manual_smoke.main()


if __name__ == "__main__":
    unittest.main()

