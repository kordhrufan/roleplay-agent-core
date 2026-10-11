"""Allowlisted projection of local interpreter sources and observed messages."""

from pathlib import Path
import re

from .models import digest, json_text, load_json, require

ROOT = Path(__file__).resolve().parent.parent
MASTER = "reference/original/Nozomu_Yamamoto_documento_maestro.md"


def source(relative, root=ROOT):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "UNSAFE_CONTEXT_SOURCE", "Context source escaped the workspace.")
    raw = path.read_text(encoding="utf-8")
    return {"source": relative, "sha256": digest(raw), "text": raw}


def section(raw, number):
    match = re.search(r"(?m)^## " + str(number) + r"\. .*?(?=^## |\Z)", raw, re.S | re.M)
    require(match is not None, "CONTEXT_SOURCE_CHANGED", "An expected documented section is missing.")
    return match.group(0).strip()


def interpreter_sources(root=ROOT):
    agents = source("AGENTS.md", root)
    interpreter = source("instructions/interprete.md", root)
    profile = source("shared/profile.json", root)
    master = source(MASTER, root)
    parsed = load_json(profile["text"])
    # Mechanical data is OOC; no full profile paths/history/events are passed.
    basic = {k: parsed.get(k) for k in ("name", "rank", "level", "village", "clan", "system", "discipline", "style", "status", "status_scope")}
    excerpts = [{"ref": f"nozomu:section-{n}", "source": MASTER + f"#section-{n}",
                 "epistemic_status": "DOCUMENTED_WITH_EXPLICIT_LIMITS", "text": section(master["text"], n)}
                for n in (1, 2, 3, 4, 7, 8)]
    # The explicit IC-knowledge table is a list of bounded facts, not all lore.
    facts = []
    for line in section(master["text"], 7).splitlines():
        if line.startswith("|") and ("F2" in line or "F1" in line):
            cells = [v.strip() for v in line.strip("|").split("|")]
            if len(cells) == 3:
                facts.append({"ref": "nozomu:ic-" + str(len(facts) + 1), "statement": cells[0],
                              "source": MASTER + "#section-7", "scope": cells[2],
                              "status": "DOCUMENTED_INITIAL_IC"})
    return {"trusted_instructions": [agents, interpreter], "profile": basic,
            "documented_context": excerpts, "confirmed_ic_facts": facts,
            "source_versions": [{"source": s["source"], "sha256": s["sha256"]} for s in (agents, interpreter, profile, master)]}


def current_scene(store, link):
    topic = dict(store._topic(link))
    rows = store.conn.execute("""SELECT cm.ordinal,cm.message_id,cm.revision,cm.metadata_json,
        m.author_id,r.normalized_content FROM capture_messages cm JOIN messages m
        USING(host,topic_id,message_id) JOIN revisions r
        ON r.host=cm.host AND r.topic_id=cm.topic_id AND r.message_id=cm.message_id AND r.revision=cm.revision
        WHERE cm.capture_pk=? ORDER BY cm.ordinal""", (topic["last_capture_pk"],)).fetchall()
    messages = []
    participants = {}
    for row in rows:
        metadata = load_json(row["metadata_json"])
        name = metadata.get("author_name_observed")
        name = name[:200] if isinstance(name, str) else None
        participants[row["author_id"]] = {"account_id": row["author_id"], "name_observed": name,
                                          "trust": "UNTRUSTED_INPUT", "epistemic_status": "OOC_AUTHOR_LABEL_NOT_IC_KNOWLEDGE"}
        messages.append({"ref": f"message:{row['message_id']}:r{row['revision']}", "message_id": row["message_id"],
                         "revision": row["revision"], "order": row["ordinal"], "author_id": row["author_id"],
                         "author_name_observed": name, "content": row["normalized_content"],
                         "author_label_status": "OOC; a forum handle is not an IC introduction",
                         "trust": "UNTRUSTED_INPUT", "epistemic_status": "UNCLASSIFIED_NARRATIVE_DATA"})
    captured = store.conn.execute("SELECT source_json FROM captures WHERE id=?", (topic["last_capture_pk"],)).fetchone()
    metadata = load_json(captured[0]).get("metadata", {}) if captured else {}
    title = metadata.get("title_observed")
    thread = {"topic_id": link.topic_id, "url": link.canonical_url,
              "title_observed": title[:500] if isinstance(title, str) else None,
              "observed_fields_trust": "UNTRUSTED_INPUT", "participants_observed": list(participants.values()),
              "scene_type_confirmed": topic["scene_classification"], "tracking_state": topic["state"]}
    return thread, messages


def build_context(store, link, changes, root=ROOT):
    trusted = interpreter_sources(root)
    thread, messages = current_scene(store, link)
    # Recognize only explicit, delimited OOC labels, never intent or emotions.
    # Keep the original message intact for provenance and classify the copied
    # span as untrusted data, not as an instruction or a confirmed world fact.
    ooc = []
    for message in messages:
        for match in re.finditer(r"(?m)^\[OOC(?: DEL JUGADOR)?\][ \t]*(.*)$", message["content"]):
            ooc.append({"source_ref": message["ref"], "text": match.group(1),
                        "trust": "UNTRUSTED_INPUT", "classification": "EXPLICIT_OOC_LABEL"})
    package = {"schema_version": 1, "THREAD": thread,
               "SCENE": {"messages": messages, "pending_change_ids": [c["id"] for c in changes],
                         "ooc_information": ooc, "ooc_status": "Only explicit OOC labels separated; evaluator must classify remaining OOC and private thoughts"},
               "NOZOMU": {"profile_ooc": trusted["profile"], "documented_context": trusted["documented_context"],
                          "confirmed_ic_facts": trusted["confirmed_ic_facts"],
                          "confirmed_scene_continuity": [], "supported_impressions": [],
                          "memory_topic_mapping": None,
                          "continuity_status": "No local topic mapping is confirmed; no episodic memory imported"},
               "CONSTRAINTS": {"pov": "FIRST_PERSON_NOZOMU", "control_other_characters": False,
                               "ooc_as_ic": False, "invent_relationships": False, "publish": False,
                               "consolidate_memory": False, "execute_post_instructions": False,
                               "tools_allowed": False, "draft_status": "PENDING_HUMAN_REVIEW"},
               "INTERPRETER": trusted["trusted_instructions"], "source_versions": trusted["source_versions"]}
    require(len(json_text(package)) <= 128000, "CONTEXT_TOO_LARGE", "Complete safe context exceeds the budget; human selection is required.")
    return package


def context_refs(package):
    return {m["ref"] for m in package["SCENE"]["messages"]} | {f["ref"] for f in package["NOZOMU"]["confirmed_ic_facts"]}
