# SPDX-License-Identifier: MIT

"""Opening an existing 3D viewer project read-only: download it, extract it safely into a cache folder (one project at a
time) and analyse it. The viewer returns a project as a flat zip (XML + STLs); a package (Model.zip inside, plus
<name>.json) is accepted too."""

import io
import json
import os
import re
import shutil
import zipfile

from app import viewanalysis

MB = 1024 * 1024
MAX_TOTAL = 500 * MB            # all extracted files together
MAX_FILE = 250 * MB             # one file
MAX_ZIP = 520 * MB              # what is downloaded
ALLOWED = (".xml", ".stl", ".json", ".png", ".jpg", ".jpeg")


class ExtractError(Exception):
    pass


class _Budget:
    def __init__(self, total, per_file):
        self.total, self.per_file, self.used = total, per_file, 0


def safe_name(name: str) -> str:
    """A folder name for a project name."""
    n = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name))[:80].lstrip(".")
    return n or "project"


def _member(name):
    """(basename or None for a folder, problem text or None). Absolute paths and '..' are refused."""
    n = name.replace("\\", "/")
    if "\x00" in n:
        return None, "contains a NUL character"
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None, "is an absolute path"
    parts = n.split("/")
    if any(p == ".." for p in parts):
        return None, 'contains ".."'
    if n.endswith("/"):
        return None, None
    return parts[-1], None


def extract(data: bytes, dest: str, budget: _Budget = None, depth: int = 0) -> dict:
    """Extract the allowed files of a zip flat into dest. Returns {"files": {name: size}, "json": {name: parsed JSON},
    "warnings": [text]}. Raises ExtractError (a size limit, a broken zip)."""
    budget = budget or _Budget(MAX_TOTAL, MAX_FILE)
    res = {"files": {}, "json": {}, "warnings": []}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ExtractError("The download is not a zip file") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > 5000:
            raise ExtractError("The zip has more than 5000 entries")
        for info in infos:
            base, problem = _member(info.filename)
            if problem:
                res["warnings"].append(f'Ignored "{info.filename}": the path {problem}.')
                continue
            if base is None or base.startswith(".") or "__MACOSX" in info.filename.split("/"):
                continue
            ext = os.path.splitext(base)[1].lower()
            if ext == ".zip" and depth == 0:
                if info.file_size > budget.per_file:
                    raise ExtractError(f'"{base}" is larger than {budget.per_file // MB} MB')
                budget.used += info.file_size           # held in memory while it is read
                if budget.used > budget.total:
                    raise ExtractError(f"The project is larger than {budget.total // MB} MB")
                try:
                    inner = zf.read(info)
                except (RuntimeError, zipfile.BadZipFile, NotImplementedError) as e:
                    raise ExtractError(f'"{base}" cannot be read: {e}') from None
                budget.used -= info.file_size
                sub = extract(inner, dest, budget, depth + 1)
                for k in ("files", "json"):
                    res[k].update(sub[k])
                res["warnings"] += sub["warnings"]
                continue
            if ext not in ALLOWED:
                res["warnings"].append(f'Ignored "{base}": only {", ".join(ALLOWED)} files are used.')
                continue
            if info.file_size > budget.per_file:
                raise ExtractError(f'"{base}" is larger than {budget.per_file // MB} MB')
            if base in res["files"]:
                res["warnings"].append(f'"{base}" is in the zip more than once; the last one is used.')
            os.makedirs(dest, exist_ok=True)
            size = 0
            try:
                with zf.open(info) as src, open(os.path.join(dest, base), "wb") as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        size += len(chunk)
                        budget.used += len(chunk)
                        if size > budget.per_file:
                            raise ExtractError(f'"{base}" is larger than {budget.per_file // MB} MB')
                        if budget.used > budget.total:
                            raise ExtractError(f"The project is larger than {budget.total // MB} MB")
                        out.write(chunk)
            except (RuntimeError, zipfile.BadZipFile, NotImplementedError) as e:
                raise ExtractError(f'"{base}" cannot be read: {e}') from None
            res["files"][base] = size
            if ext == ".json":
                try:
                    with open(os.path.join(dest, base), "rb") as f:
                        res["json"][base] = json.loads(f.read().decode("utf-8-sig"))
                except ValueError:
                    res["warnings"].append(f'"{base}" is not valid JSON and is ignored.')
    return res


def find_file(folder: str, name: str):
    """Path of a file in folder by name: the exact name first, else the same name in any case; None if there is none or
    the name is not a plain file name."""
    if not name or "/" in name or "\\" in name or name.startswith(".") or not os.path.isdir(folder):
        return None
    exact = os.path.join(folder, name)
    if os.path.isfile(exact):
        return exact
    low = name.lower()
    for f in sorted(os.listdir(folder)):
        if f.lower() == low and os.path.isfile(os.path.join(folder, f)):
            return os.path.join(folder, f)
    return None


def open_project(viewer, name: str, root: str) -> dict:
    """Download, extract into root/<safe name>/ (everything else in root is removed first: one project at a time) and
    analyse. Returns {"name", "dir", "xml", "configuration", "files", "warnings", + the analysis}."""
    data = viewer.project_zip(name)
    if len(data) > MAX_ZIP:
        raise ExtractError(f"The download is larger than {MAX_ZIP // MB} MB")
    configuration = viewer.project_configuration(name)
    os.makedirs(root, exist_ok=True)
    for entry in os.listdir(root):
        p = os.path.join(root, entry)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) and not os.path.islink(p) else os.unlink(p)
    dest = os.path.join(root, safe_name(name))
    try:
        ex = extract(data, dest)
    except ExtractError:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    os.makedirs(dest, exist_ok=True)
    warnings = [viewanalysis._warn("extract", t, None, "info") for t in ex["warnings"]]
    xmls = sorted(f for f in ex["files"] if f.lower().endswith(".xml"))
    if not xmls:
        shutil.rmtree(dest, ignore_errors=True)
        raise ExtractError("The project has no machine_definition XML file")
    pick = next((f for f in xmls if f.lower() == name.lower() + ".xml"), xmls[0])
    if len(xmls) > 1:
        warnings.append(viewanalysis._warn("extract", f'The project has {len(xmls)} XML files; "{pick}" is shown.', None, "info"))
    with open(os.path.join(dest, pick), "rb") as f:
        xml = f.read().decode("utf-8-sig", "replace")
    # the bindings: the viewer's own configuration; if it has none, the package's JSON
    if not (isinstance(configuration, dict) and configuration.get("ConfiguredAxis")):
        pkg = next((ex["json"][j] for j in sorted(ex["json"]) if j.lower() == name.lower() + ".json" and isinstance(ex["json"][j], dict)), None)
        pkg = pkg or next((v for _, v in sorted(ex["json"].items()) if isinstance(v, dict) and v.get("ConfiguredAxis")), None)
        if pkg is not None:
            configuration = pkg
            warnings.append(viewanalysis._warn("extract", "The viewer holds no axis bindings for this project; the bindings are taken from the JSON in the package.", None, "info"))
        elif not isinstance(configuration, dict):
            configuration = None
    files = sorted(ex["files"])
    analysis = viewanalysis.analyse(xml, configuration, files)
    analysis["warnings"] = warnings + analysis["warnings"]
    return {"name": name, "dir": dest, "xml": xml, "configuration": configuration,
            "files": [{"name": f, "size": ex["files"][f]} for f in files], "warnings": analysis["warnings"], **{k: v for k, v in analysis.items() if k != "warnings"}}
