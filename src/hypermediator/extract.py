"""Parse rendered HTML back into affordance controls (stdlib parser only)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

from hypermediator.microdata import ITEMTYPE

_VOID = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
)
_NATIVE_CONTROLS = frozenset({"a", "form", "button", "input", "select", "textarea"})
_NON_FIELD_INPUTS = frozenset({"hidden", "submit", "button", "image", "reset"})
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str
    required: bool
    described_by: tuple[str, ...]


@dataclass(frozen=True)
class Control:
    kind: Literal["link", "form"]
    id: str | None
    name: str | None
    href: str | None
    method: str
    rel: tuple[str, ...]
    label: str
    enabled: bool
    reason: str | None
    fields: tuple[Field, ...]
    hx: Mapping[str, str]
    wrapper_id: str | None


@dataclass(frozen=True)
class Page:
    controls: tuple[Control, ...]
    ids: Counter[str]
    text_by_id: Mapping[str, str]
    hx_elements: tuple[tuple[str, Mapping[str, str], bool], ...]

    def by_name(self, name: str) -> list[Control]:
        return [c for c in self.controls if c.name == name]


@dataclass(eq=False)
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node | str] = field(default_factory=list)

    def walk(self) -> Iterator[_Node]:
        """Yield this node's descendants in document order."""
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.walk()

    def text(self) -> str:
        parts = (c if isinstance(c, str) else c.text() for c in self.children)
        return _WS.sub(" ", " ".join(parts)).strip()

    def ancestors(self) -> Iterator[_Node]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = _Node("#root", {})
        self._current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._current)
        self._current.children.append(node)
        if tag not in _VOID:
            self._current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._current)
        self._current.children.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        # Close back to the nearest matching open element; this also implicitly
        # closes unclosed <p>/<li>. A stray end tag with no open match is ignored.
        node: _Node | None = self._current
        while node is not None and node is not self.root:
            if node.tag == tag:
                self._current = node.parent or self.root
                return
            node = node.parent

    def handle_data(self, data: str) -> None:
        self._current.children.append(data)


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(value.split()) if value else ()


def _find_by_id(nodes: list[_Node]) -> dict[str, _Node]:
    found: dict[str, _Node] = {}
    for node in nodes:
        if "id" in node.attrs:
            found.setdefault(node.attrs["id"], node)
    return found


class _Extractor:
    def __init__(self, root: _Node) -> None:
        self.nodes = list(root.walk())
        self.by_id = _find_by_id(self.nodes)
        self.microdata = self._read_microdata()

    def _read_microdata(self) -> dict[str, tuple[str, tuple[str, ...]]]:
        """Map control element id -> (name, microdata rels)."""
        result: dict[str, tuple[str, tuple[str, ...]]] = {}
        for node in self.nodes:
            if node.tag == "span" and "itemscope" in node.attrs:
                if node.attrs.get("itemtype") != ITEMTYPE:
                    continue
                props: dict[str, list[str]] = {}
                for meta in node.walk():
                    if meta.tag == "meta" and "itemprop" in meta.attrs:
                        props.setdefault(meta.attrs["itemprop"], []).append(
                            meta.attrs.get("content", "")
                        )
                for control_id in props.get("control", []):
                    name = (props.get("name") or [""])[0]
                    result[control_id] = (name, tuple(props.get("rel", [])))
        return result

    def _text_of_ids(self, ids: tuple[str, ...]) -> str:
        return " ".join(self.by_id[i].text() for i in ids if i in self.by_id)

    def _accessible_name(self, node: _Node) -> str:
        if node.attrs.get("aria-label"):
            return node.attrs["aria-label"].strip()
        labelled = _WS.sub(" ", self._text_of_ids(_tokens(node.attrs.get("aria-labelledby"))))
        if labelled.strip():
            return labelled.strip()
        if node.tag == "input":
            return node.attrs.get("value", "").strip()
        return node.text()

    @staticmethod
    def _submit_button(form: _Node) -> _Node | None:
        for node in form.walk():
            if node.tag == "button" and node.attrs.get("type", "submit") == "submit":
                return node
            if node.tag == "input" and node.attrs.get("type") in ("submit", "image"):
                return node
        return None

    def _field_label(self, node: _Node) -> str:
        field_id = node.attrs.get("id")
        if field_id:
            for label in self.nodes:
                if label.tag == "label" and label.attrs.get("for") == field_id:
                    return self._clean_label(label.text())
        for ancestor in node.ancestors():
            if ancestor.tag == "label":
                return self._clean_label(ancestor.text())
        return self._clean_label(node.attrs.get("aria-label", ""))

    @staticmethod
    def _clean_label(text: str) -> str:
        return text.strip().removesuffix(":").strip()

    def _fields(self, form: _Node) -> tuple[Field, ...]:
        fields: list[Field] = []
        for node in form.walk():
            if node.tag not in ("input", "select", "textarea") or not node.attrs.get("name"):
                continue
            kind = node.attrs.get("type", "text") if node.tag == "input" else node.tag
            if node.tag == "input" and kind in _NON_FIELD_INPUTS:
                continue
            fields.append(
                Field(
                    name=node.attrs["name"],
                    label=self._field_label(node),
                    type=kind,
                    required="required" in node.attrs,
                    described_by=_tokens(node.attrs.get("aria-describedby")),
                )
            )
        return tuple(fields)

    def control(self, node: _Node) -> Control:
        is_form = node.tag == "form"
        element_id = node.attrs.get("id")
        name, micro_rels = self.microdata.get(element_id or "", (None, ()))
        rel = tuple(dict.fromkeys(_tokens(node.attrs.get("rel")) + micro_rels))
        wrapper = next(
            (a for a in node.ancestors() if "hm-control" in _tokens(a.attrs.get("class"))), None
        )
        hx = {k: v for k, v in node.attrs.items() if k.startswith("hx-")}
        if is_form:
            button = self._submit_button(node)
            label = self._accessible_name(button) if button else ""
            enabled = "action" in node.attrs and not (button and "disabled" in button.attrs)
            describer = button
            href = node.attrs.get("action")
            method = node.attrs.get("method", "GET").upper()
            fields = self._fields(node)
        else:
            label = self._accessible_name(node)
            enabled = "href" in node.attrs and node.attrs.get("aria-disabled") != "true"
            describer = node
            href = node.attrs.get("href")
            method = "GET"
            fields = ()
        reason = None
        if describer is not None and describer.attrs.get("aria-describedby"):
            reason = _WS.sub(
                " ", self._text_of_ids(_tokens(describer.attrs["aria-describedby"]))
            ).strip()
        return Control(
            kind="form" if is_form else "link",
            id=element_id,
            name=name,
            href=href,
            method=method,
            rel=rel,
            label=label,
            enabled=enabled,
            reason=reason,
            fields=fields,
            hx=hx,
            wrapper_id=wrapper.attrs.get("id") if wrapper else None,
        )


def extract(html: str) -> Page:
    """Parse rendered HTML into a Page of controls, ids, text and hx-* elements."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    extractor = _Extractor(builder.root)
    nodes = extractor.nodes
    controls = tuple(extractor.control(n) for n in nodes if n.tag in ("a", "form"))
    ids = Counter(n.attrs["id"] for n in nodes if "id" in n.attrs)
    text_by_id = {i: n.text() for i, n in extractor.by_id.items()}
    hx_elements = tuple(
        (
            n.tag,
            {k: v for k, v in n.attrs.items() if k.startswith("hx-")},
            n.tag in _NATIVE_CONTROLS or any(d.tag in _NATIVE_CONTROLS for d in n.walk()),
        )
        for n in nodes
        if any(k.startswith("hx-") for k in n.attrs)
    )
    return Page(controls=controls, ids=ids, text_by_id=text_by_id, hx_elements=hx_elements)
