"""M9-B live text chat + tool calling smoke — full chain real.

End-to-end test of the text-channel ReAct loop:
  User text → agent.run() → LLM emits tool_call → tool executor
  runs (policy-gated file_read) → result feeds back to LLM →
  LLM emits final answer.

Unlike M9-A (voice), this exercises the *tool calling* path
end-to-end. The exit criteria: LLM's final answer contains actual
content from the file it asked to read (proving the executor ran
and the LLM used its result), not a generic fallback.

Default query: "睇下 gundam-halo backend README.md 嘅第一行係咩"
(written Cantonese; the LLM should call file_read with the README
path, the executor returns the content, the LLM paraphrases the
first line).

Output: /tmp/m9b_<ts>/ — transcript, tool-call log, final answer,
latency breakdown.

Run:
    cd backend
    export MINIMAX_API_KEY=...
    .venv/bin/python scripts/m9b_text_chat_tools.py

The script instantiates the real NativeReActAgent with the real
MiniMax engine and the real default tool set. No mocks. No
TestClient — this is a direct agent.run() call, not a network round
trip.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Make sure backend root is on sys.path so `app.*` imports work
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Default query: ask for the first line of the gundam-halo README.
# The LLM should call file_read on the README; the executor should
# return the file's content; the LLM should cite the first line.
DEFAULT_QUERY = os.environ.get(
    "M9B_QUERY",
    "用 file_read tool 讀 /Users/kencheng/workspace/working/gundam-halo/backend/README.md 然後答我第一行係咩。",
)
DEFAULT_TARGET = (
    "/Users/kencheng/workspace/working/gundam-halo/backend/README.md"
)


async def main() -> int:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 1

    out_dir = Path(f"/tmp/m9b_{int(time.time())}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir}")

    # 1. Boot config + engine + tools
    from app.core import config as _config_module
    from app.engines.minimax import MiniMaxEngine
    from app.tools.builder import default_tools
    from app.agents.native_react import NativeReActAgent
    from app.core.types import AgentContext, Role, Message

    cfg = _config_module.get_config()
    print(
        f"Config: llm.base_url={cfg.llm.base_url}, "
        f"llm.model={cfg.llm.default_model}"
    )

    engine = MiniMaxEngine(
        api_key=api_key,
        base_url=cfg.llm.base_url,
        model=cfg.llm.default_model,
    )
    tools = default_tools()
    print(f"Tools registered: {len(tools)}")
    for t in tools:
        print(f"  - {t.name}")

    agent = NativeReActAgent(
        engine=engine,
        model=cfg.llm.default_model,
        tools=tools,
        max_turns=6,
    )

    # 2. Build context (no session / no project — just a bare user query)
    ctx = AgentContext(
        session_id=f"m9b-{int(time.time())}",
        user_id="ken",
        user_display_name="Ken",
        project_id=None,
    )

    # 3. Run ReAct loop
    print(f"\nQuery: {DEFAULT_QUERY!r}\n")
    t0 = time.time()
    result = await agent.run(DEFAULT_QUERY, context=ctx)
    wall_ms = int((time.time() - t0) * 1000)

    # 4. Reconstruct the per-turn transcript
    transcript: list[dict] = []
    turn = 0
    tool_call_count = 0
    for m in result.messages:
        if m.role == Role.SYSTEM:
            transcript.append({"role": "system", "content": m.content[:200] + ("..." if len(m.content) > 200 else "")})
        elif m.role == Role.USER:
            transcript.append({"role": "user", "content": m.content})
        elif m.role == Role.ASSISTANT:
            turn += 1
            entry = {
                "role": "assistant",
                "turn": turn,
                "content": m.content,
            }
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for tc in m.tool_calls
                ]
                tool_call_count += len(m.tool_calls)
            transcript.append(entry)
        elif m.role == Role.TOOL:
            content = m.content or ""
            transcript.append({
                "role": "tool",
                "name": m.name,
                "tool_call_id": m.tool_call_id,
                "content_preview": content[:400] + ("..." if len(content) > 400 else ""),
                "content_bytes": len(content),
            })

    # 5. Print transcript
    print("=" * 60)
    print("M9-B TEXT CHAT + TOOL CALLING — TRANSCRIPT")
    print("=" * 60)
    for entry in transcript:
        role = entry["role"]
        if role == "system":
            print(f"\n[SYSTEM] ({len(entry['content'])} chars)")
        elif role == "user":
            print(f"\n[USER] {entry['content']}")
        elif role == "assistant":
            tc = entry.get("tool_calls") or []
            print(f"\n[ASSISTANT turn {entry['turn']}]")
            if entry.get("content"):
                print(f"  content: {entry['content']}")
            for c in tc:
                print(f"  -> tool_call: {c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})")
        elif role == "tool":
            print(f"\n[TOOL {entry['name']}] (id={entry['tool_call_id']})")
            print(f"  {entry['content_bytes']} bytes returned")
            print(f"  preview: {entry['content_preview']}")

    # 6. Final answer + verification
    print()
    print("=" * 60)
    print("M9-B RESULTS")
    print("=" * 60)
    final = result.output or ""
    print(f"  Success:      {result.success}")
    print(f"  Tool calls:   {tool_call_count}")
    print(f"  Wall:         {wall_ms} ms")
    print(f"  Final answer: {final!r}")

    # The critical assertion: did the LLM actually use the file content?
    # We do a soft check — look for any content from the README in the
    # final answer (first non-empty line, or any non-whitespace tokens).
    actual_first_line = ""
    try:
        with open(DEFAULT_TARGET) as f:
            actual_first_line = f.readline().strip()
    except FileNotFoundError:
        print(f"  WARN: target README not found at {DEFAULT_TARGET}")

    used_file_content = False
    if actual_first_line:
        # Heuristic: at least one distinctive token from the first line
        # appears in the LLM's final answer.
        tokens = [t for t in actual_first_line.split() if len(t) > 3]
        for tok in tokens:
            if tok in final:
                used_file_content = True
                break
        # Fallback: substring of the first line directly
        if not used_file_content and actual_first_line[:30] in final:
            used_file_content = True

    print(f"  README first line: {actual_first_line!r}")
    print(f"  LLM used file content? {used_file_content}")

    # 7. Save artefacts
    (out_dir / "transcript.json").write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False)
    )
    (out_dir / "final_answer.txt").write_text(final + "\n")
    (out_dir / "result_summary.txt").write_text(
        f"success: {result.success}\n"
        f"tool_calls: {tool_call_count}\n"
        f"wall_ms: {wall_ms}\n"
        f"used_file_content: {used_file_content}\n"
        f"first_line: {actual_first_line!r}\n"
        f"final_answer: {final!r}\n"
    )
    print(f"\n  Artefacts: {out_dir}/")
    return 0 if (result.success and used_file_content) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
