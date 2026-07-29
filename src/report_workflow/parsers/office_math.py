"""Reading the equations Word stores as OMML.

An equation typed in Word is not text. It is an ``m:oMath`` tree beside the
runs, and every reader here walked past it. The two readers failed differently
and both failed silently.

The ingest reader took ``paragraph.text``, which is the runs only, so
"雷諾數定義為 Re=ρVD/μ ，本次實驗取 D = 25 mm。" arrived as
"雷諾數定義為  ，本次實驗取 D = 25 mm。" — a sentence still promising a
definition with the definition gone — and an equation standing alone on its own
line produced no block at all, so nothing recorded that it had ever been there.

The revision reader collected every ``}t`` descendant, which does reach ``m:t``,
and joined them with nothing. That turned ρVD over μ into ``ρVDμ``: not a loss
but a different formula, written back into the author's own report as if they
had typed it.

So the fraction bar has to survive, and with it every other construct whose
meaning lives in the layout rather than in the characters — superscripts,
radicals, delimiters, n-ary operators. Flattening those is what produces a
plausible wrong answer, which is worse than an obvious gap.

The notation is the readable one an engineer would write in prose — ``2F/(ρU^2A)``,
``sqrt(2gh)`` — not TeX. Round-tripping an equation back into a real Word
equation is a larger promise than this makes: what is fixed here is that the
formula reaches the ledger, and reaches it saying what the author wrote.
"""

#: The two elements that hold an equation: inline within a sentence, and set on
#: its own line.
_MATH_ROOTS = ("oMath", "oMathPara")

_COMBINING_MACRON = "̄"
_COMBINING_CIRCUMFLEX = "̂"

# Characters that make a rendered part more than a single term, so putting it
# above or below something else needs brackets to stay unambiguous.
_OPERATORS = "+-*/^_= −±"


def _local(tag: object) -> str:
    """Local name of an XML tag, namespace dropped."""
    text = str(tag)
    return text.rsplit("}", 1)[-1] if "}" in text else text


def _is_bracketed(text: str) -> bool:
    """True when the whole string is already inside one pair of brackets."""
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index < len(text) - 1:
                return False
    return depth == 0


def _atom(text: str) -> str:
    """Bracket a part when writing it inline would change what it groups."""
    if len(text) <= 1 or _is_bracketed(text):
        return text
    return f"({text})" if any(char in text for char in _OPERATORS) else text


def _child(node, name: str):
    for child in node:
        if _local(child.tag) == name:
            return child
    return None


def _children(node, name: str) -> list:
    return [child for child in node if _local(child.tag) == name]


def _slot(node, name: str) -> str:
    child = _child(node, name)
    return _render(child) if child is not None else ""


def _property_value(props, name: str, default: str) -> str:
    """The ``m:val`` of a property such as ``m:begChr``.

    An explicit empty value is a real answer — a delimiter written with only a
    closing brace sets ``begChr`` to nothing — so it is returned as it stands.
    """
    if props is None:
        return default
    child = _child(props, name)
    if child is None:
        return default
    for key, value in child.attrib.items():
        if _local(key) == "val":
            return value
    return default


def _fraction(node) -> str:
    numerator = _slot(node, "num")
    denominator = _slot(node, "den")
    if not numerator or not denominator:
        return numerator or denominator
    return f"{_atom(numerator)}/{_atom(denominator)}"


def _superscript(node) -> str:
    base = _slot(node, "e")
    exponent = _slot(node, "sup")
    return f"{_atom(base)}^{_atom(exponent)}" if exponent else base


def _subscript(node) -> str:
    base = _slot(node, "e")
    index = _slot(node, "sub")
    return f"{_atom(base)}_{_atom(index)}" if index else base


def _sub_superscript(node) -> str:
    out = _atom(_slot(node, "e"))
    index = _slot(node, "sub")
    exponent = _slot(node, "sup")
    if index:
        out += f"_{_atom(index)}"
    if exponent:
        out += f"^{_atom(exponent)}"
    return out


def _pre_sub_superscript(node) -> str:
    index = _slot(node, "sub")
    exponent = _slot(node, "sup")
    prefix = ""
    if index:
        prefix += f"_{_atom(index)}"
    if exponent:
        prefix += f"^{_atom(exponent)}"
    return f"{prefix}{_slot(node, 'e')}"


def _radical(node) -> str:
    body = _slot(node, "e")
    degree = _slot(node, "deg")
    return f"root({degree})({body})" if degree else f"sqrt({body})"


def _delimiter(node) -> str:
    props = _child(node, "dPr")
    opening = _property_value(props, "begChr", "(")
    closing = _property_value(props, "endChr", ")")
    separator = _property_value(props, "sepChr", ",")
    parts = [_render(part) for part in _children(node, "e")]
    return opening + separator.join(parts) + closing


def _nary(node) -> str:
    props = _child(node, "naryPr")
    out = _property_value(props, "chr", "∫")
    index = _slot(node, "sub")
    exponent = _slot(node, "sup")
    if index:
        out += f"_{_atom(index)}"
    if exponent:
        out += f"^{_atom(exponent)}"
    body = _slot(node, "e")
    return f"{out} {body}" if body else out


def _function(node) -> str:
    name = _slot(node, "fName")
    body = _slot(node, "e")
    return f"{name}({body})" if name else body


def _lower_limit(node) -> str:
    base = _slot(node, "e")
    limit = _slot(node, "lim")
    return f"{_atom(base)}_{_atom(limit)}" if limit else base


def _upper_limit(node) -> str:
    base = _slot(node, "e")
    limit = _slot(node, "lim")
    return f"{_atom(base)}^{_atom(limit)}" if limit else base


def _matrix(node) -> str:
    rows = [
        ", ".join(_render(cell) for cell in _children(row, "e"))
        for row in _children(node, "mr")
    ]
    return "[" + "; ".join(rows) + "]"


def _equation_array(node) -> str:
    return "; ".join(_render(row) for row in _children(node, "e"))


def _accent(node) -> str:
    """A hat or a vector arrow over a symbol.

    Dropped, the mean and the reading become the same string, and a report that
    cites one for the other is wrong in a way nothing downstream can see. The
    combining character keeps them apart.
    """
    props = _child(node, "accPr")
    mark = _property_value(props, "chr", _COMBINING_CIRCUMFLEX)
    return f"{_slot(node, 'e')}{mark}"


def _bar(node) -> str:
    return f"{_slot(node, 'e')}{_COMBINING_MACRON}"


_HANDLERS = {
    "f": _fraction,
    "sSup": _superscript,
    "sSub": _subscript,
    "sSubSup": _sub_superscript,
    "sPre": _pre_sub_superscript,
    "rad": _radical,
    "d": _delimiter,
    "nary": _nary,
    "func": _function,
    "limLow": _lower_limit,
    "limUpp": _upper_limit,
    "m": _matrix,
    "eqArr": _equation_array,
    "acc": _accent,
    "bar": _bar,
}


def _render(node) -> str:
    name = _local(node.tag)
    if name.endswith("Pr"):
        # Formatting properties. They hold no text of their own and their
        # attributes are read by the handler that needs them.
        return ""
    if name == "t":
        return node.text or ""
    handler = _HANDLERS.get(name)
    if handler is not None:
        return handler(node)
    return "".join(_render(child) for child in node)


def omml_to_text(node) -> str:
    """One ``m:oMath`` or ``m:oMathPara`` element as readable text."""
    return _render(node)


def _collect(node, parts: list[str]) -> None:
    for child in node:
        name = _local(child.tag)
        if name in _MATH_ROOTS:
            parts.append(_render(child))
        elif name == "t":
            parts.append(child.text or "")
        else:
            _collect(child, parts)


def element_text(node) -> str:
    """Every piece of text under one element, in the order Word wrote it.

    Works on an ``lxml`` element from python-docx and on an
    ``xml.etree.ElementTree`` one alike, because both iterate their children and
    expose ``.tag`` and ``.text``.
    """
    parts: list[str] = []
    _collect(node, parts)
    return "".join(parts)


def cell_text(node) -> str:
    """One ``w:tc`` read as python-docx reads it, with the equations kept."""
    return "\n".join(
        element_text(paragraph) for paragraph in node if _local(paragraph.tag) == "p"
    )
