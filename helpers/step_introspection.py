import ast
from typing import List, Dict


def get_step_methods_with_calls(filepath: str, classname: str = "CLIP_OT_track_nr1") -> List[Dict[str, object]]:
    """Return step methods of a class with docstring and called functions."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    result: List[Dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == classname:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("step_"):
                    doc = ast.get_docstring(item) or "Keine Beschreibung vorhanden"
                    first_line = doc.splitlines()[0] if doc else ""
                    calls = []
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Call):
                            func = sub.func
                            if isinstance(func, ast.Name):
                                calls.append(func.id)
                            elif isinstance(func, ast.Attribute):
                                calls.append(func.attr)
                    result.append({
                        "name": item.name,
                        "doc": first_line,
                        "calls": sorted(set(calls)),
                    })
    return result
