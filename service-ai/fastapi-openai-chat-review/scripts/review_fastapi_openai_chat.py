#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    message: str


def read_tree(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        print(f"[WARN] Could not parse {path}: {exc}", file=sys.stderr)
        return None


def unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def class_defs(tree: ast.AST) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def assignments(cls: ast.ClassDef) -> dict[str, ast.AnnAssign]:
    fields: dict[str, ast.AnnAssign] = {}
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields[node.target.id] = node
    return fields


def literal_values(text: str) -> set[str]:
    values: set[str] = set()
    try:
        expr = ast.parse(text, mode="eval").body
    except SyntaxError:
        return values
    for node in ast.walk(expr):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.add(node.value)
    return values


def has_min_length(field: ast.AnnAssign) -> bool:
    value = field.value
    if not isinstance(value, ast.Call):
        return False
    for kw in value.keywords:
        if kw.arg == "min_length":
            return True
    return False


def find_line(path: Path, needle: str) -> int:
    try:
        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line:
                return idx
    except OSError:
        pass
    return 1


def check_chat_schema(root: Path, findings: list[Finding]) -> None:
    schema_path = root / "app" / "schemas" / "chat.py"
    if not schema_path.exists():
        findings.append(Finding("HIGH", root, 1, "No app/schemas/chat.py found; locate the chat request models manually."))
        return

    tree = read_tree(schema_path)
    if tree is None:
        return

    classes = class_defs(tree)
    chat_message = classes.get("ChatMessage")
    chat_request = classes.get("ChatRequest")

    if chat_message is None:
        findings.append(Finding("HIGH", schema_path, 1, "ChatMessage model is missing."))
    else:
        fields = assignments(chat_message)
        role = fields.get("role")
        content = fields.get("content")
        if role is None:
            findings.append(Finding("HIGH", schema_path, chat_message.lineno, "ChatMessage lacks a role field."))
        else:
            role_annotation = unparse(role.annotation)
            if "Literal" not in role_annotation and "Enum" not in role_annotation:
                findings.append(Finding("HIGH", schema_path, role.lineno, "ChatMessage.role is not constrained with Literal or an enum."))
            roles = literal_values(role_annotation)
            required = {"system", "user", "assistant", "tool"}
            missing = sorted(required - roles)
            if missing:
                findings.append(Finding("MEDIUM", schema_path, role.lineno, f"ChatMessage.role is missing baseline roles: {', '.join(missing)}."))
            if "developer" not in roles:
                findings.append(Finding("LOW", schema_path, role.lineno, "Consider developer role only if the route promises modern OpenAI parity."))
        if content is None:
            findings.append(Finding("HIGH", schema_path, chat_message.lineno, "ChatMessage lacks a content field."))
        elif unparse(content.annotation) != "str":
            findings.append(Finding("MEDIUM", schema_path, content.lineno, f"ChatMessage.content is {unparse(content.annotation)!r}; confirm this matches text-only or multimodal payloads."))

    if chat_request is None:
        findings.append(Finding("HIGH", schema_path, 1, "ChatRequest model is missing."))
    else:
        fields = assignments(chat_request)
        messages = fields.get("messages")
        if messages is None:
            findings.append(Finding("HIGH", schema_path, chat_request.lineno, "ChatRequest lacks required messages field."))
        else:
            annotation = unparse(messages.annotation)
            if "ChatMessage" not in annotation:
                findings.append(Finding("HIGH", schema_path, messages.lineno, f"ChatRequest.messages is {annotation!r}, not a list of ChatMessage."))
            if "list" not in annotation and "List" not in annotation:
                findings.append(Finding("HIGH", schema_path, messages.lineno, "ChatRequest.messages is not typed as a list."))
            if not has_min_length(messages):
                findings.append(Finding("MEDIUM", schema_path, messages.lineno, "ChatRequest.messages does not declare Field(..., min_length=1)."))
        for field_name in ("model", "stream"):
            if field_name not in fields:
                findings.append(Finding("MEDIUM", schema_path, chat_request.lineno, f"ChatRequest lacks {field_name!r}; verify this is intentional for OpenAI-style payloads."))


def route_decorators(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> list[str]:
    return [unparse(decorator) for decorator in fn.decorator_list]


def check_routes(root: Path, findings: list[Finding]) -> None:
    routes_dir = root / "app" / "api" / "routes"
    if not routes_dir.exists():
        findings.append(Finding("HIGH", root, 1, "No app/api/routes directory found."))
        return

    chat_request_routes = 0
    websocket_routes = 0

    for path in sorted(routes_dir.glob("*.py")):
        tree = read_tree(path)
        if tree is None:
            continue
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                decorators = route_decorators(node)
                is_route = any("router." in item for item in decorators)
                if not is_route:
                    continue
                annotations = [unparse(arg.annotation) for arg in node.args.args]
                if any(annotation == "ChatRequest" for annotation in annotations):
                    chat_request_routes += 1
                    decorator_text = "\n".join(decorators)
                    segment = ast.get_source_segment(source, node) or ""
                    if "router.post" in decorator_text and "response_model=" not in decorator_text and "StreamingResponse" not in segment:
                        findings.append(Finding("MEDIUM", path, node.lineno, "Chat HTTP POST route has no response_model; check chatbot response envelope validation."))
                if any(".websocket" in item for item in decorators):
                    websocket_routes += 1
                    segment = ast.get_source_segment(source, node) or ""
                    if "ChatRequest(" not in segment and "ChatRequest.model_validate" not in segment:
                        findings.append(Finding("HIGH", path, node.lineno, "WebSocket route does not instantiate ChatRequest for payload validation."))
                    if "payload.get(\"content\")" in segment or "payload.get(\"message\")" in segment or "str(payload)" in segment:
                        findings.append(Finding("MEDIUM", path, node.lineno, "WebSocket route accepts non-standard content/message fallback; ensure tests cover this compatibility shim."))

        text = source
        if "payload.get(\"messages\", [])" in text and "ChatRequest" not in text:
            findings.append(Finding("HIGH", path, find_line(path, "payload.get(\"messages\", [])"), "Route reads messages manually without ChatRequest validation."))

    if chat_request_routes == 0:
        findings.append(Finding("HIGH", routes_dir, 1, "No HTTP route accepts ChatRequest directly."))
    if websocket_routes and chat_request_routes == 0:
        findings.append(Finding("HIGH", routes_dir, 1, "WebSocket chat exists without an HTTP ChatRequest route to share the schema."))


def check_tests(root: Path, findings: list[Finding]) -> None:
    tests_dir = root / "tests"
    if not tests_dir.exists():
        findings.append(Finding("MEDIUM", root, 1, "No tests directory found for chat contract coverage."))
        return
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in tests_dir.rglob("test_*.py"))
    expected_terms = {
        "valid chat payload": "\"messages\"",
        "empty messages rejection": "messages\": []",
        "invalid role rejection": "invalid-role",
        "WebSocket validation": "websocket_connect",
    }
    for label, needle in expected_terms.items():
        if needle not in text:
            findings.append(Finding("LOW", tests_dir, 1, f"Missing obvious test signal for {label}."))


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    findings: list[Finding] = []

    check_chat_schema(root, findings)
    check_routes(root, findings)
    check_tests(root, findings)

    print("# FastAPI OpenAI Chat Review")
    print(f"Service root: {root}")
    if not findings:
        print("\nNo static contract findings detected. Still review route behavior and negative tests manually.")
        return 0

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for finding in sorted(findings, key=lambda item: (severity_order.get(item.severity, 9), str(item.path), item.line)):
        rel = finding.path
        try:
            rel = finding.path.relative_to(root)
        except ValueError:
            pass
        print(f"\n- [{finding.severity}] {rel}:{finding.line}")
        print(f"  {finding.message}")

    return 1 if any(item.severity == "HIGH" for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
