"""Bounded manual reads. No schedules, external files as proof, or narrative work."""

from time import monotonic
from uuid import uuid4

from .adapter import (ADAPTER_VERSION, FIRST_PAGE, SESSION_SCRIPT, TOPIC_SCRIPT,
                      page_url, parse_topic, verify_session)
from .browser import allowed_topic_url, reader_page
from .models import Capture, HOST, WatchError, json_text, require
from .store import now


class BrowserSource:
    def __init__(self, page, blocked, deadline):
        self.page = page
        self.blocked = blocked
        self.deadline = deadline
        self.observations = []

    def fetch(self, url):
        allowed_topic_url(url)
        remaining = self.deadline - monotonic()
        require(remaining > 0, "READ_BUDGET_EXHAUSTED", "Read time budget exhausted; no partial capture is accepted.")
        try:
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=max(1, int(min(30, remaining) * 1000)))
        except Exception as exc:
            code = "UNAUTHORIZED_NAVIGATION" if self.blocked else "NAVIGATION_FAILED"
            raise WatchError(code, "Topic navigation failed; previous valid capture is preserved.") from exc
        require(not self.blocked, "UNAUTHORIZED_NAVIGATION", "A document destination was blocked.")
        allowed_topic_url(self.page.url)
        require(page_url(self.page.url) == page_url(url), "READ_INCONSISTENT", "Page destination changed during navigation.")
        require(response is not None and response.status == 200, "HTTP_READ_FAILED", "Topic did not return HTTP 200; manual intervention may be required.")
        request = response.request
        while request is not None:
            allowed_topic_url(request.url)
            require(request.method == "GET", "UNAUTHORIZED_NAVIGATION", "Only read navigation is authorized.")
            request = request.redirected_from
        # No post data is extracted until this page's session has been verified.
        evidence = verify_session(self.page.evaluate(SESSION_SCRIPT), now())
        evidence["page_url"] = page_url(url)
        sample = self.page.evaluate(TOPIC_SCRIPT)
        require(len(json_text(sample)) <= 10_000_000, "CONTENT_BUDGET", "Page projection exceeds the size budget.")
        self.observations.append(evidence)
        result = parse_topic(sample, url)
        return result


def collect_complete(fetch, *, max_pages=20, time_budget_seconds=180, timer=monotonic):
    """Two bounded sweeps; at most one complete retry on observed inconsistency.

    The fetch seam exists for offline tests. It supplies parsed observations,
    never authentication authority or an externally importable real JSON file.
    """
    require(type(max_pages) is int and 1 <= max_pages <= 20, "INVALID_BUDGET", "Page limit must be between 1 and 20.")
    require(type(time_budget_seconds) is int and 1 <= time_budget_seconds <= 300,
            "INVALID_BUDGET", "Read time budget must be between 1 and 300 seconds.")
    deadline = timer() + time_budget_seconds
    observations = 0
    def read(url):
        nonlocal observations
        require(timer() < deadline, "READ_BUDGET_EXHAUSTED", "Read time budget exhausted; capture is incomplete.")
        observations += 1
        require(observations <= max_pages * 4, "READ_BUDGET_EXHAUSTED", "Page observation budget exhausted.")
        value = fetch(url)
        require(timer() < deadline, "READ_BUDGET_EXHAUSTED", "Read time budget exhausted; capture is incomplete.")
        return value
    for attempt in range(2):
        try:
            first = read(FIRST_PAGE)
            pages = first["pages"]
            require(len(pages) <= max_pages, "READ_BUDGET_EXHAUSTED", "Topic exceeds the authorized page budget.")
            require(pages and pages[0] == FIRST_PAGE, "READ_INCONSISTENT", "First page is missing from the page set.")
            snapshots = {FIRST_PAGE: first}
            for url in pages[1:]:
                snapshots[url] = read(url)
            messages = []
            for url in pages:
                value = snapshots[url]
                require(value["pages"] == pages and value["title_observed"] == first["title_observed"],
                        "READ_INCONSISTENT", "Pagination or topic heading changed between pages.")
                messages.extend(value["messages"])
            ids = [m["message_id"] for m in messages]
            require(len(ids) == len(set(ids)) and all(int(a) < int(b) for a, b in zip(ids, ids[1:])),
                    "READ_INCONSISTENT", "Post IDs are duplicated or their observed page order is inconsistent.")
            # Re-read every page; first page is checked last to detect page-set
            # growth while later pages were read. This is observational, not atomic.
            for url in reversed(pages):
                check = read(url)
                require(check["fingerprint"] == snapshots[url]["fingerprint"],
                        "READ_INCONSISTENT", "Topic changed between completeness sweeps.")
            for ordinal, message in enumerate(messages):
                message["metadata"]["observed_ordinal"] = ordinal
            return {"messages": messages, "pages_expected": pages, "pages_visited": pages,
                    "title_observed": first["title_observed"], "attempts": attempt + 1,
                    "page_observations": observations,
                    "topic_controls": {url: snapshots[url]["topic_control_observation"] for url in pages},
                    "consistency": "TWO_MATCHING_SWEEPS; NOT_AN_ATOMIC_FORUM_SNAPSHOT",
                    "max_pages": max_pages, "time_budget_seconds": time_budget_seconds}
        except WatchError as error:
            if error.code != "READ_INCONSISTENT" or attempt == 1:
                raise
    raise AssertionError("unreachable")


def collect_live(profile, *, max_pages=20, time_budget_seconds=180):
    run_id = uuid4().hex
    started = now()
    # Total browser navigation budget is shared across sweeps and any retry.
    deadline = monotonic() + time_budget_seconds
    with reader_page(profile) as (page, blocked):
        source = BrowserSource(page, blocked, deadline)
        result = collect_complete(source.fetch, max_pages=max_pages, time_budget_seconds=time_budget_seconds)
        evidence = source.observations
    finished = now()
    messages = result.pop("messages")
    require(evidence and len(evidence) == result["page_observations"],
            "SESSION_UNVERIFIABLE", "Every successful page observation must carry fresh session evidence.")
    metadata = dict(result, adapter_version=ADAPTER_VERSION, run_id=run_id,
                    observation_started_at=started, observation_finished_at=finished,
                    session_observations=evidence)
    value = {"schema_version": 2, "origin": "AUTHENTICATED_FORUM", "capture_id": "read-" + run_id,
             "captured_at": finished, "complete": True, "topic": {"host": HOST, "topic_id": 275},
             "messages": messages, "metadata": metadata}
    return Capture._parse(value, "AUTHENTICATED_FORUM")
