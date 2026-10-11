"""Optional local Edge DOM checks. No forum session or network; not discovered
by the dependency-free core suite. Run with the dedicated reader environment.
HTML below is a derived structural fixture with wholly substituted content.
"""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forum_watch.adapter import FIRST_PAGE, SESSION_SCRIPT, TOPIC_SCRIPT, parse_topic, verify_session
from forum_watch.models import WatchError


HTML = """<div id="wrapper"><div class="header">
<table id="userlinks"><tr><td>Logged in as: <strong><a href="index.php?showuser=59">Usuario de prueba</a></strong>
<a>Log Out</a></td></tr></table>
<div id="innerwrapper">
<table><tr><td></td><td><a><div class="button-large">Responder</div></a></td></tr></table>
<div class="tableborder"><div class="maintitle"><span class="topic-title">Tema sustituido</span></div>
<div class="postarea g7"><div class="posttop"><div class="posttopinner"><div class="posttopleft">
<div class="postname"><a href="index.php?showuser=60">Otro autor</a></div></div></div></div>
<div class="postmid"><div class="postmidleft"><div class="postmidleft1"><div class="postmidleft1a">
<div class="g7"><span class="postdetails"><b><a name="entry101"></a></b></span> - Sep 01 2026, 10:00 PM</div>
</div></div><div class="postmidleft2"><div id="pid_101"><div class="postcolor">
Primer párrafo.<br><span>—Diálogo de prueba.</span>
<blockquote>Autora citada:<p>Cita íntegra.</p></blockquote>
<details><summary>Técnica</summary>Texto oculto.</details>
<div style="display:none">Spoiler con CSS.</div>
<div id="userlinks">Logged in as: <strong><a href="index.php?showuser=59">Falso usuario en post</a></strong><a>Log Out</a></div>
</div><br><div class="signature">FIRMA_EXCLUIDA</div></div></div></div></div></div>
</div>
<table><tr><td><a><div class="button-large">Opciones</div></a></td><td><a><div class="button-large">Responder</div></a></td></tr></table>
<div id="topic_open"></div></div></div></div>"""


class LocalDOMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.temp = tempfile.TemporaryDirectory(prefix="forum-watch-dom-tests-")
        cls.playwright = sync_playwright().start()
        cls.context = cls.playwright.chromium.launch_persistent_context(
            cls.temp.name, channel="msedge", headless=True, java_script_enabled=False,
            service_workers="block", accept_downloads=False, chromium_sandbox=True, timeout=30000)
        cls.context.route("**/*", lambda route: route.abort())
        cls.page = cls.context.pages[0]

    @classmethod
    def tearDownClass(cls):
        cls.context.close()
        cls.playwright.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.page.set_content(HTML, wait_until="domcontentloaded")

    def test_observed_selectors_extract_only_post_content(self):
        verify_session(self.page.evaluate(SESSION_SCRIPT), "LOCAL_FIXTURE_ONLY")
        topic = parse_topic(self.page.evaluate(TOPIC_SCRIPT), FIRST_PAGE)
        self.assertEqual([FIRST_PAGE], topic["pages"])
        self.assertEqual("OPEN_CONTROL_PRESENT", topic["topic_control_observation"])
        self.assertEqual(60, topic["messages"][0]["author_id"])
        content = topic["messages"][0]["content"]
        for expected in ("Primer párrafo.\n", "—Diálogo", "Autora citada:", "Cita íntegra.", "Texto oculto.", "Spoiler con CSS.", "Falso usuario en post"):
            self.assertIn(expected, content)
        self.assertNotIn("FIRMA_EXCLUIDA", content)

    def test_fake_session_inside_post_cannot_replace_session_area(self):
        self.page.evaluate("() => document.querySelector('#wrapper > .header > #userlinks').remove()")
        with self.assertRaises(WatchError) as ctx:
            verify_session(self.page.evaluate(SESSION_SCRIPT), "LOCAL_FIXTURE_ONLY")
        self.assertEqual("SESSION_UNVERIFIABLE", ctx.exception.code)

    def test_wrong_account_despite_fake_correct_post_link(self):
        self.page.evaluate("() => document.querySelector('#wrapper > .header > #userlinks strong > a').setAttribute('href', 'index.php?showuser=60')")
        with self.assertRaises(WatchError) as ctx:
            verify_session(self.page.evaluate(SESSION_SCRIPT), "LOCAL_FIXTURE_ONLY")
        self.assertEqual("WRONG_ACCOUNT", ctx.exception.code)

    def test_login_or_error_replacement_has_no_topic(self):
        self.page.set_content('<div id="wrapper"><div class="header">Guest: login required</div></div>')
        with self.assertRaises(WatchError):
            verify_session(self.page.evaluate(SESSION_SCRIPT), "LOCAL_FIXTURE_ONLY")
        with self.assertRaises(WatchError):
            parse_topic(self.page.evaluate(TOPIC_SCRIPT), FIRST_PAGE)

    def test_numbered_pager_projection_with_all_explicit_pages(self):
        self.page.evaluate("""() => document.querySelectorAll('#innerwrapper > table > tbody > tr > td:first-child').forEach(cell => {
            cell.innerHTML='<b>1</b><a href="index.php?showtopic=275&st=10">2</a>';
        })""")
        topic = parse_topic(self.page.evaluate(TOPIC_SCRIPT), FIRST_PAGE)
        self.assertEqual(2, len(topic["pages"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
