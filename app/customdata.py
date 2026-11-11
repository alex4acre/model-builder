# SPDX-License-Identifier: MIT

"""The customdata attribute of parts and frames: Display ID and the entries the editor keeps unchanged (0.5.0).

From the 3D viewer 4.6.2 client code (not device-tested): the attribute is split on the two-character string ",;"; each entry is
trimmed and matched against  displayid( <id> )  with <id> = [\\w#-]+ (ASCII), and  visible( always | active ), case-insensitive.
A geometry's customdata list is [customdata of the transform/axis it sits directly in, its own]; every distinct string forms
one group. A transform copies its customdata over that of its child transforms (the parent wins).
"""

import re

SEP = ",;"
ID_RE = re.compile(r"displayid *\( *([\w#\-]+) *\)", re.IGNORECASE | re.ASCII)
VALID_ID = re.compile(r"[\w#\-]+", re.ASCII)


def entries(raw) -> list:
    """The entries of a customdata text (not trimmed: they are written back as they were)."""
    return str(raw).split(SEP) if raw else []


def parse(raw) -> str:
    """The Display ID of a customdata text ("" if none; the last displayid entry wins, as in the viewer)."""
    found = ""
    for e in entries(raw):
        m = ID_RE.fullmatch(e.strip())
        if m:
            found = m.group(1)
    return found


def check_id(display_id) -> str:
    if not isinstance(display_id, str):
        raise ValueError("The Display ID is text")
    v = display_id.strip()
    if v and not VALID_ID.fullmatch(v):
        raise ValueError("A Display ID has letters, digits, '_', '-' or '#' only (the viewer ignores anything else)")
    return v


def compose(raw, display_id: str) -> str:
    """The customdata text for a node whose stored text is raw and whose Display ID is display_id. Other entries (visible(...),
    unknown) stay as they were, in their place; a Display ID that did not change leaves the text untouched."""
    display_id = check_id(display_id)
    if parse(raw) == display_id:
        return raw or ""
    parts = entries(raw)
    hits = [i for i, e in enumerate(parts) if ID_RE.fullmatch(e.strip())]
    if display_id:
        new = "displayid(%s)" % display_id
        if hits:
            parts[hits[-1]] = new
            parts = [e for i, e in enumerate(parts) if i not in hits[:-1]]
        else:
            parts.insert(0, new)
    else:
        parts = [e for i, e in enumerate(parts) if i not in hits]
    return SEP.join(parts)


def other_entries(raw) -> list:
    """The entries that are not a displayid, trimmed (for display)."""
    return [e.strip() for e in entries(raw) if e.strip() and not ID_RE.fullmatch(e.strip())]


def attrs_with(xattrs: dict, display_id: str) -> dict:
    """A copy of the node's other attributes with customdata set from the Display ID: in place when the node already had one,
    at the end otherwise; removed when nothing is left."""
    xattrs = dict(xattrs or {})
    if display_id is None:
        return xattrs                      # the node carries no Display ID field: its attributes are written as they are
    raw = xattrs.get("customdata")
    text = compose(raw, display_id)
    if "customdata" in xattrs:
        if text:
            xattrs["customdata"] = text
        else:
            del xattrs["customdata"]
    elif text:
        xattrs["customdata"] = text
    return xattrs
