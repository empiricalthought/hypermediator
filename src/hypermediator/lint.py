"""Template linter: report hand-written links and forms that bypass hypermediator's tags."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.apps import apps
from django.template import engines
from django.template.backends.django import DjangoTemplates
from django.urls import NoReverseMatch, Resolver404, resolve

from hypermediator.endpoints import endpoint_for

_MESSAGE = (
    "Hand-written link to affordance '{name}'; use {{% hm_link %}}, {{% hm_action %}} or "
    "{{% hm_form %}} so see/use checks apply."
)
_TAG = r"\{%(?:[^%\n]|%(?!\}))*%\}|\{\{(?:[^}\n]|\}(?!\}))*\}\}"
# Alternatives inside a quoted value are mutually exclusive so a failed match stays linear.
_CHAR = r"\{(?![%{])"
_ATTRIBUTE = re.compile(
    rf"""(?<![\w-])(?:href|action)\s*=\s*"""
    rf"""(?:"((?:{_TAG}|[^"{{]|{_CHAR})*)"|'((?:{_TAG}|[^'{{]|{_CHAR})*)')""",
    re.IGNORECASE,
)
_URL_TAG = re.compile(r"""\{%\s*url\s+(?:'([^']+)'|"([^"]+)")""")
_COMMENT = re.compile(r"\{%\s*comment\b.*?%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}", re.DOTALL)
_SUFFIXES = (".html", ".txt")
_OWN_TEMPLATES = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class LintIssue:
    template: str
    line: int
    url_name: str
    message: str


def _affordance_name(value: str) -> str | None:
    """The URL name of the affordance this attribute value links to, if any."""
    tag = _URL_TAG.search(value)
    if tag is not None:
        name = tag.group(1) or tag.group(2)
        try:
            return name if endpoint_for(name) is not None else None
        except NoReverseMatch:
            return None
    if value.startswith("/") and "{{" not in value and "{%" not in value:
        try:
            match = resolve(urlsplit(value).path)
        except Resolver404:
            return None
        name = match.view_name
        return name if name and endpoint_for(name) is not None else None
    return None


def lint_source(name: str, source: str) -> list[LintIssue]:
    """The hand-written links to affordances in one template's source."""
    issues: list[LintIssue] = []
    source = _COMMENT.sub(lambda m: "\n" * m.group().count("\n"), source)
    for attribute in _ATTRIBUTE.finditer(source):
        value = attribute.group(1) if attribute.group(1) is not None else attribute.group(2)
        url_name = _affordance_name(value)
        if url_name is not None:
            line = source.count("\n", 0, attribute.start()) + 1
            issues.append(LintIssue(name, line, url_name, _MESSAGE.format(name=url_name)))
    return issues


def _template_roots() -> list[Path]:
    roots: list[Path] = []
    for engine in engines.all():
        if not isinstance(engine, DjangoTemplates):
            continue
        candidates = [Path(d) for d in engine.dirs]
        if engine.app_dirs:
            candidates += [Path(c.path) / "templates" for c in apps.get_app_configs()]
        for root in candidates:
            if root.is_dir() and root not in roots and root.resolve() != _OWN_TEMPLATES.resolve():
                roots.append(root)
    return roots


def lint_files() -> Iterator[tuple[Path, LintIssue]]:
    """Every issue in every template, with the full path of the template it is in."""
    for root in _template_roots():
        for path in sorted(root.rglob("*")):
            if path.suffix in _SUFFIXES and path.is_file():
                name = path.relative_to(root).as_posix()
                for issue in lint_source(name, path.read_text(encoding="utf-8")):
                    yield path, issue


def lint_templates() -> list[LintIssue]:
    """Lint every template under the configured engines' DIRS and installed apps' templates."""
    return [issue for _, issue in lint_files()]
