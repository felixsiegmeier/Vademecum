import asyncio
import json
import logging
from typing import AsyncGenerator, Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

THINKING_BUDGET_BLOCK_1 = 512
THINKING_BUDGET_BLOCK_2 = 1024

MAX_ITERATIONS_BLOCK_1 = 8
MAX_ITERATIONS_BLOCK_2 = 5

# Token-Budgets: Notbremse gegen Runaway-Loops, nicht Kostenkontrolle.
# Absichtlich hoch angesetzt — ein realer Überlauf wäre ein Bug, kein Normalfall.
MAX_TOTAL_TOKENS_BLOCK_1 = 200_000
MAX_TOTAL_TOKENS_BLOCK_2 = 100_000

_MAX_MALFORMED_RETRIES = 2  # 1 initial + 2 retries = 3 total attempts


class ToolCallInfo(BaseModel):
    tool: str
    args: dict


class Proposal(BaseModel):
    type: Literal["add", "delete", "update", "update_singleton"]
    # Für add / delete / update_singleton:
    call: Optional[ToolCallInfo] = None
    # Für update (delete + add im selben Turn):
    delete_call: Optional[ToolCallInfo] = None
    add_call: Optional[ToolCallInfo] = None


def _extract_call_tokens(usage) -> int | None:
    """Extrahiert die Token-Anzahl aus einem LLM-Response-Usage-Objekt.

    Gibt None zurück wenn usage fehlt — Caller behandelt das als 0 + WARN.
    Nutzt total_tokens falls vorhanden, sonst prompt + completion.
    """
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if total is not None:
        return int(total)
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    return prompt + completion


async def run_pass(
    llm,
    system_prompt: str,
    user_messages: list[dict],
    tools: list[dict],
    thinking_budget: int,
    max_iterations: int = 5,
    max_tokens: int = 8192,
    max_total_tokens: int = MAX_TOTAL_TOKENS_BLOCK_1,
    pass_name: str = "pass",
) -> list[list[dict]]:
    """Multi-Turn-Loop für einen Extraction-Pass.

    Sammelt Tool-Calls iterationsweise ohne sie anzuwenden. Tool-Results
    sind einfache Acknowledgment-Strings, damit der LLM weitermachen kann.
    Bricht ab wenn der LLM 0 Tool-Calls liefert, max_iterations erreicht
    oder max_total_tokens überschritten wird.

    Returns: Liste von Iterationen, jede Iteration ist eine Liste von
    {"tool": str, "args": dict}-Dicts.
    """
    conversation: list[dict] = [
        {"role": "system", "content": system_prompt},
        *user_messages,
    ]
    iterations: list[list[dict]] = []
    exit_reason = "max_iter"
    last_iter = 0
    cumulative_tokens = 0
    _warned_no_usage = False

    logger.info(
        "[%s] start: conversation_msgs=%d, user_content_len=%d",
        pass_name,
        len(conversation),
        sum(len(str(m.get("content", ""))) for m in conversation if m.get("role") == "user"),
    )

    for iter_n in range(1, max_iterations + 1):
        last_iter = iter_n
        response = await llm.chat_completion(
            conversation,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
        )
        finish_reason = response.choices[0].finish_reason

        # Iteration 1 only: Gemini droppt intermittierend das PDF-Content-Part,
        # liefert MALFORMED_FUNCTION_CALL. Retry bis zu _MAX_MALFORMED_RETRIES.
        if iter_n == 1:
            retries = 0
            while "MALFORMED_FUNCTION_CALL" in str(finish_reason or ""):
                if retries >= _MAX_MALFORMED_RETRIES:
                    logger.warning(
                        "[%s] retry erschöpft: 3 Versuche alle MALFORMED_FUNCTION_CALL",
                        pass_name,
                    )
                    raise RuntimeError(
                        f"LLM provider instability: {pass_name} failed after "
                        f"{_MAX_MALFORMED_RETRIES + 1} attempts (PDF drop). "
                        f"Bitte Upload erneut starten."
                    )
                retries += 1
                logger.warning(
                    "[%s] iter=1 MALFORMED_FUNCTION_CALL (PDF-Drop?), retry %d/3 nach 500ms",
                    pass_name,
                    retries,
                )
                await asyncio.sleep(0.5)
                response = await llm.chat_completion(
                    conversation,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0,
                    max_tokens=max_tokens,
                    thinking_budget=thinking_budget,
                )
                finish_reason = response.choices[0].finish_reason

        msg = response.choices[0].message
        usage = getattr(response, "usage", None)
        call_tokens = _extract_call_tokens(usage)
        if call_tokens is None:
            if not _warned_no_usage:
                logger.warning(
                    "[%s] Response ohne usage-Objekt — Token-Zählung inakkurat ab jetzt",
                    pass_name,
                )
                _warned_no_usage = True
            call_tokens = 0
        cumulative_tokens += call_tokens

        if not msg.tool_calls:
            exit_reason = "empty_response" if iter_n == 1 else "complete"
            logger.info(
                "[%s] iter %d/%d: no tool calls, exit=%s, tokens=%d/%d, finish=%s",
                pass_name, iter_n, max_iterations, exit_reason,
                cumulative_tokens, max_total_tokens, finish_reason,
            )
            break

        # Parse valide Tool-Calls — malformed JSON wird übersprungen
        valid_calls: list[dict] = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "[%s] Malformed JSON args für Tool %s, wird übersprungen",
                    pass_name, tc.function.name,
                )
                continue
            valid_calls.append({"tool": tc.function.name, "args": args})

        logger.info(
            "[%s] iter %d/%d: proposals=%d, call_tokens=%d, cumulative=%d/%d, finish=%s",
            pass_name, iter_n, max_iterations, len(valid_calls),
            call_tokens, cumulative_tokens, max_total_tokens, finish_reason,
        )

        if valid_calls:
            iterations.append(valid_calls)

        # Assistent-Turn anhängen (inkl. Gemini-Metadaten wie thought_signature)
        assistant_dict = {k: v for k, v in msg.model_dump().items() if v is not None}
        conversation.append(assistant_dict)

        # Tool-Acknowledgments für alle Calls (auch malformed — API erwartet alle IDs)
        for tc in msg.tool_calls:
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"queued: {tc.function.name}",
            })

        if cumulative_tokens >= max_total_tokens:
            exit_reason = "token_budget_exceeded"
            logger.warning(
                "[%s] Token-Budget erschöpft nach iter %d: %d >= %d — Loop-Abbruch",
                pass_name, iter_n, cumulative_tokens, max_total_tokens,
            )
            break

    total_proposals = sum(len(i) for i in iterations)
    logger.info(
        "[%s] done: total_iters=%d, total_proposals=%d, exit=%s, cumulative_tokens=%d",
        pass_name, last_iter, total_proposals, exit_reason, cumulative_tokens,
    )
    return iterations


_HEARTBEAT_INTERVAL: float = 5.0


async def _yield_heartbeats_and_run(coro, out: list) -> AsyncGenerator[dict, None]:
    """Yields heartbeat events every _HEARTBEAT_INTERVAL seconds while awaiting coro.

    Stores the coroutine result in out[0]; re-raises the exception if coro fails.

    Why as a background Task instead of yield-in-mainloop: async generators can
    only yield when they have control of the event loop. Running the LLM call as
    a Task and polling with asyncio.wait gives back control at each heartbeat
    tick, keeping the NDJSON stream alive through reverse-proxy idle timeouts
    (Nginx default: 60 s).
    """
    task = asyncio.create_task(coro)
    next_hb = asyncio.create_task(asyncio.sleep(_HEARTBEAT_INTERVAL))
    try:
        while not task.done():
            done, _ = await asyncio.wait([task, next_hb], return_when=asyncio.FIRST_COMPLETED)
            if next_hb in done and not task.done():
                yield {"type": "heartbeat"}
                next_hb = asyncio.create_task(asyncio.sleep(_HEARTBEAT_INTERVAL))
    finally:
        next_hb.cancel()
        try:
            await next_hb
        except asyncio.CancelledError:
            pass
    out.append(task.result())  # re-raises if task raised


async def run_pass_streaming(
    llm,
    system_prompt: str,
    user_messages: list[dict],
    tools: list[dict],
    thinking_budget: int,
    phase: Literal["block1", "block2"],
    max_iterations: int = 5,
    max_tokens: int = 8192,
    max_total_tokens: int = MAX_TOTAL_TOKENS_BLOCK_1,
    pass_name: str = "pass",
) -> AsyncGenerator[dict, None]:
    """Multi-Turn-Loop (streaming variant). Yields status, heartbeat, proposals events.

    Event order per iteration: status (before LLM call) → heartbeats (during call)
    → proposals (after successful tool batch). status-before-proposals guarantees
    the client sees "working on block1, iter N" before results; the done event is
    the caller's responsibility (emitted after both passes complete).

    Yields {"type": "aborted", "reason": "token_budget_exceeded", ...} and returns
    when max_total_tokens is exceeded after completing the current iteration.
    """
    conversation: list[dict] = [
        {"role": "system", "content": system_prompt},
        *user_messages,
    ]
    items_in_phase = 0
    exit_reason = "max_iter"
    last_iter = 0
    cumulative_tokens = 0
    _warned_no_usage = False

    logger.info(
        "[%s] stream start: conversation_msgs=%d, user_content_len=%d",
        pass_name,
        len(conversation),
        sum(len(str(m.get("content", ""))) for m in conversation if m.get("role") == "user"),
    )

    for iter_n in range(1, max_iterations + 1):
        last_iter = iter_n

        # Status event before call — lets client display progress immediately
        yield {
            "type": "status",
            "phase": phase,
            "iter": iter_n,
            "max_iter": max_iterations,
            "items_in_phase": items_in_phase,
        }

        # LLM call with interleaved heartbeats
        resp_box: list = []
        async for event in _yield_heartbeats_and_run(
            llm.chat_completion(
                conversation,
                tools=tools,
                tool_choice="auto",
                temperature=0,
                max_tokens=max_tokens,
                thinking_budget=thinking_budget,
            ),
            resp_box,
        ):
            yield event
        response = resp_box[0]
        finish_reason = response.choices[0].finish_reason

        # Retry on MALFORMED_FUNCTION_CALL (iter 1 only — Gemini PDF-drop workaround)
        if iter_n == 1:
            retries = 0
            while "MALFORMED_FUNCTION_CALL" in str(finish_reason or ""):
                if retries >= _MAX_MALFORMED_RETRIES:
                    msg_text = (
                        f"LLM provider instability: {pass_name} failed after "
                        f"{_MAX_MALFORMED_RETRIES + 1} attempts (PDF drop). "
                        f"Bitte Upload erneut starten."
                    )
                    logger.warning("[%s] retry erschöpft: 3 Versuche MALFORMED_FUNCTION_CALL", pass_name)
                    yield {"type": "error", "message": msg_text, "retryable": True}
                    return
                retries += 1
                logger.warning(
                    "[%s] iter=1 MALFORMED_FUNCTION_CALL (PDF-Drop?), retry %d/3",
                    pass_name, retries,
                )
                await asyncio.sleep(0.5)
                resp_box = []
                async for event in _yield_heartbeats_and_run(
                    llm.chat_completion(
                        conversation,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0,
                        max_tokens=max_tokens,
                        thinking_budget=thinking_budget,
                    ),
                    resp_box,
                ):
                    yield event
                response = resp_box[0]
                finish_reason = response.choices[0].finish_reason

        msg = response.choices[0].message
        usage = getattr(response, "usage", None)
        call_tokens = _extract_call_tokens(usage)
        if call_tokens is None:
            if not _warned_no_usage:
                logger.warning(
                    "[%s] Response ohne usage-Objekt — Token-Zählung inakkurat ab jetzt",
                    pass_name,
                )
                _warned_no_usage = True
            call_tokens = 0
        cumulative_tokens += call_tokens

        if not msg.tool_calls:
            exit_reason = "empty_response" if iter_n == 1 else "complete"
            logger.info(
                "[%s] iter %d/%d: no tool calls, exit=%s, tokens=%d/%d, finish=%s",
                pass_name, iter_n, max_iterations, exit_reason,
                cumulative_tokens, max_total_tokens, finish_reason,
            )
            break

        valid_calls: list[dict] = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "[%s] Malformed JSON args für Tool %s, wird übersprungen",
                    pass_name, tc.function.name,
                )
                continue
            valid_calls.append({"tool": tc.function.name, "args": args})

        logger.info(
            "[%s] iter %d/%d: proposals=%d, call_tokens=%d, cumulative=%d/%d, finish=%s",
            pass_name, iter_n, max_iterations, len(valid_calls),
            call_tokens, cumulative_tokens, max_total_tokens, finish_reason,
        )

        if valid_calls:
            # items_in_phase counts add_* calls cumulatively within the phase
            items_in_phase += sum(1 for c in valid_calls if c["tool"].startswith("add_"))
            proposals_batch = group_proposals([valid_calls])
            yield {
                "type": "proposals",
                "phase": phase,
                "items": [p.model_dump() for p in proposals_batch],
            }

        assistant_dict = {k: v for k, v in msg.model_dump().items() if v is not None}
        conversation.append(assistant_dict)

        for tc in msg.tool_calls:
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"queued: {tc.function.name}",
            })

        if cumulative_tokens >= max_total_tokens:
            exit_reason = "token_budget_exceeded"
            logger.warning(
                "[%s] Token-Budget erschöpft nach iter %d: %d >= %d — Stream-Abbruch",
                pass_name, iter_n, cumulative_tokens, max_total_tokens,
            )
            yield {
                "type": "aborted",
                "reason": "token_budget_exceeded",
                "phase": phase,
                "iter": iter_n,
                "cumulative_tokens": cumulative_tokens,
                "max_total_tokens": max_total_tokens,
            }
            return

    logger.info(
        "[%s] stream done: total_iters=%d, exit=%s, cumulative_tokens=%d",
        pass_name, last_iter, exit_reason, cumulative_tokens,
    )


def group_proposals(iterations: list[list[dict]]) -> list[Proposal]:
    """Bündelt Tool-Call-Iterationen zu Proposals.

    Regel: 1 delete_entry + 1 add_* im selben Turn → Update-Proposal.
    Alles andere → separate Proposals pro Call.
    """
    proposals: list[Proposal] = []

    for calls in iterations:
        deletes = [c for c in calls if c["tool"] == "delete_entry"]
        adds = [c for c in calls if c["tool"].startswith("add_")]
        updates = [c for c in calls if c["tool"].startswith("update_")]

        if len(deletes) == 1 and len(adds) == 1 and not updates:
            proposals.append(Proposal(
                type="update",
                delete_call=ToolCallInfo(tool=deletes[0]["tool"], args=deletes[0]["args"]),
                add_call=ToolCallInfo(tool=adds[0]["tool"], args=adds[0]["args"]),
            ))
        else:
            for c in calls:
                if c["tool"].startswith("add_"):
                    kind: Literal["add", "delete", "update_singleton"] = "add"
                elif c["tool"] == "delete_entry":
                    kind = "delete"
                else:
                    kind = "update_singleton"
                proposals.append(Proposal(
                    type=kind,
                    call=ToolCallInfo(tool=c["tool"], args=c["args"]),
                ))

    return proposals
