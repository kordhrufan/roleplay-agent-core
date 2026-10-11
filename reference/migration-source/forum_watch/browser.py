"""Dedicated Edge lifecycle and request boundary. Login itself proves no identity."""

from contextlib import contextmanager
from pathlib import Path
import sys
from urllib.parse import urlsplit

from .models import INITIAL_URL, WatchError, normalize_url, require


WORKSPACE = Path(__file__).resolve().parent.parent
PROFILE_MARKER = ".forum-watch-dedicated-profile-v1"
PROFILE_SIGNATURE = "Forum Watch dedicated browser profile; narutorol.jcink.net; account expected 59\n"


def profile_path(value):
    require(bool(value), "PROFILE_REQUIRED", "An explicit dedicated profile path is required.")
    path = Path(value).expanduser().resolve()
    require(not path.is_relative_to(WORKSPACE.parent) and not WORKSPACE.is_relative_to(path),
            "PROTECTED_PROFILE_PATH", "Browser profile must be outside the project and its narrative context directory.")
    return path


def prepare_profile(value):
    path = profile_path(value)
    marker = path / PROFILE_MARKER
    if path.exists():
        require(path.is_dir(), "INVALID_PROFILE", "Dedicated profile must be a directory.")
        if marker.exists():
            require(marker.read_text(encoding="utf-8") == PROFILE_SIGNATURE,
                    "INVALID_PROFILE", "Dedicated profile marker is not recognized.")
        else:
            require(not any(path.iterdir()), "NON_DEDICATED_PROFILE",
                    "Refusing to reuse an unmarked nonempty directory or a personal browser profile.")
    path.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        with marker.open("x", encoding="utf-8", newline="") as handle:
            handle.write(PROFILE_SIGNATURE)
    return path


@contextmanager
def profile_lock(path):
    # OS lock is released even after a crash. The harmless lock file can remain.
    with (path / ".forum-watch.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise WatchError("PROFILE_BUSY", "Dedicated profile is already in use; personal browsers will not be closed.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def allowed_topic_url(url):
    link = normalize_url(url)
    require(link.topic_id == 275, "UNAUTHORIZED_TOPIC", "The manual reader is authorized only for topic 275.")
    return link


def permit_read_request(url, method, resource_type, *, main_frame=True):
    """No GET-by-itself authorization; only topic documents and same-host styling."""
    if method != "GET":
        return False
    if resource_type == "document":
        if not main_frame:
            return False
        try:
            allowed_topic_url(url)
            return True
        except WatchError:
            return False
    try:
        parts = urlsplit(url)
        return (resource_type in {"stylesheet", "font"} and parts.scheme == "https"
                and parts.hostname == "narutorol.jcink.net" and parts.port in (None, 443)
                and parts.username is None and parts.password is None
                and not parts.query and not parts.fragment
                and Path(parts.path).suffix.lower() in {".css", ".woff", ".woff2", ".ttf", ".otf"})
    except ValueError:
        return False


@contextmanager
def reader_page(profile):
    """Fixed-scope read context; page scripts, images, frames and downloads are disabled."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise WatchError("READER_DEPENDENCY_MISSING", "Use the dedicated reader virtual environment.") from exc
    path = prepare_profile(profile)
    with profile_lock(path):
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(path), channel="msedge", headless=True, accept_downloads=False,
                    service_workers="block", java_script_enabled=False,
                    chromium_sandbox=True, timeout=30000)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    blocked_documents = []
                    def guard(route):
                        request = route.request
                        permitted = permit_read_request(request.url, request.method, request.resource_type,
                                                        main_frame=request.frame == page.main_frame)
                        if permitted:
                            route.continue_()
                        else:
                            if request.resource_type == "document":
                                blocked_documents.append("UNAUTHORIZED_NAVIGATION")
                            route.abort()
                    context.route("**/*", guard)
                    yield page, blocked_documents
                finally:
                    if context.browser.is_connected():
                        context.close()
        except WatchError:
            raise
        except Error as exc:
            raise WatchError("BROWSER_READ_FAILED", "Dedicated browser read failed; no partial capture is accepted.") from exc


def manual_login(profile, *, timeout_seconds=600):
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 1800,
            "INVALID_TIMEOUT", "Manual login timeout must be between 1 and 1800 seconds.")
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError as exc:
        raise WatchError("READER_DEPENDENCY_MISSING", "Install requirements-reader.txt in the dedicated virtual environment.") from exc
    path = prepare_profile(profile)
    with profile_lock(path):
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(path), channel="msedge", headless=False, accept_downloads=False,
                    service_workers="block", chromium_sandbox=True, timeout=30000)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    def initial_navigation_guard(route):
                        if route.request.is_navigation_request():
                            try:
                                allowed_topic_url(route.request.url)
                            except WatchError:
                                route.abort()
                                return
                        route.continue_()
                    context.route("**/*", initial_navigation_guard)
                    # Only initial navigation is automatic. The human uses the real login UI.
                    # During login: no DOM reads, screenshots, traces, video, HAR, headers,
                    # storage/cookie exports, request logs or automated form interactions.
                    page.goto(INITIAL_URL, wait_until="domcontentloaded", timeout=30000)
                    allowed_topic_url(page.url)
                    context.unroute("**/*", initial_navigation_guard)
                    print("LOGIN_MANUAL: inicia sesion en la ventana dedicada de Edge. "
                          "No introduzcas credenciales en la terminal. Cierra esa ventana "
                          "cuando termines; el lector verificara la identidad por separado.",
                          flush=True, file=sys.stderr)
                    try:
                        page.wait_for_event("close", timeout=timeout_seconds * 1000)
                    except TimeoutError as exc:
                        raise WatchError("LOGIN_TIMEOUT", "Manual login window timed out; no extraction or import was attempted.") from exc
                finally:
                    if context.browser.is_connected():
                        context.close()
        except WatchError:
            raise
        except Error as exc:
            # Browser logs can contain session URLs. Never print the raw exception after login.
            raise WatchError("BROWSER_START_OR_LOGIN_FAILED",
                             "Dedicated Edge could not complete startup/login. No identity or reading was verified.") from exc
    return {"result": "LOGIN_WINDOW_CLOSED", "session_identity_status": "NOT_VERIFIED",
            "messages_extracted": 0, "captures_imported": 0}
