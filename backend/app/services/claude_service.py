import asyncio
import json
from pathlib import Path

from app.config import settings


async def call_claude(
    prompt: str,
    context_files: list[Path] | None = None,
    system_prompt: str | None = None,
    json_schema: dict | None = None,
) -> dict | str:
    """Call Claude CLI via subprocess in print mode."""
    cmd = [
        "claude",
        "-p",
        "--model", settings.claude_model,
        "--output-format", "json",
    ]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    # Build prompt with file contents inlined
    full_prompt = prompt
    if context_files:
        for f in context_files:
            if f.exists() and f.stat().st_size < 500_000:
                content = f.read_text(errors="ignore")
                full_prompt += f"\n\n--- FILE: {f.name} ---\n{content}\n"

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate(input=full_prompt.encode())

    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI failed (exit {proc.returncode}): {stderr.decode()}")

    result_text = stdout.decode()
    try:
        parsed = json.loads(result_text)
        # Claude CLI JSON output wraps result in a structure
        if isinstance(parsed, dict) and "result" in parsed:
            inner = parsed["result"]
            # Try to parse inner as JSON if it's a string
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    return inner
            return inner
        return parsed
    except json.JSONDecodeError:
        return result_text
