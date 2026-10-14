"""Memory: source events, provenance, IC/OOC knowledge and narrative topics (7a).

The narrative model is exported lazily: `core.memory.narrative` imports
`core.character.models`, which imports `core.memory.provenance` and so this package; an eager
import here would leave `core.character.models` half initialised when it is imported first.
"""

from core.memory.provenance import SourceRef

_NARRATIVE = frozenset({
    "CharacterSheetRef",
    "DraftPublication",
    "ExternalPost",
    "HumanSeed",
    "LoadedNarrativeTopic",
    "NarrativeDraftRecord",
    "NarrativeDraftView",
    "NarrativeError",
    "NarrativePostView",
    "NarrativePublication",
    "PostAuthor",
    "PostRef",
    "SeedMode",
    "TopicHeader",
    "TopicReplay",
    "TopicState",
    "context_sha256",
    "decode_topic_state",
    "draft_semantics",
    "encode_topic_content",
    "narrative_draft_summary",
    "post_summary",
    "publication_summary",
    "seed_semantics",
    "seed_summary",
    "topic_summary",
})

__all__ = [
    "CharacterSheetRef",
    "DraftPublication",
    "ExternalPost",
    "HumanSeed",
    "LoadedNarrativeTopic",
    "NarrativeDraftRecord",
    "NarrativeDraftView",
    "NarrativeError",
    "NarrativePostView",
    "NarrativePublication",
    "PostAuthor",
    "PostRef",
    "SeedMode",
    "SourceRef",
    "TopicHeader",
    "TopicReplay",
    "TopicState",
    "context_sha256",
    "decode_topic_state",
    "draft_semantics",
    "encode_topic_content",
    "narrative_draft_summary",
    "post_summary",
    "publication_summary",
    "seed_semantics",
    "seed_summary",
    "topic_summary",
]


def __getattr__(name: str):
    if name in _NARRATIVE:
        from core.memory import narrative

        return getattr(narrative, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
