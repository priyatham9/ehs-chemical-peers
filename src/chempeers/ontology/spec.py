"""Load and validate the declarative ontology spec (``spec.json``).

The spec is plain JSON, so it needs no dependency. Validation is static: it
checks the spec against itself (keys exist, links resolve, actions edit only
editable properties, functions point at code that exists) before any data is
read. Data-level checks (primary-key uniqueness, property types, one-to-one
violations, dangling foreign keys) happen when objects are loaded, in
:mod:`.runtime`. All errors are collected and raised together.
"""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SPEC_PATH = Path(__file__).with_name("spec.json")

PROPERTY_TYPES = ("string", "integer", "double", "boolean", "string_array")
CARDINALITIES = ("one_to_one", "many_to_one", "many_to_many")
FK_CARDINALITIES = ("one_to_one", "many_to_one")
JOIN_RULES = ("source_array_contains_target_key", "through_object")
OPERATORS = ("equals", "not_equals", "is_null", "not_null")
PARAMETER_TYPES = ("string", "integer", "double", "boolean", "object_reference")


class SpecError(ValueError):
    """Raised when the ontology spec is internally inconsistent."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("invalid ontology spec:\n  - " + "\n  - ".join(self.errors))


def resolve_dotted(path: str) -> Any:
    """Import ``package.module.attr`` and return ``attr``."""
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ImportError(f"{path!r} is not a dotted path")
    return getattr(importlib.import_module(module_name), attr)


def check_value_type(value: Any, type_name: str) -> bool:
    """Return True if a JSON literal is compatible with a property type."""
    if value is None:
        return True
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "double":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "string_array":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, str)


class OntologySpec:
    """A validated spec with lookup helpers (object, link, action, function by api_name)."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = copy.deepcopy(raw)
        self.object_types = {o["api_name"]: o for o in self.raw["object_types"]}
        self.link_types = {lk["api_name"]: lk for lk in self.raw["link_types"]}
        self.action_types = {a["api_name"]: a for a in self.raw["action_types"]}
        self.functions = {f["api_name"]: f for f in self.raw["functions"]}

    def properties(self, object_type: str) -> Dict[str, Dict[str, Any]]:
        """Property api_name -> property dict for an object type."""
        return {p["api_name"]: p for p in self.object_types[object_type]["properties"]}

    def links_from(self, object_type: str) -> Dict[str, Dict[str, Any]]:
        """Link name -> {link, direction ('forward' or 'reverse'), to} for links leaving a type."""
        out: Dict[str, Dict[str, Any]] = {}
        for lk in self.link_types.values():
            if lk["source"] == object_type:
                out[lk["source_link_name"]] = {"link": lk, "direction": "forward", "to": lk["target"]}
            if lk["target"] == object_type:
                out[lk["target_link_name"]] = {"link": lk, "direction": "reverse", "to": lk["source"]}
        return out


def _check_fk(errors, name, props, pks, src, fk, tgt):
    """A foreign key on ``src`` must exist, be read-only and match ``tgt``'s key type."""
    if fk not in props[src]:
        errors.append(f"link {name}: foreign key {fk!r} is not a property of {src}")
        return
    ftype, ptype = props[src][fk].get("type"), props[tgt][pks[tgt]].get("type")
    if ftype != ptype:
        errors.append(f"link {name}: {src}.{fk} type {ftype!r} does not match {tgt} key {ptype!r}")
    if props[src][fk].get("editable"):
        errors.append(f"link {name}: foreign key {src}.{fk} must not be editable")


def _validate_objects(raw, errors):
    props: Dict[str, Dict[str, Dict[str, Any]]] = {}
    pks: Dict[str, str] = {}
    for ot in raw["object_types"]:
        name = ot.get("api_name", "<unnamed>")
        if name in props:
            errors.append(f"object type {name!r} defined twice")
        plist = ot.get("properties", [])
        pmap = {p.get("api_name"): p for p in plist}
        if len(pmap) != len(plist):
            errors.append(f"{name}: duplicate property api_name")
        props[name] = pmap
        for p in plist:
            if p.get("type") not in PROPERTY_TYPES:
                errors.append(f"{name}.{p.get('api_name')}: unknown type {p.get('type')!r}")
            if "default" in p and not check_value_type(p["default"], p.get("type", "")):
                errors.append(f"{name}.{p['api_name']}: default does not match type")
        pk = ot.get("primary_key")
        pks[name] = pk
        if pk not in pmap:
            errors.append(f"{name}: primary key {pk!r} is not a property")
            pmap.setdefault(pk, {"type": None})
        elif pmap[pk].get("nullable", True) or pmap[pk].get("editable"):
            errors.append(f"{name}: primary key {pk!r} must be non-nullable and not editable")
        if ot.get("title_property") not in pmap:
            errors.append(f"{name}: title property {ot.get('title_property')!r} is not a property")
    return props, pks


def _validate_links(raw, props, pks, errors):
    link_names: Dict[str, set] = {name: set() for name in props}
    for lk in raw["link_types"]:
        name = lk.get("api_name", "<unnamed>")
        src, tgt = lk.get("source"), lk.get("target")
        if src not in props or tgt not in props:
            errors.append(f"link {name}: endpoint {src!r} -> {tgt!r} is not an object type")
            continue
        card = lk.get("cardinality")
        if card not in CARDINALITIES:
            errors.append(f"link {name}: unknown cardinality {card!r}")
        elif card in FK_CARDINALITIES:
            _check_fk(errors, name, props, pks, src, lk.get("foreign_key"), tgt)
        elif lk.get("join_rule") not in JOIN_RULES:
            errors.append(f"link {name}: unknown join_rule {lk.get('join_rule')!r}")
        elif lk["join_rule"] == "source_array_contains_target_key":
            arr = props[src].get(lk.get("array_property"), {})
            if arr.get("type") != "string_array":
                errors.append(f"link {name}: array_property must be a string_array on {src}")
        else:
            thr = lk.get("through")
            if thr not in props:
                errors.append(f"link {name}: through type {thr!r} is not an object type")
            else:
                _check_fk(errors, name, props, pks, thr, lk.get("through_source_key"), src)
                _check_fk(errors, name, props, pks, thr, lk.get("through_target_key"), tgt)
                for lp in lk.get("link_properties", []):
                    if lp not in props[thr]:
                        errors.append(f"link {name}: link property {lp!r} is not on {thr}")
                hide = lk.get("hide_when")
                if hide and hide.get("property") not in props[thr]:
                    errors.append(f"link {name}: hide_when property is not on {thr}")
        for side, ot in (("source_link_name", src), ("target_link_name", tgt)):
            ln = lk.get(side)
            if not ln:
                errors.append(f"link {name}: missing {side}")
            elif ln in link_names[ot] or ln in props[ot]:
                errors.append(f"link {name}: link name {ln!r} clashes on {ot}")
            else:
                link_names[ot].add(ln)


def _validate_actions(raw, props, errors):
    for act in raw["action_types"]:
        name = act.get("api_name", "<unnamed>")
        params = {p.get("api_name"): p for p in act.get("parameters", [])}
        for p in params.values():
            if p.get("type") not in PARAMETER_TYPES:
                errors.append(f"action {name}: parameter {p.get('api_name')!r} has unknown type")
            if p.get("type") == "object_reference" and p.get("object_type") not in props:
                errors.append(f"action {name}: parameter {p['api_name']!r} references unknown type")
            rw = p.get("required_when")
            if rw and rw.get("parameter") not in params:
                errors.append(f"action {name}: required_when refers to unknown parameter")
        for crit in act.get("submission_criteria", []):
            par = params.get(crit.get("parameter"))
            if not par or par.get("type") != "object_reference" or par.get("object_type") not in props:
                errors.append(f"action {name}: criterion must name an object parameter")
                continue
            ot = par["object_type"]
            prop = props[ot].get(crit.get("property"))
            if prop is None:
                errors.append(f"action {name}: criterion property {crit.get('property')!r} not on {ot}")
            elif crit.get("operator") not in OPERATORS:
                errors.append(f"action {name}: unknown operator {crit.get('operator')!r}")
            elif not check_value_type(crit.get("value"), prop["type"]):
                errors.append(f"action {name}: criterion value does not match {ot}.{prop['api_name']}")
            if not crit.get("failure_message"):
                errors.append(f"action {name}: criterion needs a failure_message")
        for edit in act.get("edits", []):
            par = params.get(edit.get("object_parameter"))
            if not par or par.get("type") != "object_reference" or par.get("object_type") not in props:
                errors.append(f"action {name}: edit must target an object parameter")
                continue
            ot = par["object_type"]
            for prop_name, value in edit.get("set", {}).items():
                prop = props[ot].get(prop_name)
                if prop is None:
                    errors.append(f"action {name}: edits unknown property {ot}.{prop_name}")
                    continue
                if not prop.get("editable"):
                    errors.append(f"action {name}: {ot}.{prop_name} is not editable")
                if isinstance(value, str) and value.startswith("$"):
                    if value[1:] not in params:
                        errors.append(f"action {name}: {value} is not a parameter")
                elif not check_value_type(value, prop["type"]):
                    errors.append(f"action {name}: literal for {ot}.{prop_name} has wrong type")
                elif value is None and not prop.get("nullable", True):
                    errors.append(f"action {name}: {ot}.{prop_name} is not nullable")


def validate(raw: Dict[str, Any]) -> List[str]:
    """Return every consistency problem in a raw spec dict (empty if valid)."""
    errors = [f"missing top-level key {k!r}"
              for k in ("ontology", "object_types", "link_types", "action_types", "functions")
              if k not in raw]
    if errors:
        return errors
    props, pks = _validate_objects(raw, errors)
    _validate_links(raw, props, pks, errors)
    _validate_actions(raw, props, errors)
    for fn in raw["functions"]:
        target = fn.get("reuses")
        try:
            resolve_dotted(target or "")
        except (ImportError, AttributeError):
            errors.append(f"function {fn.get('api_name')}: {target!r} does not resolve to existing code")
    return errors


def load_spec(source: Optional[Union[Path, str, Dict[str, Any]]] = None) -> OntologySpec:
    """Load and validate a spec from a path, a parsed dict, or the bundled ``spec.json``.

    Raises:
        SpecError: Listing every problem found.
    """
    if source is None:
        source = SPEC_PATH
    raw = source if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    errors = validate(raw)
    if errors:
        raise SpecError(errors)
    return OntologySpec(raw)
