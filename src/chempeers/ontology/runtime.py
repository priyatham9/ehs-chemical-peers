"""In-memory object store: typed objects, link traversal, object sets and actions.

It plays the part of Foundry's object storage plus the Actions service:

* objects are typed, keyed and checked against the spec when loaded;
* links resolve from a foreign key, from an array property, or through a join
  object whose properties travel with the link (the RMP to OSHA match), and
  can be traversed in either direction from one object or a whole set;
* the only way to change an object after loading is :meth:`ObjectStore.apply`,
  which checks parameters and submission criteria, edits only properties the
  spec marks editable, and appends who, when, why, before and after to an
  append-only action log.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional

from .spec import FK_CARDINALITIES, OntologySpec, load_spec


class ObjectValidationError(ValueError):
    """Raised when loaded data does not fit its object type."""


class ActionRejected(ValueError):
    """Raised when an action fails validation; ``errors`` lists every reason."""

    def __init__(self, action: str, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__(f"{action} rejected: " + "; ".join(self.errors))


@dataclass(frozen=True)
class OntologyObject:
    """A read-only view of one object."""

    object_type: str
    primary_key: Any
    title: Any
    properties: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.properties[name]


@dataclass
class ActionLogEntry:
    """One applied action, as recorded in the action log."""

    action_id: str
    action_type: str
    actor: str
    timestamp: str
    parameters: Dict[str, Any]
    edits: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return copy.deepcopy({"action_id": self.action_id, "action_type": self.action_type,
                              "actor": self.actor, "timestamp": self.timestamp,
                              "parameters": self.parameters, "edits": self.edits})


def coerce_value(value: Any, type_name: str) -> Any:
    """Convert a JSON value to the Python type a property declares.

    Raises:
        ObjectValidationError: If the value cannot represent that type.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if type_name == "string":
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if type_name == "string_array":
        if not isinstance(value, (list, tuple)):
            raise ObjectValidationError(f"{value!r} is not a list")
        return tuple(str(v) for v in value)
    if type_name == "boolean":
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        raise ObjectValidationError(f"{value!r} is not a boolean")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObjectValidationError(f"{value!r} is not a number")
    if type_name == "integer":
        if isinstance(value, float) and not value.is_integer():
            raise ObjectValidationError(f"{value!r} is not an integer")
        return int(value)
    return float(value)


class ObjectSet:
    """An ordered, immutable set of objects of one type (Foundry Object Set)."""

    def __init__(self, store: "ObjectStore", object_type: str, keys: Iterable[Any]) -> None:
        self._store = store
        self.object_type = object_type
        self._keys = list(dict.fromkeys(keys))

    def __iter__(self) -> Iterator[OntologyObject]:
        for k in self._keys:
            yield self._store.get(self.object_type, k)

    def __len__(self) -> int:
        return len(self._keys)

    def count(self) -> int:
        return len(self._keys)

    def primary_keys(self) -> List[Any]:
        return list(self._keys)

    def where(self, **equals: Any) -> "ObjectSet":
        """Filter to objects whose properties equal every given value."""
        props = self._store.spec.properties(self.object_type)
        for name in equals:
            if name not in props:
                raise KeyError(f"{self.object_type} has no property {name!r}")
        rows = self._store._rows[self.object_type]
        return ObjectSet(self._store, self.object_type,
                         [k for k in self._keys if all(rows[k][n] == v for n, v in equals.items())])

    def filter(self, predicate: Callable[[OntologyObject], bool]) -> "ObjectSet":
        """Filter with an arbitrary predicate on each object."""
        return ObjectSet(self._store, self.object_type, [o.primary_key for o in self if predicate(o)])

    def search_around(self, link_name: str) -> "ObjectSet":
        """Follow a link from every object in the set (Foundry Search Around)."""
        hop = self._store._hop(self.object_type, link_name)
        keys: List[Any] = []
        for k in self._keys:
            keys.extend(self._store._traverse_keys(self.object_type, k, link_name))
        return ObjectSet(self._store, hop["to"], keys)

    def one(self) -> Optional[OntologyObject]:
        """The single object in the set, ``None`` if empty; ValueError if more than one."""
        if len(self._keys) > 1:
            raise ValueError(f"expected at most one {self.object_type}, got {len(self._keys)}")
        return self._store.get(self.object_type, self._keys[0]) if self._keys else None

    def to_records(self) -> List[Dict[str, Any]]:
        """Property dicts, one per object, in set order (arrays as lists)."""
        rows = self._store._rows[self.object_type]
        return [{k: list(v) if isinstance(v, tuple) else v for k, v in rows[key].items()}
                for key in self._keys]


class ObjectStore:
    """Typed objects for every type in a spec, with links and actions.

    Args:
        spec: A validated spec; defaults to the bundled one.
        clock: Zero-argument callable returning an aware ``datetime``, so tests
            can pin action timestamps.
    """

    def __init__(self, spec: Optional[OntologySpec] = None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.spec = spec or load_spec()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._rows: Dict[str, Dict[Any, Dict[str, Any]]] = {t: {} for t in self.spec.object_types}
        self._index: Dict[tuple, Dict[Any, List[Any]]] = {}
        self.action_log: List[ActionLogEntry] = []

    # ------------------------------------------------------------------ load
    def add_objects(self, object_type: str, records: Iterable[Mapping[str, Any]]) -> int:
        """Validate and add objects; missing properties take their spec default.

        Raises:
            ObjectValidationError: On a type mismatch, a null in a non-nullable
                property, or a duplicate primary key.
        """
        props = self.spec.properties(object_type)
        pk_name = self.spec.object_types[object_type]["primary_key"]
        table = self._rows[object_type]
        added = 0
        for rec in records:
            row: Dict[str, Any] = {}
            for name, prop in props.items():
                try:
                    value = coerce_value(rec.get(name, prop.get("default")), prop["type"])
                except ObjectValidationError as exc:
                    raise ObjectValidationError(f"{object_type}.{name}: {exc}") from None
                if value is None and not prop.get("nullable", True):
                    raise ObjectValidationError(
                        f"{object_type}.{name} is not nullable (key {rec.get(pk_name)!r})")
                row[name] = value
            if row[pk_name] in table:
                raise ObjectValidationError(f"duplicate {object_type} primary key {row[pk_name]!r}")
            table[row[pk_name]] = row
            added += 1
        self._index.clear()
        return added

    # ------------------------------------------------------------------ read
    def get(self, object_type: str, primary_key: Any) -> OntologyObject:
        """Return one object; KeyError if it does not exist."""
        row = self._rows[object_type][primary_key]
        title = row[self.spec.object_types[object_type]["title_property"]]
        return OntologyObject(object_type, primary_key, title, MappingProxyType(dict(row)))

    def objects(self, object_type: str) -> ObjectSet:
        """All objects of a type."""
        return ObjectSet(self, object_type, self._rows[object_type].keys())

    def linked(self, obj: OntologyObject, link_name: str) -> ObjectSet:
        """Objects reached from ``obj`` along ``link_name``."""
        hop = self._hop(obj.object_type, link_name)
        return ObjectSet(self, hop["to"], self._traverse_keys(obj.object_type, obj.primary_key, link_name))

    def link_rows(self, obj: OntologyObject, link_name: str,
                  include_hidden: bool = False) -> List[Dict[str, Any]]:
        """For a link backed by a join object: each linked object with its link properties."""
        hop = self._hop(obj.object_type, link_name)
        lk = hop["link"]
        if lk.get("join_rule") != "through_object":
            raise TypeError(f"link {lk['api_name']!r} carries no link properties")
        out = []
        for tkey in self._through_keys(lk, hop["direction"], obj.primary_key, include_hidden):
            trow = self._rows[lk["through"]][tkey]
            far = trow[lk["through_target_key" if hop["direction"] == "forward" else "through_source_key"]]
            if far in self._rows[hop["to"]]:
                out.append({"object": self.get(hop["to"], far), "via": tkey,
                            "link_properties": {p: trow[p] for p in lk.get("link_properties", [])}})
        return out

    def _hop(self, object_type: str, link_name: str) -> Dict[str, Any]:
        hops = self.spec.links_from(object_type)
        if link_name not in hops:
            raise KeyError(f"{object_type} has no link {link_name!r}; has {sorted(hops)}")
        return hops[link_name]

    def _build_index(self, name: tuple, table: str, key_of: Callable[[Dict[str, Any]], Iterable[Any]]):
        idx = self._index.get(name)
        if idx is None:
            idx = {}
            for pk, row in self._rows[table].items():
                for k in key_of(row):
                    idx.setdefault(k, []).append(pk)
            self._index[name] = idx
        return idx

    def _hidden(self, lk: Dict[str, Any], through_row: Dict[str, Any]) -> bool:
        hide = lk.get("hide_when")
        return bool(hide) and through_row[hide["property"]] == hide["equals"]

    def _through_keys(self, lk, direction, key, include_hidden=False) -> List[Any]:
        col = lk["through_source_key" if direction == "forward" else "through_target_key"]
        idx = self._build_index((lk["api_name"], direction), lk["through"], lambda r: [r[col]])
        rows = self._rows[lk["through"]]
        return [t for t in idx.get(key, []) if include_hidden or not self._hidden(lk, rows[t])]

    def _traverse_keys(self, object_type: str, key: Any, link_name: str) -> List[Any]:
        hop = self._hop(object_type, link_name)
        lk, fwd = hop["link"], hop["direction"] == "forward"
        row = self._rows[object_type][key]
        targets = self._rows[hop["to"]]
        if lk["cardinality"] in FK_CARDINALITIES:
            fk = lk["foreign_key"]
            if fwd:
                return [row[fk]] if row[fk] in targets else []
            return self._build_index((lk["api_name"], "rev"), lk["source"], lambda r: [r[fk]]).get(key, [])
        if lk["join_rule"] == "source_array_contains_target_key":
            arr = lk["array_property"]
            if fwd:
                return [k for k in dict.fromkeys(row[arr]) if k in targets]
            return self._build_index((lk["api_name"], "rev"), lk["source"],
                                     lambda r: dict.fromkeys(r[arr])).get(key, [])
        far = lk["through_target_key" if fwd else "through_source_key"]
        trows = self._rows[lk["through"]]
        return [trows[t][far] for t in self._through_keys(lk, hop["direction"], key)
                if trows[t][far] in targets]

    def link_pairs(self, link_api_name: str) -> List[tuple]:
        """All traversable (source_pk, target_pk) pairs of a link type."""
        lk = self.spec.link_types[link_api_name]
        name = lk["source_link_name"]
        return [(s, t) for s in self._rows[lk["source"]] for t in self._traverse_keys(lk["source"], s, name)]

    def integrity_report(self) -> Dict[str, Dict[str, int]]:
        """Per link: resolved, null and dangling keys (and one-to-one duplicates, hidden joins).

        A dangling key is a non-null key with no target object.
        """
        report: Dict[str, Dict[str, int]] = {}
        for name, lk in self.spec.link_types.items():
            src_rows = self._rows[lk["source"]]
            if lk["cardinality"] in FK_CARDINALITIES:
                targets = self._rows[lk["target"]]
                c = {"resolved": 0, "null": 0, "dangling": 0}
                seen: Dict[Any, int] = {}
                for row in src_rows.values():
                    fk = row[lk["foreign_key"]]
                    c["null" if fk is None else "resolved" if fk in targets else "dangling"] += 1
                    if fk is not None:
                        seen[fk] = seen.get(fk, 0) + 1
                if lk["cardinality"] == "one_to_one":
                    c["duplicate_targets"] = sum(1 for v in seen.values() if v > 1)
            elif lk["join_rule"] == "source_array_contains_target_key":
                targets = self._rows[lk["target"]]
                vals = [v for row in src_rows.values() for v in dict.fromkeys(row[lk["array_property"]])]
                c = {"resolved": sum(v in targets for v in vals), "dangling": sum(v not in targets for v in vals)}
            else:
                trows = self._rows[lk["through"]].values()
                ok = [r for r in trows if r[lk["through_source_key"]] in src_rows
                      and r[lk["through_target_key"]] in self._rows[lk["target"]]]
                c = {"resolved": sum(not self._hidden(lk, r) for r in ok),
                     "hidden": sum(self._hidden(lk, r) for r in ok), "dangling": len(trows) - len(ok)}
            report[name] = c
        return report

    # --------------------------------------------------------------- actions
    def apply(self, action_type: str, parameters: Mapping[str, Any], actor: str) -> ActionLogEntry:
        """Validate and apply an action, then log it.

        Object references are passed as primary keys or :class:`OntologyObject`.

        Raises:
            ActionRejected: With every reason; nothing is edited or logged.
            KeyError: If the action type does not exist.
        """
        act = self.spec.action_types[action_type]
        params = {p["api_name"]: p for p in act["parameters"]}
        errors: List[str] = []
        if not isinstance(actor, str) or not actor.strip():
            errors.append("actor is required")
        unknown = set(parameters) - set(params)
        if unknown:
            errors.append(f"unknown parameters {sorted(unknown)}")

        values: Dict[str, Any] = {}
        targets: Dict[str, Any] = {}
        for name, p in params.items():
            v = parameters.get(name)
            if isinstance(v, OntologyObject):
                v = v.primary_key
            if isinstance(v, str) and not v.strip() and p["type"] == "string":
                v = None
            values[name] = v
            rw = p.get("required_when")
            required = p.get("required") or (rw and parameters.get(rw["parameter"]) == rw["equals"])
            if v is None:
                if required:
                    errors.append(f"{name} is required")
                continue
            if p["type"] == "object_reference":
                if v not in self._rows[p["object_type"]]:
                    errors.append(f"{name}: no {p['object_type']} with key {v!r}")
                else:
                    targets[name] = v
                continue
            if p["type"] == "string" and not isinstance(v, str):
                errors.append(f"{name} must be a string")
                continue
            if "allowed_values" in p and v not in p["allowed_values"]:
                errors.append(f"{name} must be one of {p['allowed_values']}")
            if isinstance(v, str):
                if len(v.strip()) < p.get("min_length", 0):
                    errors.append(f"{name} must be at least {p['min_length']} characters")
                if "max_length" in p and len(v) > p["max_length"]:
                    errors.append(f"{name} must be at most {p['max_length']} characters")

        if not errors:
            for crit in act.get("submission_criteria", []):
                ot = params[crit["parameter"]]["object_type"]
                current = self._rows[ot][targets[crit["parameter"]]][crit["property"]]
                ok = {"equals": current == crit.get("value"),
                      "not_equals": current != crit.get("value"),
                      "is_null": current is None,
                      "not_null": current is not None}[crit["operator"]]
                if not ok:
                    errors.append(crit["failure_message"])
        if errors:
            raise ActionRejected(action_type, errors)

        edits: List[Dict[str, Any]] = []
        for edit in act.get("edits", []):
            pname = edit["object_parameter"]
            ot = params[pname]["object_type"]
            row = self._rows[ot][targets[pname]]
            for prop, spec_value in edit["set"].items():
                new = values[spec_value[1:]] if isinstance(spec_value, str) and spec_value.startswith("$") else spec_value
                edits.append({"object_type": ot, "primary_key": targets[pname], "property": prop,
                              "before": row[prop], "after": new})
                row[prop] = new
        entry = ActionLogEntry(
            action_id=f"act-{len(self.action_log) + 1:06d}", action_type=action_type, actor=actor,
            timestamp=self.clock().astimezone(timezone.utc).isoformat(),
            parameters=dict(values), edits=edits)
        self.action_log.append(entry)
        return entry

    def edit_history(self, object_type: str, primary_key: Any) -> List[Dict[str, Any]]:
        """Every logged edit to one object, oldest first, with who and when."""
        return [{"action_id": e.action_id, "action_type": e.action_type, "actor": e.actor,
                 "timestamp": e.timestamp, **ed}
                for e in self.action_log for ed in e.edits
                if ed["object_type"] == object_type and ed["primary_key"] == primary_key]
