import ast


def extract_step_sequence_from_cycle(filepath: str):
    """Return ordered FSM keys from return statements in cycle file."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    sequence = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
            val = node.value.value
            if isinstance(val, str) and val.isupper():
                sequence.append(val)

    seen = set()
    result = []
    for val in sequence:
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result
