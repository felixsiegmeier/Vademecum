import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

THINKING_BUDGET_BLOCK_1 = 512
THINKING_BUDGET_BLOCK_2 = 1024

MAX_ITERATIONS_BLOCK_1 = 8
MAX_ITERATIONS_BLOCK_2 = 5


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


async def run_pass(
    llm,
    system_prompt: str,
    user_messages: list[dict],
    tools: list[dict],
    thinking_budget: int,
    max_iterations: int = 5,
    pass_name: str = "pass",
) -> list[list[dict]]:
    """Multi-Turn-Loop für einen Extraction-Pass.

    Sammelt Tool-Calls iterationsweise ohne sie anzuwenden. Tool-Results
    sind einfache Acknowledgment-Strings, damit der LLM weitermachen kann.
    Bricht ab wenn der LLM 0 Tool-Calls liefert oder max_iterations erreicht.

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
    print(f"[{pass_name} start] conversation_msgs={len(conversation)}, user_msg_content_len={sum(len(str(m.get('content',''))) for m in conversation if m.get('role')=='user')}")

    for iter_n in range(1, max_iterations + 1):
        last_iter = iter_n
        response = await llm.chat_completion(
            conversation,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=8192,
            thinking_budget=thinking_budget,
        )
        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        usage = getattr(response, "usage", None)
        tokens_in = usage.prompt_tokens if usage else "?"
        tokens_out = usage.completion_tokens if usage else "?"

        if not msg.tool_calls:
            exit_reason = "empty_response" if iter_n == 1 else "complete"
            print(f"[{pass_name} iter {iter_n}/{max_iterations}] iteration={iter_n}, proposals_in_response=0, tokens_in={tokens_in}, tokens_out={tokens_out}, finish_reason={finish_reason}")
            print(f"[{pass_name} no-tool-call response] content={repr(msg.content)[:500]}, usage_raw={usage}")
            break

        # Parse valide Tool-Calls — malformed JSON wird übersprungen
        valid_calls: list[dict] = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON args für Tool %s, wird übersprungen", tc.function.name)
                continue
            valid_calls.append({"tool": tc.function.name, "args": args})

        print(f"[{pass_name} iter {iter_n}/{max_iterations}] iteration={iter_n}, proposals_in_response={len(valid_calls)}, tokens_in={tokens_in}, tokens_out={tokens_out}, finish_reason={finish_reason}")

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

    total_proposals = sum(len(i) for i in iterations)
    print(f"[{pass_name} done] total_iterations={last_iter}, total_proposals={total_proposals}, exit_reason={exit_reason}")
    return iterations


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
