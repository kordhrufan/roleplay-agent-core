"""Versioned adapter for the topic-275 DOM observed on 2026-09-13.

Inputs are minimal DOM projections, never a full authenticated page. Offline
fixtures describe this projection; they are not evidence of a live session.
"""

from urllib.parse import parse_qsl, urljoin, urlsplit
import re

from .browser import allowed_topic_url
from .models import HOST, digest, json_text, normalize_content, positive_int, require


ADAPTER_VERSION = "jcink-topic275-observed-20260913-v1"
BASE = f"https://{HOST}/index.php"
FIRST_PAGE = BASE + "?showtopic=275&st=0"
SESSION_SELECTOR = "#wrapper > .header > #userlinks"

# Only the scoped session signal crosses the browser boundary. Other session
# controls, their URLs, PM counters, forms, and logout tokens are never returned.
SESSION_SCRIPT = r"""() => {
  const panels = document.querySelectorAll('#wrapper > .header > #userlinks');
  if (panels.length !== 1) return {panel_count:panels.length};
  const p = panels[0];
  return {panel_count:1,
    label:p.textContent.includes('Logged in as:') ? 'Logged in as:' : null,
    profiles:Array.from(p.querySelectorAll('strong > a[href]')).map(a => a.getAttribute('href')),
    logout_count:Array.from(p.querySelectorAll('a')).filter(a => a.textContent.trim()==='Log Out').length};
}"""

# All selectors below come from the observed topic. No navigation uses a post
# link. Buttons in the pagination cells are excluded before reading their URLs.
TOPIC_SCRIPT = r"""() => {
  const roots = Array.from(document.querySelectorAll('#innerwrapper > .tableborder'))
    .filter(e => e.querySelector(':scope > .maintitle > .topic-title'));
  if (roots.length !== 1) return {topic_count:roots.length};
  const root = roots[0];
  let budget = 0;
  function tree(n) {
    if (++budget > 100000) throw new Error('DOM budget');
    if (n.nodeType===3) return n.textContent;
    if (n.nodeType!==1) return '';
    const attrs={};
    if (n.tagName==='A' && n.hasAttribute('href')) attrs.href=n.getAttribute('href');
    if (n.tagName==='BLOCKQUOTE' && n.hasAttribute('cite')) attrs.cite=n.getAttribute('cite');
    return {tag:n.tagName.toLowerCase(), attrs, children:Array.from(n.childNodes).map(tree)};
  }
  const nav=Array.from(document.querySelectorAll('#innerwrapper > table > tbody > tr > td:first-child'))
    .map(cell => {
      const clone=cell.cloneNode(true);
      clone.querySelectorAll('.button-large').forEach(button => {
        const a=button.closest('a'); (a || button).remove();
      });
      return Array.from(clone.childNodes).map(tree);
    });
  const posts=Array.from(root.querySelectorAll(':scope > .postarea')).map(post => {
    const authors=post.querySelectorAll(':scope > .posttop > .posttopinner > .posttopleft > .postname > a[href]');
    const containers=post.querySelectorAll(':scope > .postmid > .postmidleft > .postmidleft2 > div[id^="pid_"]');
    const dates=post.querySelectorAll(':scope > .postmid > .postmidleft > .postmidleft1 > .postmidleft1a');
    const bodies=containers.length===1 ? containers[0].querySelectorAll(':scope > .postcolor') : [];
    const entries=dates.length===1 ? Array.from(dates[0].querySelectorAll('a[name]')).map(a => a.getAttribute('name')) : [];
    return {author_count:authors.length, container_count:containers.length, body_count:bodies.length,
      author_url:authors.length===1 ? authors[0].getAttribute('href') : null,
      author_name:authors.length===1 ? authors[0].textContent : null,
      pid:containers.length===1 ? containers[0].id : null,
      date_count:dates.length, date_visible:dates.length===1 ? dates[0].textContent : null,
      entries, body:bodies.length===1 ? Array.from(bodies[0].childNodes).map(tree) : null,
      edit_indicator:null};
  });
  return {topic_count:1, title:root.querySelector(':scope > .maintitle > .topic-title').textContent,
    nav, posts, open_control_count:document.querySelectorAll('#innerwrapper > #topic_open').length};
}"""


def account_id(href):
    require(isinstance(href, str) and not any(c.isspace() for c in href),
            "UNVERIFIABLE_ACCOUNT", "Account link is absent or malformed.")
    try:
        url = urlsplit(urljoin(BASE, href))
        pairs = parse_qsl(url.query, strict_parsing=True)
        valid = (url.scheme == "https" and url.hostname == HOST and url.port in (None, 443)
                 and url.username is None and url.password is None and url.path == "/index.php"
                 and not url.fragment and len(pairs) == 1 and pairs[0][0] == "showuser"
                 and re.fullmatch(r"[0-9]{1,19}", pairs[0][1]))
    except ValueError:
        valid = False
    require(valid, "UNVERIFIABLE_ACCOUNT", "Expected a scoped same-host account link.")
    return positive_int(int(pairs[0][1]), "account_id")


def verify_session(sample, checked_at):
    require(sample.get("panel_count") == 1 and sample.get("label") == "Logged in as:"
            and sample.get("logout_count") == 1 and len(sample.get("profiles", [])) == 1,
            "SESSION_UNVERIFIABLE", "Session expired, guest, access challenge or unrecognized session area; manual intervention required.")
    observed = account_id(sample["profiles"][0])
    require(observed == 59, "WRONG_ACCOUNT", "The connected account is not the authorized account 59.")
    return {"expected_account_id": 59, "observed_account_id": observed, "checked_at": checked_at,
            "method": SESSION_SELECTOR + "; Logged in as:; strong > a[showuser]; Log Out label",
            "status": "VERIFIED_FOR_THIS_OBSERVATION"}


def page_url(value):
    absolute = urljoin(BASE, value)
    allowed_topic_url(absolute)
    pairs = dict(parse_qsl(urlsplit(absolute).query))
    offset = int(pairs.get("st", "0"))
    return BASE + f"?showtopic=275&st={offset}"


BLOCKS = {"div", "p", "pre", "ul", "ol", "li", "table", "tr", "dl", "dt", "dd",
          "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "center"}
INLINE = {"span", "b", "strong", "i", "em", "u", "s", "strike", "small", "big", "font",
          "code", "sup", "sub", "mark", "td", "th", "tbody", "thead", "tfoot", "label"}


def body_text(nodes, depth=0):
    require(depth < 80 and isinstance(nodes, list), "UNEXTRACTABLE_CONTENT", "Post markup exceeds the supported structure.")
    result = []
    for node in nodes:
        if isinstance(node, str):
            result.append(node)
            continue
        tag = node.get("tag")
        require(tag in BLOCKS | INLINE | {"a", "br", "hr", "blockquote", "details", "summary"},
                "UNEXTRACTABLE_CONTENT", "Post contains media, active or unsupported markup; no complete capture was imported.")
        text = body_text(node.get("children", []), depth + 1)
        attrs = node.get("attrs", {})
        if tag in BLOCKS:
            text = "\n" + text + "\n"
        elif tag in {"br", "hr"}:
            text = "\n"
        elif tag in {"blockquote", "details", "summary"}:
            cite = " " + attrs["cite"] if tag == "blockquote" and attrs.get("cite") else ""
            text = f"\n[{tag}{cite}]\n{text}\n[/{tag}]\n"
        elif tag == "a" and attrs.get("href"):
            # Inert representation, never followed or executed (even javascript:).
            text += " <" + attrs["href"] + ">"
        result.append(text)
    return normalize_content("".join(result))


def pagination(cells, current_url):
    require(isinstance(cells, list) and len(cells) == 2, "UNKNOWN_PAGINATION", "Expected the observed top and bottom navigation cells.")
    all_links = set()
    signatures = []
    for cell in cells:
        links = set()
        labels = []
        def visit(nodes):
            for node in nodes:
                if isinstance(node, str):
                    stripped = node.strip()
                    if stripped:
                        require(re.fullmatch(r"[0-9]+", stripped) is not None,
                                "UNKNOWN_PAGINATION", "Unrecognized or truncated pager; completeness cannot be established.")
                        labels.append(int(stripped))
                    continue
                if node.get("tag") == "a":
                    label = body_text(node.get("children", [])).strip()
                    require(label.isascii() and label.isdecimal() and int(label) > 0,
                            "UNKNOWN_PAGINATION", "Only explicit numbered page links are supported.")
                    links.add(page_url(node.get("attrs", {}).get("href", "")))
                    labels.append(int(label))
                else:
                    require(node.get("tag") in {"span", "b", "strong", "div", "br"},
                            "UNKNOWN_PAGINATION", "Unexpected pager markup.")
                    visit(node.get("children", []))
        visit(cell)
        require(not labels or (len(labels) == len(set(labels)) and sorted(labels) == list(range(1, max(labels) + 1))),
                "UNKNOWN_PAGINATION", "Pagination must expose every numbered page without gaps.")
        # On the observed one-page topic both stripped cells are empty.
        pages = links | {page_url(current_url)}
        require(not labels or len(pages) == len(labels), "UNKNOWN_PAGINATION", "Page numbers and explicit destinations disagree.")
        signatures.append(pages)
        all_links.update(pages)
    require(signatures[0] == signatures[1], "READ_INCONSISTENT", "Top and bottom pagination disagree.")
    require(FIRST_PAGE in all_links, "READ_INCONSISTENT", "The complete page set must include the first page.")
    return sorted(all_links, key=lambda url: int(dict(parse_qsl(urlsplit(url).query))["st"]))


def parse_topic(sample, url):
    require(sample.get("topic_count") == 1, "UNEXPECTED_TOPIC_PAGE", "Expected topic structure was replaced by a login, error or unknown page.")
    pages = pagination(sample.get("nav"), url)
    require(isinstance(sample.get("title"), str) and sample["title"].strip(), "UNEXPECTED_TOPIC_PAGE", "Topic title is unavailable.")
    require(isinstance(sample.get("posts"), list) and 0 < len(sample["posts"]) <= 1000,
            "INCOMPLETE_CAPTURE", "Expected a bounded nonempty list of posts.")
    messages = []
    for post in sample["posts"]:
        require(post.get("container_count") == 1 and post.get("body_count") == 1
                and re.fullmatch(r"pid_[1-9][0-9]{0,18}", post.get("pid") or ""),
                "UNIDENTIFIED_POST", "A post or its content could not be identified uniquely.")
        message_id = post["pid"][4:]
        require(post.get("entries") == ["entry" + message_id], "UNIDENTIFIED_POST", "Post ID and metadata permalink anchor disagree.")
        require(post.get("author_count") == 1, "UNIDENTIFIED_AUTHOR", "Post author cannot be identified uniquely.")
        author_id = account_id(post.get("author_url"))
        require(post.get("date_count") == 1, "UNIDENTIFIED_DATE", "Post date container cannot be identified uniquely.")
        visible_date = " ".join((post.get("date_visible") or "").split())
        require(bool(visible_date.strip(" -")), "UNIDENTIFIED_DATE", "Post date text is absent; no date is inferred.")
        content = body_text(post.get("body"))
        require(len(content) <= 2_000_000, "CONTENT_BUDGET", "Post content exceeds the size budget.")
        messages.append({"message_id": message_id, "author_id": author_id, "content": content,
                         "metadata": {"author_name_observed": post.get("author_name"),
                                      "date_visible": visible_date, "date_iso": None,
                                      "edit_indicator": post.get("edit_indicator"),
                                      "edit_detection": "CONTENT_HASH; DOM edit marker not verified",
                                      "message_url": page_url(url) + "#entry" + message_id,
                                      "page_url": page_url(url)}})
    ids = [m["message_id"] for m in messages]
    require(len(ids) == len(set(ids)), "READ_INCONSISTENT", "Duplicate post IDs within a page.")
    result = {"pages": pages, "title_observed": sample["title"], "messages": messages,
              "topic_control_observation": "OPEN_CONTROL_PRESENT" if sample.get("open_control_count") == 1 else "UNKNOWN"}
    result["fingerprint"] = digest(json_text(result))
    return result
