import ast
import pathlib
import textwrap

# Extract _extract_sections definition from app/handlers/chats.py without importing the module
source = pathlib.Path('app/handlers/chats.py').read_text()
module = ast.parse(source)
func_src = None
for node in module.body:
    if isinstance(node, ast.FunctionDef) and node.name == '_extract_sections':
        lines = source.splitlines()[node.lineno-1:node.end_lineno]
        func_src = "\n".join(lines)
        break
assert func_src, "_extract_sections function not found"
exec(textwrap.dedent(func_src), globals())


def test_extract_sections_stream():
    buf = ""
    pieces = []
    chunks = ["/s/Hello", " world/n//s/Second", " line/n/Trailing"]
    for ch in chunks:
        buf += ch
        parts, buf = _extract_sections(buf)
        pieces.extend(parts)
    # simulate final flush
    parts, buf = _extract_sections(buf)
    pieces.extend(parts)
    if buf.strip():
        pieces.append(buf.strip())
        buf = ""
    assert pieces == ["Hello world", "Second line", "Trailing"]
    assert buf == ""


def test_extract_sections_partial():
    parts, buf = _extract_sections("/s/Part")
    assert parts == []
    assert buf == "/s/Part"


def test_extract_sections_newline_fallback():
    buf = ""
    pieces = []
    chunks = ["Hello ", "world\nSecond ", "line\nThird"]
    for ch in chunks:
        buf += ch
        parts, buf = _extract_sections(buf)
        pieces.extend(parts)
    assert pieces == ["Hello world", "Second line"]
    # final flush should deliver the rest
    parts, buf = _extract_sections(buf)
    pieces.extend(parts)
    if buf.strip():
        pieces.append(buf.strip())
        buf = ""
    assert pieces == ["Hello world", "Second line", "Third"]
    assert buf == ""


