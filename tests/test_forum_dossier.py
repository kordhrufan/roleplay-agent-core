import dataclasses
import hashlib
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from core.memory.provenance import SourceRef
from core.runtime.assimilation import (
    DOSSIER_NAME,
    OPTIONAL_SECTIONS,
    REQUIRED_SECTIONS,
    DossierAssessment,
    DossierError,
    DossierSection,
    DossierSectionSpec,
    DossierSectionStatus,
    DossierSourceSpec,
    ForumDossier,
    LoadedDossierSource,
    LooseMaterialSpec,
    assess_dossier,
    load_dossier,
    parse_dossier,
)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "core" / "runtime" / "templates"
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"

HEADER = (
    "# Expediente del foro\n"
    "forum_id: foro-prueba\n"
    "nombre: Foro de prueba\n"
    "versión_expediente: 1\n"
)
HEADINGS = (
    "Normas generales",
    "Ambientación",
    "Creación de fichas",
    "Revisión del staff",
    "Plataforma y formato",
    "Sistema de combate",
    "Creación de técnicas o habilidades",
    "Material suelto",
)
META = 'Metadatos: id="{id}" | versión="1" | autoridad="Staff" | alcance="foro"'


def inline(source_id: str, text: str = "Texto de la fuente.\n", extra: str = "",
           fence: str = "~~~~") -> str:
    return f"### Fuente\n{META.format(id=source_id)}{extra}\n{fence} texto\n{text}{fence}\n"


def document(overrides: dict[str, str] | None = None, header: str = HEADER) -> str:
    """A valid dossier: required sections with one inline source, optional ones not applicable."""
    bodies = {heading: inline(f"fuente-{i}") for i, heading in enumerate(HEADINGS[:5])}
    bodies["Sistema de combate"] = "Estado: NO APLICA\n"
    bodies["Creación de técnicas o habilidades"] = "Estado: NO APLICA\n"
    bodies["Material suelto"] = ""
    bodies.update(overrides or {})
    parts = [header]
    for heading in HEADINGS:
        parts.append(f"\n## {heading}\n{bodies[heading]}")
    return "".join(parts)


def line_of(text: str, needle: str, occurrence: int = 0) -> int:
    """1-based line number of the `occurrence`-th line equal to `needle` (-1 = last)."""
    numbers = [i + 1 for i, line in enumerate(text.split("\n")) if line == needle]
    return numbers[occurrence]


def section(dossier: ForumDossier, which: DossierSection) -> DossierSectionSpec:
    return next(s for s in dossier.sections if s.section is which)


class TempDossier:
    def __init__(self, test: unittest.TestCase, text: str | bytes | None = None):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir = self.root / "expediente"
        self.dir.mkdir()
        if text is not None:
            self.write(text)

    def write(self, text: str | bytes) -> None:
        raw = text.encode("utf-8") if isinstance(text, str) else text
        (self.dir / DOSSIER_NAME).write_bytes(raw)

    def material(self, relative: str, raw: bytes) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path


def file_source(source_id: str, path: str, passage: str | None = None) -> str:
    extra = f' | archivo="{path}"' + (f' | pasaje="{passage}"' if passage else "")
    return f"### Fuente\n{META.format(id=source_id)}{extra}\n"


class ModelTest(unittest.TestCase):
    def spec(self, **overrides) -> DossierSourceSpec:
        fields = dict(source_id="s", version="1", authority="Staff", scope="foro",
                      effective_from=None, effective_until=None, section_or_passage=None,
                      path=None, inline_text="texto\n")
        fields.update(overrides)
        return DossierSourceSpec(**fields)

    def test_dataclasses_are_immutable_tuples(self):
        dossier = parse_dossier(document())
        self.assertIsInstance(dossier.sections, tuple)
        self.assertIsInstance(dossier.sections[0].sources, tuple)
        self.assertIsInstance(dossier.loose_material, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            dossier.forum_id = "otro"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            dossier.sections[0].sources[0].version = "2"

    def test_section_constants(self):
        self.assertEqual(REQUIRED_SECTIONS + OPTIONAL_SECTIONS, tuple(DossierSection))
        self.assertEqual(len(REQUIRED_SECTIONS), 5)

    def test_source_spec_requires_exactly_one_origin(self):
        self.spec()
        self.spec(path="a.md", inline_text=None)
        with self.assertRaises(DossierError):
            self.spec(path="a.md")
        with self.assertRaises(DossierError):
            self.spec(inline_text=None)

    def test_source_spec_rejects_non_canonical_or_empty_inline(self):
        for bad in ("a\r\n", "  \n", ""):
            with self.subTest(inline=bad):
                with self.assertRaises(DossierError):
                    self.spec(inline_text=bad)

    def test_source_spec_dates(self):
        self.spec(effective_from=date(2026, 1, 1), effective_until=date(2026, 1, 1))
        with self.assertRaises(DossierError):
            self.spec(effective_from=date(2026, 2, 1), effective_until=date(2026, 1, 1))
        with self.assertRaises(DossierError):
            self.spec(effective_from="2026-01-01")

    def test_section_spec_status_rules(self):
        src = self.spec()
        with self.assertRaises(DossierError):
            DossierSectionSpec(DossierSection.SETTING, DossierSectionStatus.NOT_APPLICABLE, None, ())
        DossierSectionSpec(DossierSection.COMBAT_SYSTEM, DossierSectionStatus.NOT_APPLICABLE, None, ())
        with self.assertRaises(DossierError):
            DossierSectionSpec(DossierSection.SETTING, DossierSectionStatus.PROVIDED, None, ())
        with self.assertRaises(DossierError):
            DossierSectionSpec(DossierSection.SETTING, DossierSectionStatus.MISSING, None, (src,))

    def test_forum_dossier_requires_fixed_section_order(self):
        dossier = parse_dossier(document())
        with self.assertRaises(DossierError):
            dataclasses.replace(dossier, sections=tuple(reversed(dossier.sections)))
        with self.assertRaises(DossierError):
            dataclasses.replace(dossier, sections=dossier.sections[:-1])

    def test_forum_dossier_rejects_incoherent_repeat(self):
        dossier = parse_dossier(document())
        first = dossier.sections[0].sources[0]
        clash = dataclasses.replace(first, authority="Otro")
        with self.assertRaises(DossierError):
            dataclasses.replace(dossier, loose_material=(LooseMaterialSpec(clash, ()),))

    def test_loose_material_rejects_duplicate_suggestions(self):
        with self.assertRaises(DossierError):
            LooseMaterialSpec(self.spec(), (DossierSection.SETTING, DossierSection.SETTING))

    def test_assessment_is_consistent(self):
        DossierAssessment((), (DossierSection.COMBAT_SYSTEM,), True)
        with self.assertRaises(DossierError):
            DossierAssessment((DossierSection.SETTING,), (), True)
        with self.assertRaises(DossierError):
            DossierAssessment((DossierSection.COMBAT_SYSTEM,), (), False)

    def test_loaded_source_must_match_its_literal(self):
        spec = self.spec()
        good = SourceRef("s", "loc", sha256=hashlib.sha256(b"texto\n").hexdigest())
        LoadedDossierSource(spec, "texto\n", good)
        with self.assertRaises(DossierError):
            LoadedDossierSource(spec, "otro\n", good)
        with self.assertRaises(DossierError):
            LoadedDossierSource(spec, "texto\n", SourceRef("s", "loc", sha256="0" * 64))


class TemplateAndFixtureTest(unittest.TestCase):
    def test_template_is_valid_but_not_ready(self):
        text = (TEMPLATES / "expediente.template.md").read_text(encoding="utf-8")
        dossier = parse_dossier(text)
        assessment = assess_dossier(dossier)
        self.assertEqual(assessment.missing_required, REQUIRED_SECTIONS)
        self.assertEqual(assessment.missing_optional, OPTIONAL_SECTIONS)
        self.assertFalse(assessment.ready_for_assimilation)
        self.assertEqual(dossier.loose_material, ())
        self.assertNotIn("<!--", text)

    def test_readme_example_is_valid(self):
        text = (TEMPLATES / "LEEME-expediente.md").read_text(encoding="utf-8")
        start = text.index("````markdown\n") + len("````markdown\n")
        end = text.index("\n````", start) + 1
        dossier = parse_dossier(text[start:end])
        self.assertEqual(assess_dossier(dossier).missing_required, (DossierSection.STAFF_REVIEW,))
        self.assertIn("~~~~\n", dossier.loose_material[0].source.inline_text)

    def test_fixture_loads_and_is_ready(self):
        loaded = load_dossier(FIXTURE)
        dossier = loaded.dossier
        self.assertEqual(dossier.forum_id, "foro-neutral")
        assessment = assess_dossier(dossier)
        self.assertTrue(assessment.ready_for_assimilation)
        self.assertEqual(assessment.missing_optional, ())
        for optional in OPTIONAL_SECTIONS:
            self.assertIs(section(dossier, optional).status, DossierSectionStatus.NOT_APPLICABLE)
        self.assertEqual(loaded.dossier_path, FIXTURE / DOSSIER_NAME)

    def test_fixture_inline_literal_preserves_markdown(self):
        loaded = load_dossier(FIXTURE)
        literal = loaded.sections[1].sources[0].literal_text
        for fragment in ("# Mundo base\n", "## Regiones\n", "- Llanura central\n",
                         "| Región | Clima |\n", "```\n", "\n~~~~\n"):
            self.assertIn(fragment, literal)
        self.assertTrue(literal.endswith("Fin del pasaje de ambientación.\n"))

    def test_fixture_repeat_and_loose_material(self):
        loaded = load_dossier(FIXTURE)
        rules = loaded.sections[0].sources[0]
        creation = loaded.sections[2].sources[0]
        self.assertEqual(rules.spec.key, creation.spec.key)
        self.assertNotEqual(rules.spec.section_or_passage, creation.spec.section_or_passage)
        self.assertEqual(rules.source_ref.sha256, creation.source_ref.sha256)
        loose = loaded.loose_material
        self.assertEqual(len(loose), 2)
        self.assertIsNotNone(loose[0].spec.source.path)
        self.assertEqual(loose[0].spec.suggested_sections,
                         (DossierSection.SETTING, DossierSection.CHARACTER_CREATION))
        self.assertIsNotNone(loose[1].spec.source.inline_text)
        self.assertEqual(loose[1].spec.suggested_sections, ())


class HeaderAndStructureTest(unittest.TestCase):
    def assert_error(self, text: str, line: int | None, fragment: str) -> DossierError:
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(text, locator="exp.md")
        error = ctx.exception
        self.assertEqual(error.locator, "exp.md")
        self.assertEqual(error.line, line)
        self.assertIn(fragment, error.reason)
        expected = f"exp.md:{line}: " if line is not None else "exp.md: "
        self.assertTrue(str(error).startswith(expected))
        return error

    def test_header(self):
        self.assert_error(document(header=HEADER.replace("# Expediente del foro", "# Expediente")),
                          1, "primera línea")
        self.assert_error(document(header=HEADER.replace("forum_id: foro-prueba", "forum_id: Foro")),
                          2, "forum_id")
        self.assert_error(document(header=HEADER.replace("nombre: Foro de prueba", "nombre:  Foro")),
                          3, "nombre")
        self.assert_error(document(header=HEADER.replace("versión_expediente: 1\n", "\nversión_expediente: 1\n")),
                          4, "versión_expediente")

    def test_not_text(self):
        with self.assertRaises(DossierError):
            parse_dossier(b"# Expediente del foro")

    def test_headings_order_uniqueness_and_spelling(self):
        text = document()
        swapped = text.replace("## Ambientación", "## TMP").replace(
            "## Normas generales", "## Ambientación").replace("## TMP", "## Normas generales")
        self.assert_error(swapped, 6, "fuera de orden")
        repeated = text.replace("## Material suelto\n", "## Material suelto\n\n## Ambientación\n")
        self.assert_error(repeated, line_of(repeated, "## Ambientación", -1), "repetido")
        misspelled = text.replace("## Ambientación", "## Ambientacion")
        self.assert_error(misspelled, line_of(misspelled, "## Ambientacion"), "desconocido")
        truncated = text.replace("## Material suelto\n", "")
        self.assert_error(truncated, len(truncated.split("\n")), "Material suelto")

    def test_unknown_heading_levels_and_prose(self):
        text = document()
        for bad in ("# Otro", "### Otra cosa", "#### Fuente", "Texto libre", " ### Fuente",
                    "Estado: FALTA ", "<!-- comentario -->", "   "):
            with self.subTest(bad=bad):
                broken = text.replace("## Material suelto\n", f"## Material suelto\n{bad}\n")
                line = broken.split("\n").index(bad) + 1
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(broken)
                self.assertEqual(ctx.exception.line, line)

    def test_text_before_first_section(self):
        text = HEADER + "Prosa\n" + document()[len(HEADER):]
        self.assert_error(text, 5, "antes")


class StatusAndNotesTest(unittest.TestCase):
    def test_markers(self):
        dossier = parse_dossier(document({
            "Ambientación": "Estado: FALTA\nNota: Pendiente de pedir al staff.\n",
            "Sistema de combate": "Estado: FALTA\n",
        }))
        setting = section(dossier, DossierSection.SETTING)
        self.assertIs(setting.status, DossierSectionStatus.MISSING)
        self.assertEqual(setting.notes, "Pendiente de pedir al staff.")
        assessment = assess_dossier(dossier)
        self.assertEqual(assessment.missing_required, (DossierSection.SETTING,))
        self.assertEqual(assessment.missing_optional, (DossierSection.COMBAT_SYSTEM,))
        self.assertFalse(assessment.ready_for_assimilation)

    def test_missing_optional_does_not_block(self):
        dossier = parse_dossier(document({"Sistema de combate": "Estado: FALTA\n"}))
        self.assertTrue(assess_dossier(dossier).ready_for_assimilation)

    def test_note_without_status_before_sources(self):
        dossier = parse_dossier(document({"Ambientación": "Nota: Resumen.\n" + inline("x")}))
        setting = section(dossier, DossierSection.SETTING)
        self.assertIs(setting.status, DossierSectionStatus.PROVIDED)
        self.assertEqual(setting.notes, "Resumen.")

    def test_invalid_status_and_notes(self):
        cases = {
            "required not applicable": {"Ambientación": "Estado: NO APLICA\n"},
            "unknown marker": {"Ambientación": "Estado: PENDIENTE\n"},
            "status after note": {"Ambientación": "Nota: x.\nEstado: FALTA\n"},
            "two notes": {"Ambientación": "Estado: FALTA\nNota: a.\nNota: b.\n"},
            "note after source": {"Ambientación": inline("x") + "Nota: tarde.\n"},
            "status with sources": {"Ambientación": "Estado: FALTA\n" + inline("x")},
            "provided without sources": {"Ambientación": "Nota: solo nota.\n"},
            "empty note": {"Ambientación": "Estado: FALTA\nNota: \n"},
            "loose status": {"Material suelto": "Estado: FALTA\n"},
            "loose note": {"Material suelto": "Nota: x.\n"},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(document(overrides))
                self.assertIsNotNone(ctx.exception.line)

    def test_contradictions_point_to_the_culprit_line(self):
        text = document({"Ambientación": "Estado: NO APLICA\n"})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(text)
        self.assertEqual(ctx.exception.line, line_of(text, "## Ambientación") + 1)
        text = document({"Ambientación": "Estado: FALTA\n" + inline("x")})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(text)
        self.assertEqual(ctx.exception.line, line_of(text, "## Ambientación") + 2)
        self.assertIn("Estado:", ctx.exception.reason)
        text = document({"Ambientación": "Nota: solo nota.\n"})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(text)
        self.assertEqual(ctx.exception.line, line_of(text, "## Ambientación"))


class MetadataTest(unittest.TestCase):
    def parse_meta(self, meta: str, body: str | None = "~~~~ texto\nx\n~~~~\n",
                   heading: str = "Ambientación") -> DossierSourceSpec:
        source = f"### Fuente\nMetadatos: {meta}\n" + (body or "")
        dossier = parse_dossier(document({heading: source}))
        if heading == "Material suelto":
            return dossier.loose_material[0]
        return section(dossier, DossierSection.SETTING).sources[0]

    def test_order_does_not_matter(self):
        a = self.parse_meta('id="s" | versión="1" | autoridad="Staff" | alcance="foro" | pasaje="P"')
        b = self.parse_meta('pasaje="P" | alcance="foro" | autoridad="Staff" | versión="1" | id="s"')
        self.assertEqual(a, b)

    def test_defaults_for_omitted_optional_keys(self):
        spec = self.parse_meta('id="s" | versión="1" | autoridad="Staff" | alcance="foro"')
        self.assertIsNone(spec.effective_from)
        self.assertIsNone(spec.effective_until)
        self.assertIsNone(spec.section_or_passage)
        self.assertIsNone(spec.path)
        self.assertEqual(spec.inline_text, "x\n")

    def test_explicit_nulls_and_dates(self):
        spec = self.parse_meta('id="s" | versión="1" | autoridad="Staff" | alcance="foro" | '
                               'desde="2026-01-31" | hasta=null | pasaje=null | archivo=null')
        self.assertEqual(spec.effective_from, date(2026, 1, 31))
        self.assertIsNone(spec.effective_until)

    def test_invalid_metadata(self):
        base = 'id="s" | versión="1" | autoridad="Staff" | alcance="foro"'
        cases = {
            "missing required": 'id="s" | versión="1" | autoridad="Staff"',
            "unknown key": base + ' | autor="x"',
            "repeated key": base + ' | id="t"',
            "unquoted text": 'id=s | versión="1" | autoridad="Staff" | alcance="foro"',
            "space before value": 'id= "s" | versión="1" | autoridad="Staff" | alcance="foro"',
            "bad separator": 'id="s"|versión="1" | autoridad="Staff" | alcance="foro"',
            "trailing separator": base + " | ",
            "trailing text": base + " extra",
            "number as text": 'id="s" | versión=1 | autoridad="Staff" | alcance="foro"',
            "outer whitespace": 'id=" s" | versión="1" | autoridad="Staff" | alcance="foro"',
            "control character": 'id="s\\u0001" | versión="1" | autoridad="Staff" | alcance="foro"',
            "empty text": 'id="" | versión="1" | autoridad="Staff" | alcance="foro"',
            "NaN": base + " | desde=NaN",
            "deep nesting": base + " | pasaje=" + "[" * 20000 + "]" * 20000,
            "bad date format": base + ' | desde="2026-1-31"',
            "compact date": base + ' | desde="20260131"',
            "impossible date": base + ' | desde="2026-02-30"',
            "date order": base + ' | desde="2026-02-01" | hasta="2026-01-01"',
            "pasaje type": base + " | pasaje=3",
            "archivo type": base + " | archivo=true",
            "suggestions outside loose": base + " | sugerencias=[]",
            "oversized integer": base + " | pasaje=" + "9" * 5000,
            "lone surrogate in id": 'id="\\ud800" | versión="1" | autoridad="Staff" | alcance="foro"',
            "lone surrogate in version": 'id="s" | versión="\\udfff" | autoridad="Staff" | alcance="foro"',
            "no prefix space": None,
        }
        for name, meta in cases.items():
            with self.subTest(name):
                if meta is None:
                    source = "### Fuente\nMetadatos:" + base + "\n~~~~ texto\nx\n~~~~\n"
                    text = document({"Ambientación": source})
                else:
                    text = document({"Ambientación": f"### Fuente\nMetadatos: {meta}\n~~~~ texto\nx\n~~~~\n"})
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(text)
                meta_line = line_of(text, "## Ambientación") + 2
                self.assertEqual(ctx.exception.line, meta_line, ctx.exception)

    def test_suggestions_in_loose_material(self):
        base = 'id="s" | versión="1" | autoridad="Staff" | alcance="foro"'
        loose = self.parse_meta(base, heading="Material suelto")
        self.assertEqual(loose.suggested_sections, ())
        loose = self.parse_meta(base + ' | sugerencias=["Ambientación", "Sistema de combate"]',
                                heading="Material suelto")
        self.assertEqual(loose.suggested_sections,
                         (DossierSection.SETTING, DossierSection.COMBAT_SYSTEM))
        for bad in ('["Material suelto"]', '["setting"]', '["Ambientación", "Ambientación"]',
                    '"Ambientación"', "null", '[["Ambientación"]]', '[{"a": 1}]', "[1]"):
            with self.subTest(bad=bad):
                text = document({"Material suelto": f"### Fuente\nMetadatos: {base} | "
                                                    f"sugerencias={bad}\n~~~~ texto\nx\n~~~~\n"})
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(text)
                self.assertEqual(ctx.exception.line, line_of(text, "### Fuente", -1) + 1)

    def test_metadata_must_follow_fuente(self):
        stray = document({"Material suelto": META.format(id="x") + "\n"})
        with self.assertRaises(DossierError):
            parse_dossier(stray)
        missing = document({"Material suelto": "### Fuente\nTexto\n"})
        with self.assertRaises(DossierError):
            parse_dossier(missing)
        with_blank = parse_dossier(document({
            "Material suelto": f"### Fuente\n\n{META.format(id='x')}\n~~~~ texto\nx\n~~~~\n"}))
        self.assertEqual(len(with_blank.loose_material), 1)


class FenceTest(unittest.TestCase):
    def setting_text(self, body: str) -> str:
        return section(parse_dossier(document({"Ambientación": body})),
                       DossierSection.SETTING).sources[0].inline_text

    def test_origin_is_inferred(self):
        file_dossier = parse_dossier(document({"Ambientación": file_source("f", "a.md")}))
        spec = section(file_dossier, DossierSection.SETTING).sources[0]
        self.assertEqual(spec.path, "a.md")
        self.assertIsNone(spec.inline_text)

    def test_file_source_cannot_have_fence(self):
        body = file_source("f", "a.md") + "~~~~ texto\nx\n~~~~\n"
        with self.assertRaises(DossierError):
            parse_dossier(document({"Ambientación": body}))
        body = f"### Fuente\n{META.format(id='f')} | archivo=null\n~~~~ texto\nx\n~~~~\n"
        self.assertEqual(self.setting_text(body), "x\n")

    def test_inline_source_needs_immediate_fence(self):
        for body in (f"### Fuente\n{META.format(id='f')}\n\n~~~~ texto\nx\n~~~~\n",
                     f"### Fuente\n{META.format(id='f')}\n ~~~~ texto\nx\n~~~~\n",
                     f"### Fuente\n{META.format(id='f')}\n~~~ texto\nx\n~~~\n",
                     f"### Fuente\n{META.format(id='f')}\n~~~~ text\nx\n~~~~\n",
                     f"### Fuente\n{META.format(id='f')}\n~~~~ texto \nx\n~~~~\n",
                     f"### Fuente\n{META.format(id='f')}\n"):
            with self.subTest(body=body):
                with self.assertRaises(DossierError):
                    parse_dossier(document({"Ambientación": body}))

    def test_literal_preserves_markdown_and_final_lf(self):
        literal = "# Título\n\n## Sub\n- a\n| x | y |\n```\ncode\n```\n   sangría  \n"
        self.assertEqual(self.setting_text(inline("f", literal)), literal)

    def test_longer_fence_allows_short_fence_inside(self):
        literal = "antes\n~~~~\ndespués\n"
        self.assertEqual(self.setting_text(inline("f", literal, fence="~~~~~")), literal)

    def test_fence_collision_and_missing_close(self):
        colliding = document({"Ambientación": inline("f", "a ~~~~ b\n")})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(colliding)
        self.assertEqual(ctx.exception.line, colliding.split("\n").index("a ~~~~ b") + 1)
        with self.assertRaises(DossierError):
            parse_dossier(document({"Ambientación": inline("f", "~~~~~~\n", fence="~~~~~")}))
        opened = f"### Fuente\n{META.format(id='f')}\n~~~~ texto\nx\n"
        unclosed_last = document({"Material suelto": opened})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(unclosed_last)
        self.assertIn("no tiene cierre", ctx.exception.reason)
        self.assertEqual(ctx.exception.line, line_of(unclosed_last, "~~~~ texto", -1))
        unclosed_middle = document({"Ambientación": opened})
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(unclosed_middle)
        opening = line_of(unclosed_middle, "## Ambientación") + 3
        self.assertIn(f"línea {opening} tenga su cierre", ctx.exception.reason)

    def test_empty_inline_text(self):
        for literal in ("", "  \n\n"):
            with self.subTest(literal=literal):
                with self.assertRaises(DossierError):
                    parse_dossier(document({"Ambientación": inline("f", literal)}))

    def test_stray_fence_outside_source(self):
        with self.assertRaises(DossierError):
            parse_dossier(document({"Material suelto": "~~~~ texto\nx\n~~~~\n"}))


class LineEndingTest(unittest.TestCase):
    def test_crlf_and_lf_give_same_literal_and_hash(self):
        lf = document()
        crlf = lf.replace("\n", "\r\n")
        a, b = TempDossier(self, lf), TempDossier(self, crlf)
        la, lb = load_dossier(a.dir), load_dossier(b.dir)
        self.assertEqual(la.dossier, lb.dossier)
        ra = la.sections[0].sources[0].source_ref
        rb = lb.sections[0].sources[0].source_ref
        self.assertEqual(ra.sha256, rb.sha256)
        self.assertEqual(ra.sha256, hashlib.sha256("Texto de la fuente.\n".encode()).hexdigest())

    def test_lone_cr_and_bom(self):
        with self.assertRaises(DossierError) as ctx:
            parse_dossier(document().replace("Foro de prueba", "Foro\rde prueba"))
        self.assertEqual(ctx.exception.line, 3)
        with self.assertRaises(DossierError):
            parse_dossier("\ufeff" + document())
        temp = TempDossier(self, b"\xef\xbb\xbf" + document().encode("utf-8"))
        with self.assertRaises(DossierError) as ctx:
            load_dossier(temp.dir)
        self.assertEqual(ctx.exception.line, 1)

    def test_invalid_utf8_document(self):
        temp = TempDossier(self, document().encode("utf-8") + b"\n\xff\n")
        with self.assertRaises(DossierError) as ctx:
            load_dossier(temp.dir)
        self.assertIsInstance(ctx.exception.__cause__, UnicodeDecodeError)


class LoadTest(unittest.TestCase):
    def test_inline_hash_and_locator_stable_when_editing_elsewhere(self):
        first = TempDossier(self, document())
        edited = document({"Material suelto": inline("otra")}).replace(
            "versión_expediente: 1", "versión_expediente: 2")
        edited = edited.replace("## Ambientación\n" + inline("fuente-1"),
                                "## Ambientación\nNota: añadida.\n" + inline("fuente-1"))
        second = TempDossier(self, edited)
        ref_a = load_dossier(first.dir).sections[1].sources[0].source_ref
        ref_b = load_dossier(second.dir).sections[1].sources[0].source_ref
        self.assertEqual(ref_a.sha256, ref_b.sha256)
        self.assertEqual(ref_a.locator.split("#", 1)[1], ref_b.locator.split("#", 1)[1])
        self.assertEqual(ref_a.locator.split("#", 1)[1], "inline:id=fuente-1&version=1")
        self.assertIsNone(ref_a.observed_at)
        self.assertIsNone(ref_a.ic_date)

    def test_inline_locator_is_percent_encoded(self):
        body = ('### Fuente\nMetadatos: id="a&b" | versión="v 1/2" | autoridad="Staff" | '
                'alcance="foro"\n~~~~ texto\nx\n~~~~\n')
        temp = TempDossier(self, document({"Ambientación": body}))
        ref = load_dossier(temp.dir).sections[1].sources[0].source_ref
        self.assertTrue(ref.locator.endswith("#inline:id=a%26b&version=v%201%2F2"))

    def test_file_source_keeps_exact_bytes(self):
        raw = "línea 1\r\nlínea 2\n".encode("utf-8")
        temp = TempDossier(self, document({"Ambientación": file_source("f", "materiales/a.md", "P")}))
        temp.material("materiales/a.md", raw)
        loaded = load_dossier(temp.dir).sections[1].sources[0]
        self.assertEqual(loaded.literal_text.encode("utf-8"), raw)
        self.assertEqual(loaded.source_ref.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(loaded.source_ref.locator, (temp.dir / "materiales" / "a.md").as_posix())
        self.assertEqual(loaded.source_ref.section_or_passage, "P")

    def test_invalid_file_sources(self):
        cases = {
            "absolute": "/etc/a.md",
            "unc": "//server/share/a.md",
            "drive": "C:/a.md",
            "alternate stream": "a.md:secreto",
            "backslash": "materiales\\\\a.md",
            "traversal": "../fuera.md",
            "dot segment": "./a.md",
            "empty segment": "materiales//a.md",
            "trailing dot": "materiales/a.md.",
        }
        for name, path in cases.items():
            with self.subTest(name):
                text = document({"Ambientación": file_source("f", path)})
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(text)
                self.assertEqual(ctx.exception.line, line_of(text, "## Ambientación") + 2)

    def test_missing_empty_or_invalid_file(self):
        temp = TempDossier(self, document({"Ambientación": file_source("f", "a.md")}))
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)
        (temp.dir / "a.md").mkdir()
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)
        (temp.dir / "a.md").rmdir()
        for raw in (b"", b"  \n", b"\xff"):
            with self.subTest(raw=raw):
                temp.material("a.md", raw)
                with self.assertRaises(DossierError):
                    load_dossier(temp.dir)

    def test_missing_document_or_directory(self):
        temp = TempDossier(self)
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)
        with self.assertRaises(DossierError):
            load_dossier(temp.root / "no-existe")
        for bad in (None, 3):
            with self.subTest(dossier_dir=bad):
                with self.assertRaises(DossierError) as ctx:
                    load_dossier(bad)
                self.assertIsInstance(ctx.exception.__cause__, TypeError)

    def failing_read(self, failing_name: str):
        original = Path.read_bytes

        def read_bytes(path: Path) -> bytes:
            if path.name == failing_name:
                raise OSError("fallo simulado")
            return original(path)

        return mock.patch.object(Path, "read_bytes", read_bytes)

    def test_document_read_error_is_wrapped(self):
        temp = TempDossier(self, document())
        with self.failing_read(DOSSIER_NAME):
            with self.assertRaises(DossierError) as ctx:
                load_dossier(temp.dir)
        self.assertEqual(ctx.exception.locator, (temp.dir / DOSSIER_NAME).as_posix())
        self.assertIsNone(ctx.exception.line)
        self.assertIsInstance(ctx.exception.__cause__, OSError)

    def test_material_read_error_is_wrapped(self):
        text = document({"Ambientación": file_source("f", "a.md")})
        temp = TempDossier(self, text)
        temp.material("a.md", b"contenido\n")
        with self.failing_read("a.md"):
            with self.assertRaises(DossierError) as ctx:
                load_dossier(temp.dir)
        self.assertEqual(ctx.exception.locator, (temp.dir / DOSSIER_NAME).as_posix())
        self.assertEqual(ctx.exception.line, line_of(text, "## Ambientación") + 2)
        self.assertIsInstance(ctx.exception.__cause__, OSError)

    def test_coherent_repeat_and_distinct_versions(self):
        body_rules = file_source("manual", "m.md", "Normas")
        body_sheet = file_source("manual", "m.md", "Fichas")
        v2 = ('### Fuente\nMetadatos: id="manual" | versión="2" | autoridad="Staff" | '
              'alcance="foro" | archivo="m2.md"\n')
        temp = TempDossier(self, document({
            "Normas generales": body_rules, "Creación de fichas": body_sheet,
            "Material suelto": v2}))
        temp.material("m.md", b"manual\n")
        temp.material("m2.md", b"manual nuevo\n")
        loaded = load_dossier(temp.dir)
        a = loaded.sections[0].sources[0]
        b = loaded.sections[2].sources[0]
        self.assertEqual(a.source_ref.sha256, b.source_ref.sha256)
        self.assertEqual((a.spec.section_or_passage, b.spec.section_or_passage), ("Normas", "Fichas"))
        self.assertNotEqual(loaded.loose_material[0].source.source_ref.sha256, a.source_ref.sha256)

    def test_incoherent_repeat_reports_later_line(self):
        cases = {
            "authority": inline("fuente-0").replace('autoridad="Staff"', 'autoridad="Otro"'),
            "inline content": inline("fuente-0", "Otro contenido.\n"),
            "origin": file_source("fuente-0", "a.md"),
        }
        for name, repeat in cases.items():
            with self.subTest(name):
                text = document({"Material suelto": repeat})
                with self.assertRaises(DossierError) as ctx:
                    parse_dossier(text)
                self.assertEqual(ctx.exception.line, line_of(text, "### Fuente", -1) + 1)
                self.assertIn("línea", ctx.exception.reason)


class SymlinkTest(unittest.TestCase):
    def link(self, target: Path, link: Path, *, directory: bool) -> None:
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("el sistema no permite crear enlaces simbólicos a este usuario")

    def test_symlinked_source_file(self):
        temp = TempDossier(self, document({"Ambientación": file_source("f", "a.md")}))
        outside = temp.root / "fuera.md"
        outside.write_bytes(b"secreto\n")
        self.link(outside, temp.dir / "a.md", directory=False)
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)

    def test_symlinked_intermediate_directory(self):
        temp = TempDossier(self, document({"Ambientación": file_source("f", "sub/a.md")}))
        outside = temp.root / "fuera"
        outside.mkdir()
        (outside / "a.md").write_bytes(b"secreto\n")
        self.link(outside, temp.dir / "sub", directory=True)
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)

    def test_symlinked_document_or_directory(self):
        temp = TempDossier(self)
        real = temp.root / "real.md"
        real.write_bytes(document().encode("utf-8"))
        self.link(real, temp.dir / DOSSIER_NAME, directory=False)
        with self.assertRaises(DossierError):
            load_dossier(temp.dir)
        linked_dir = temp.root / "enlazado"
        self.link(temp.dir, linked_dir, directory=True)
        with self.assertRaises(DossierError):
            load_dossier(linked_dir)


if __name__ == "__main__":
    unittest.main()
