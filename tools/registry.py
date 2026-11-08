"""
registry.py — one place that knows every tool Jarvis can call.

Decorate a function with @tool and it is automatically:
  * declared to Gemini (name, description, typed parameters, required list),
  * callable by the server (tools.call(name, args)),
  * optionally marked sensitive (needs the user's spoken "confirm").

The parameter types and the required list come from the function signature,
so the declaration can never drift out of sync with the code.
"""

from __future__ import annotations

import inspect
import logging
import types as _pytypes
import typing
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("jarvis.tools")

_TYPE_NAMES = {str: "STRING", int: "INTEGER", float: "NUMBER", bool: "BOOLEAN"}


@dataclass
class Tool:
    name: str
    fn: Callable[..., str]
    description: str
    params: dict[str, str] = field(default_factory=dict)
    enums: dict[str, list[str]] = field(default_factory=dict)
    confirm: Callable[[dict], str | None] | None = None   # sensitive → summary for the user

    def declaration(self) -> dict:
        """Gemini function declaration built from the Python signature."""
        sig = inspect.signature(self.fn)
        hints = typing.get_type_hints(self.fn)
        properties: dict[str, dict] = {}
        required: list[str] = []
        for pname, p in sig.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            schema: dict = {"type": _gemini_type(hints.get(pname, str))}
            if pname in self.params:
                schema["description"] = self.params[pname]
            if pname in self.enums:
                schema["enum"] = list(self.enums[pname])
            properties[pname] = schema
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        decl: dict = {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "OBJECT", "properties": properties},
        }
        if required:
            decl["parameters"]["required"] = required
        return decl


def _gemini_type(hint) -> str:
    """str → STRING, int | None → INTEGER, ... (unknown types default to STRING)."""
    origin = typing.get_origin(hint)
    if origin in (typing.Union, _pytypes.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        hint = args[0] if args else str
    return _TYPE_NAMES.get(hint, "STRING")


TOOLS: dict[str, Tool] = {}


def tool(description: str, *, name: str | None = None, params: dict[str, str] | None = None,
         enums: dict[str, list[str]] | None = None,
         confirm: Callable[[dict], str | None] | None = None):
    """
    Register a function as a Gemini tool.

        @tool("Opens a website.", params={"url": "Full URL or search text"})
        def open_website(url: str) -> str: ...

    confirm: optional fn(args) -> summary. When set, the server asks the user to
    say "confirm" before running the tool (return None to skip asking, e.g. when
    the tool will refuse anyway).
    """
    def decorator(fn):
        tool_name = name or fn.__name__
        unknown = set(params or {}) | set(enums or {})
        unknown -= set(inspect.signature(fn).parameters)
        if unknown:
            raise TypeError(f"@tool {tool_name}: documented params not in signature: {sorted(unknown)}")
        if tool_name in TOOLS:
            raise ValueError(f"Duplicate tool name: {tool_name}")
        TOOLS[tool_name] = Tool(tool_name, fn, description, dict(params or {}),
                                dict(enums or {}), confirm)
        return fn
    return decorator


def declarations() -> list[dict]:
    return [t.declaration() for t in TOOLS.values()]


def clean_args(fn: Callable, args: dict) -> dict:
    """Drop arguments the function doesn't accept (models sometimes invent extras)."""
    accepted = inspect.signature(fn).parameters
    if any(p.kind == p.VAR_KEYWORD for p in accepted.values()):
        return dict(args)
    extra = set(args) - set(accepted)
    if extra:
        log.debug(f"[TOOLS] Ignoring unexpected args for {getattr(fn, '__name__', fn)}: {sorted(extra)}")
    return {k: v for k, v in args.items() if k in accepted}
