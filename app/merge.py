# SPDX-License-Identifier: MIT

"""What the 3D viewer already has when a project is uploaded again (0.5.0).

A POST of an existing project name clears the viewer's configuration (measured), so the app PUTs one afterwards. Without a
merge that would also wipe what the user set in the viewer itself: Data Layer variable bindings on axes the app leaves unbound,
Visual Effects (GeometryProperties), safe zones, tool nodes ...

The rule (merge_configuration):
  * an axis the app binds to a MOTION axis gets the app's entry;
  * any other axis of the new model keeps the viewer's current entry (any ConnectionType) - except when that entry is exactly what
    the app sent last time (the user has cleared the binding in the app since then): it is dropped;
  * viewer entries for names that are no longer a model axis are dropped and reported;
  * every other top-level key of the viewer's configuration is kept (it wins over the import-time copy in configuration_extra);
    the TrackId is never sent.
"""

ENTRY_KEYS = ("ModelAxisName", "ConnectionType", "DatalayerNode", "DatalayerVariable", "ExpressionScript")


def entry_key(e: dict) -> tuple:
    """An entry as the app compares it with what it sent: the five keys the viewer keeps, a missing one counts as empty."""
    return tuple(str(e.get(k) or "") for k in ENTRY_KEYS)


def merge_configuration(app_cfg: dict, viewer_cfg: dict, model_axes: list, bound: set, last_sent: dict) -> tuple:
    """(configuration to send, report). app_cfg = xmlgen.configuration(project), viewer_cfg = the viewer's current configuration,
    model_axes = the axis names of the new model, bound = the axes the app binds to a MOTION axis, last_sent = {axis name: entry} the app sent last time (may be empty).
    report: {"kept_bindings": [axis names], "cleared": [axis names the user cleared in the app], "dropped": [names without an
    axis any more], "kept_settings": [top-level keys kept from the viewer]}."""
    last_sent = last_sent or {}
    axes = set(model_axes)
    app_entries = {}
    for e in app_cfg.get("ConfiguredAxis") or []:
        if isinstance(e, dict) and e.get("ModelAxisName") in axes and e["ModelAxisName"] in bound:
            app_entries.setdefault(e["ModelAxisName"], e)
    out_entries = list(app_entries.values())
    report = {"kept_bindings": [], "cleared": [], "dropped": [], "kept_settings": []}
    seen = set()
    for e in viewer_cfg.get("ConfiguredAxis") or []:
        if not isinstance(e, dict) or not e.get("ModelAxisName"):
            continue
        name = e["ModelAxisName"]
        if name not in axes:
            if name not in report["dropped"]:
                report["dropped"].append(name)
            continue
        if name in app_entries or name in seen:
            continue
        seen.add(name)
        sent = last_sent.get(name)
        if isinstance(sent, dict) and entry_key(sent) == entry_key(e):
            report["cleared"].append(name)
            continue
        out_entries.append(e)
        report["kept_bindings"].append(name)
    cfg = {k: v for k, v in app_cfg.items() if k != "ConfiguredAxis"}
    for k, v in viewer_cfg.items():
        if k in ("ConfiguredAxis", "TrackId"):
            continue
        cfg[k] = v
        report["kept_settings"].append(k)
    cfg["ConfiguredAxis"] = out_entries
    cfg.pop("TrackId", None)
    return cfg, report
