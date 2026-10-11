"""Offline bootstrap boundaries; these tests do not open a browser or visit a site."""

from contextlib import contextmanager
import io
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from forum_watch.browser import (INITIAL_URL, PROFILE_MARKER, WORKSPACE, allowed_topic_url,
                                manual_login, prepare_profile, profile_lock)
from forum_watch.models import WatchError


class FakeError(Exception):
    pass


class FakeTimeout(FakeError):
    pass


class FakePage:
    def __init__(self, final_url=INITIAL_URL, wait_error=None):
        self.url = final_url
        self.wait_error = wait_error
        self.visits = []

    def goto(self, url, **kwargs):
        self.visits.append(url)

    def wait_for_event(self, event, **kwargs):
        assert event == "close"
        if self.wait_error:
            raise self.wait_error


class FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self.browser = self
        self.closed = False
        self.guards = []

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True

    def route(self, pattern, callback):
        self.guards.append(callback)

    def unroute(self, pattern, callback):
        pass


class FakePlaywright:
    def __init__(self, page):
        self.context = FakeContext(page)
        self.chromium = self
        self.launch_options = None

    def launch_persistent_context(self, directory, **kwargs):
        self.launch_options = kwargs
        return self.context


@contextmanager
def fake_browser(page):
    playwright = FakePlaywright(page)
    module = ModuleType("playwright.sync_api")
    module.Error = FakeError
    module.TimeoutError = FakeTimeout
    module.sync_playwright = lambda: FakeManager(playwright)
    with patch.dict("sys.modules", {"playwright.sync_api": module}):
        yield playwright


class FakeManager:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_):
        pass


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="forum-watch-bootstrap-")
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name) / "dedicated"

    def test_creates_marked_external_profile_without_touching_personal_browser(self):
        path = prepare_profile(self.profile)
        self.assertTrue((path / PROFILE_MARKER).is_file())
        self.assertFalse(path.is_relative_to(WORKSPACE))
        self.assertEqual(path, prepare_profile(self.profile))

    def test_refuses_existing_unmarked_directory_without_reading_its_files(self):
        self.profile.mkdir()
        sentinel = self.profile / "personal-data-placeholder"
        sentinel.write_text("test placeholder only", encoding="utf-8")
        with self.assertRaises(WatchError) as caught:
            prepare_profile(self.profile)
        self.assertEqual("NON_DEDICATED_PROFILE", caught.exception.code)
        self.assertFalse((self.profile / PROFILE_MARKER).exists())

    def test_refuses_project_and_narrative_parent_paths(self):
        for path in (WORKSPACE, WORKSPACE / "memory", WORKSPACE.parent / "another-scene", WORKSPACE.parent):
            with self.subTest(path=path), self.assertRaises(WatchError) as caught:
                prepare_profile(path)
            self.assertEqual("PROTECTED_PROFILE_PATH", caught.exception.code)

    def test_refuses_changed_marker(self):
        prepare_profile(self.profile)
        (self.profile / PROFILE_MARKER).write_text("other tool", encoding="utf-8")
        with self.assertRaises(WatchError):
            prepare_profile(self.profile)

    def test_profile_lock_rejects_overlap_and_is_released(self):
        path = prepare_profile(self.profile)
        with profile_lock(path):
            with self.assertRaises(WatchError) as caught:
                with profile_lock(path):
                    self.fail("Second profile owner acquired lock")
            self.assertEqual("PROFILE_BUSY", caught.exception.code)
        with profile_lock(path):
            pass

    def test_only_topic_275_and_its_pages_are_automatic_destinations(self):
        self.assertEqual(275, allowed_topic_url(INITIAL_URL).topic_id)
        self.assertEqual(275, allowed_topic_url("https://narutorol.jcink.net/index.php?showtopic=275&st=20").topic_id)
        for url in ("https://example.org/index.php?showtopic=275",
                    "https://narutorol.jcink.net/index.php?showtopic=276",
                    "https://narutorol.jcink.net/index.php?showuser=59",
                    "https://narutorol.jcink.net/index.php?showtopic=275&act=Post"):
            with self.subTest(url=url), self.assertRaises(WatchError):
                allowed_topic_url(url)

    def test_login_closure_does_not_assert_identity_or_import(self):
        page = FakePage()
        with fake_browser(page) as playwright, patch("sys.stderr", new=io.StringIO()):
            result = manual_login(self.profile)
        self.assertEqual("NOT_VERIFIED", result["session_identity_status"])
        self.assertEqual((0, 0), (result["messages_extracted"], result["captures_imported"]))
        self.assertEqual([INITIAL_URL], page.visits)
        self.assertTrue(playwright.context.closed)
        options = playwright.launch_options
        self.assertEqual("msedge", options["channel"])
        self.assertFalse(options["headless"])
        self.assertFalse(options["accept_downloads"])
        self.assertNotIn("record_video_dir", options)
        self.assertNotIn("record_har_path", options)
        self.assertNotIn("traces_dir", options)
        self.assertNotIn("args", options)

    def test_login_timeout_does_not_extract_or_assert_success(self):
        with fake_browser(FakePage(wait_error=FakeTimeout())), patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(WatchError) as caught:
                manual_login(self.profile, timeout_seconds=1)
        self.assertEqual("LOGIN_TIMEOUT", caught.exception.code)

    def test_final_redirect_to_other_topic_or_host_is_rejected(self):
        for url in ("https://example.org/", "https://narutorol.jcink.net/index.php?showtopic=276"):
            with self.subTest(url=url), fake_browser(FakePage(final_url=url)) as playwright:
                with self.assertRaises(WatchError):
                    manual_login(self.profile)
            self.assertTrue(playwright.context.closed)

    def test_initial_navigation_guard_blocks_unapproved_redirect_before_request(self):
        with fake_browser(FakePage()) as playwright, patch("sys.stderr", new=io.StringIO()):
            manual_login(self.profile)
        guard = playwright.context.guards[0]

        class Request:
            url = "https://narutorol.jcink.net/index.php?showtopic=276"
            def is_navigation_request(self):
                return True

        class Route:
            request = Request()
            aborted = False
            continued = False
            def abort(self):
                self.aborted = True
            def continue_(self):
                self.continued = True

        route = Route()
        guard(route)
        self.assertTrue(route.aborted)
        self.assertFalse(route.continued)

    def test_raw_browser_error_with_session_details_is_not_reported(self):
        with fake_browser(FakePage(wait_error=FakeError("secret-placeholder"))), patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(WatchError) as caught:
                manual_login(self.profile)
        self.assertEqual("BROWSER_START_OR_LOGIN_FAILED", caught.exception.code)
        self.assertNotIn("secret-placeholder", str(caught.exception))

    def test_invalid_timeout_fails_before_creating_profile(self):
        with self.assertRaises(WatchError):
            manual_login(self.profile, timeout_seconds=0)
        self.assertFalse(self.profile.exists())


if __name__ == "__main__":
    unittest.main()
