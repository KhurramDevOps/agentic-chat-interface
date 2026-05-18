"""
tests/unit/test_tools.py
─────────────────────────
Unit tests for all agent tools:
  - calculate   — safe AST math evaluator
  - run_python  — sandboxed subprocess executor
  - fetch_url   — HTML-stripping URL fetcher + markdown hallucination cleaner
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc(expr: str) -> str:
    from app.agents.domain_agents import _calculate_impl
    return _calculate_impl(expr)


def _run(code: str) -> str:
    from app.agents.domain_agents import _run_python_impl
    return _run_python_impl(code)


async def _fetch(url: str, html: str = "Hello") -> str:
    from app.agents.domain_agents import _fetch_url_impl

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.agents.domain_agents.httpx.AsyncClient", return_value=mock_client):
        return await _fetch_url_impl(url)


# ── calculate ─────────────────────────────────────────────────────────────────

class TestCalculate:

    def test_addition(self):
        assert _calc("1 + 1") == "2"

    def test_subtraction(self):
        assert _calc("10 - 3") == "7"

    def test_multiplication(self):
        assert _calc("6 * 7") == "42"

    def test_integer_division(self):
        assert _calc("10 / 2") == "5"

    def test_float_division(self):
        result = _calc("10 / 3")
        assert result.startswith("3.333")

    def test_floor_division(self):
        assert _calc("10 // 3") == "3"

    def test_modulo(self):
        assert _calc("10 % 3") == "1"

    def test_power(self):
        assert _calc("2 ** 8") == "256"

    def test_unary_negation(self):
        assert _calc("-5 + 10") == "5"

    def test_parentheses(self):
        assert _calc("(2 + 3) * 4") == "20"

    def test_nested_parentheses(self):
        assert _calc("((2 + 3) * (4 - 1)) / 5") == "3"

    def test_division_by_zero(self):
        result = _calc("1 / 0")
        assert "zero" in result.lower()

    def test_rejects_import(self):
        result = _calc("__import__('os')")
        assert "Error" in result

    def test_rejects_string_literal(self):
        result = _calc("'hello'")
        assert "Error" in result

    def test_rejects_function_call(self):
        result = _calc("abs(-1)")
        assert "Error" in result

    def test_large_number(self):
        result = _calc("999999 * 999999")
        assert "999998000001" in result

    def test_float_input(self):
        result = _calc("3.14 * 2")
        assert "6.28" in result


# ── run_python ────────────────────────────────────────────────────────────────

class TestRunPython:

    def test_simple_print(self):
        assert "hello" in _run("print('hello')")

    def test_arithmetic_output(self):
        assert "55" in _run("print(sum(range(1, 11)))")

    def test_multiline_script(self):
        code = "x = 10\ny = 20\nprint(x + y)"
        assert "30" in _run(code)

    def test_list_comprehension(self):
        code = "print([x**2 for x in range(5)])"
        result = _run(code)
        assert "16" in result  # 4^2

    def test_no_output_script(self):
        result = _run("x = 1 + 1")
        assert "no output" in result.lower() or result == "(script ran successfully with no output)"

    def test_blocks_os_import(self):
        result = _run("import os\nprint(os.getcwd())")
        assert "not allowed" in result.lower() or "Error" in result

    def test_blocks_sys_import(self):
        result = _run("import sys\nprint(sys.version)")
        assert "not allowed" in result.lower() or "Error" in result

    def test_blocks_subprocess(self):
        result = _run("import subprocess\nsubprocess.run(['ls'])")
        assert "not allowed" in result.lower() or "Error" in result

    def test_blocks_open(self):
        result = _run("open('/etc/passwd').read()")
        assert "not allowed" in result.lower() or "Error" in result

    def test_blocks_eval(self):
        result = _run("eval('1+1')")
        assert "not allowed" in result.lower() or "Error" in result

    def test_timeout_enforcement(self):
        result = _run("while True: pass")
        assert "timeout" in result.lower()

    def test_syntax_error_reported(self):
        result = _run("def broken(:\n    pass")
        assert "error" in result.lower()

    def test_runtime_error_reported(self):
        result = _run("x = 1 / 0")
        assert "error" in result.lower() or "ZeroDivisionError" in result


# ── fetch_url ─────────────────────────────────────────────────────────────────

class TestFetchUrl:

    @pytest.mark.asyncio
    async def test_fetches_allowlisted_url(self):
        result = await _fetch("https://api.tavily.com/search", "Title\nBody text")
        assert "Title" in result
        assert "Body text" in result

    @pytest.mark.asyncio
    async def test_rejects_ftp_url(self):
        from app.agents.domain_agents import _fetch_url_impl
        result = await _fetch_url_impl("ftp://example.com")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_rejects_empty_url(self):
        from app.agents.domain_agents import _fetch_url_impl
        result = await _fetch_url_impl("   ")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_rejects_non_allowlisted_url(self):
        from app.agents.domain_agents import _fetch_url_impl
        result = await _fetch_url_impl("https://example.com")
        assert "allowlist" in result

    @pytest.mark.asyncio
    async def test_truncates_long_content(self):
        long_text = "x" * 20000
        result = await _fetch("https://api.tavily.com/search", long_text)
        assert len(result) == 3000

    @pytest.mark.asyncio
    async def test_http_error_returns_message(self):
        import httpx
        from app.agents.domain_agents import _fetch_url_impl

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        http_err = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=http_err)

        with patch("app.agents.domain_agents.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_url_impl("https://api.tavily.com/missing")

        assert "Error fetching URL" in result
        assert "Not Found" in result
