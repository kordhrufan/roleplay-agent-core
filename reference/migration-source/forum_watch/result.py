"""Validate the committed schema and epistemic references; never salvage output."""

from pathlib import Path

from .models import load_json, require

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas/narrative-result.json"


def validate_schema(value, schema):
    kind = schema["type"]
    kinds = kind if isinstance(kind, list) else [kind]
    actual = {str: "string", dict: "object", list: "array", type(None): "null"}.get(type(value))
    require(actual in kinds, "INVALID_MODEL_OUTPUT", "Model output does not match its JSON schema.")
    if "enum" in schema:
        require(value in schema["enum"], "INVALID_MODEL_OUTPUT", "Unsupported model output enum.")
    if actual == "object":
        require(set(schema["required"]) <= value.keys() and value.keys() <= schema["properties"].keys(),
                "INVALID_MODEL_OUTPUT", "Missing or additional model output fields.")
        for key, item in value.items():
            validate_schema(item, schema["properties"][key])
    elif actual == "array":
        require(len(value) <= schema.get("maxItems", 1000), "INVALID_MODEL_OUTPUT", "Model array exceeds schema budget.")
        for item in value:
            validate_schema(item, schema["items"])
    elif actual == "string":
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 20000),
                "INVALID_MODEL_OUTPUT", "Model text exceeds schema bounds.")


def validate_result(raw, package):
    value = load_json(raw) if isinstance(raw, str) else raw
    validate_schema(value, load_json(SCHEMA_PATH.read_text(encoding="utf-8")))
    message_refs = {m["ref"] for m in package["SCENE"]["messages"]}
    initial = {f["ref"] for f in package["NOZOMU"]["confirmed_ic_facts"]}
    assessments = {}
    for item in value["scene_assessment"]:
        ref = "assessment:" + item["ref"]
        require(ref not in assessments and item["source_ref"] in message_refs,
                "INVALID_MODEL_OUTPUT", "Assessment source is missing or repeated.")
        assessments[ref] = item
    usable_ic = initial | {ref for ref, item in assessments.items() if item["kind"] == "OBSERVABLE_IC"}
    require(set(value["ic_facts_used"]) <= usable_ic, "INVALID_MODEL_OUTPUT",
            "IC references must be confirmed initial facts or explicitly observable IC assessments.")
    for candidate in value["memory_candidates"]:
        require(candidate["source_refs"] and set(candidate["source_refs"]) <= initial | assessments.keys(),
                "INVALID_MODEL_OUTPUT", "Memory proposals require valid source references.")
        if candidate["category"] == "FACT":
            require(set(candidate["source_refs"]) <= usable_ic, "INVALID_MODEL_OUTPUT",
                    "OOC, private thoughts, proposals and unconfirmed outcomes cannot become FACT candidates.")
    if value["decision"] == "DRAFT_READY":
        require(isinstance(value["draft"], str) and bool(value["draft"].strip()),
                "INVALID_MODEL_OUTPUT", "DRAFT_READY requires a complete nonempty draft.")
        require(not value["important_decisions"] and not any(i["kind"] in {"COMBAT", "UNCERTAIN"} for i in assessments.values()),
                "INVALID_MODEL_OUTPUT", "Important decisions, combat or material uncertainty require review, not a social draft.")
    else:
        require(value["draft"] is None, "INVALID_MODEL_OUTPUT", "Only DRAFT_READY may carry a draft.")
    if any(i["kind"] == "COMBAT" for i in assessments.values()):
        require(value["decision"] == "COMBAT_REVIEW_REQUIRED", "INVALID_MODEL_OUTPUT", "Observed mechanics require the existing combat specialist.")
    return value
