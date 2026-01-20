"""
FastAPI-based orchestrator agent that uses Azure OpenAI with tool calling.

Responsibilities:
- Expose REST endpoints for chat and health checks.
- Manage per-user conversation memory in-memory.
- Route tool calls to gradebook and regulation search utilities.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import AzureOpenAI
from pydantic import BaseModel

from prompts import SYSTEM_PROMPT
from server import (
    TOOLS,
    ToolExecutionError,
    check_absences,
    get_grades,
    get_student,
    get_subjects,
    get_timetable,
    search_regulations,
)

load_dotenv()

# Configure root logging once; downstream modules reuse the same handler.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("orchestrator.agent")

TOOL_FUNCTIONS = {
    "get_student": get_student,
    "get_subjects": get_subjects,
    "get_timetable": get_timetable,
    "get_grades": get_grades,
    "check_absences": check_absences,
    "search_regulations": search_regulations,
}

app = FastAPI(title="EduAi Orchestrator", version="1.0.0")

# Per-user conversation histories; key = phone, value = list of messages.
user_histories: Dict[str, List[Dict[str, Any]]] = {}

# Lazy-initialized Azure OpenAI client.
_client: Optional[AzureOpenAI] = None


def _debug_log(hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open("/Users/cryptobroski/git/edu-ai/.cursor/debug.log", "a") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _phone_kind(phone: str) -> str:
    if phone.startswith("+"):
        return "phone_like"
    if phone.isdigit():
        return "digits_only"
    return "other"


def _now_context_ro() -> str:
    weekday_names = [
        "luni",
        "marți",
        "miercuri",
        "joi",
        "vineri",
        "sâmbătă",
        "duminică",
    ]
    now = datetime.now()
    weekday = weekday_names[now.weekday()]
    return f"Data curentă este {weekday}, {now.strftime('%d.%m.%Y')}."


class ChatRequest(BaseModel):
    """Inbound chat payload."""

    phone: str  # Verified phone number (server-trusted)
    message: str  # User message


def build_client() -> AzureOpenAI:
    """
    Instantiate the Azure OpenAI client from environment variables.

    Expected variables:
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_KEY
    - AZURE_OPENAI_DEPLOYMENT (model/deployment name)
    - AZURE_OPENAI_API_VERSION (optional, defaults to 2024-05-01-preview)
    """

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")

    if not all([endpoint, api_key, deployment]):
        missing = [
            name
            for name, value in [
                ("AZURE_OPENAI_ENDPOINT", endpoint),
                ("AZURE_OPENAI_KEY", api_key),
                ("AZURE_OPENAI_DEPLOYMENT", deployment),
            ]
            if not value
        ]
        raise RuntimeError(f"Missing Azure OpenAI environment variables: {', '.join(missing)}")

    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )
    logger.info("Azure OpenAI client initialized with deployment '%s'.", deployment)
    return client


def _append_message(messages: List[Dict[str, Any]], role: str, content: str) -> None:
    """Helper to append a simple message to the running conversation."""

    messages.append({"role": role, "content": content})


PHONE_BOUND_TOOLS = {
    "get_student",
    "get_subjects",
    "get_timetable",
    "get_grades",
    "check_absences",
}


def _dispatch_tool_call(tool_call: Dict[str, Any], phone: str) -> str:
    """
    Execute a tool call from the model and return serialized content.

    Security: for phone-bound tools, the backend injects the authenticated
    user's phone and ignores any phone provided by the model.

    Args:
        tool_call: Tool call payload from the model response.
        phone: Authenticated user phone number.

    Returns:
        JSON-encoded string with the tool result or error information.
    """

    name = tool_call["function"]["name"]
    arguments_raw = tool_call["function"]["arguments"]

    # region debug log H1
    _debug_log(
        "H1",
        "agent.py:_dispatch_tool_call",
        "tool_call_received",
        {
            "tool": name,
            "phone_bound": name in PHONE_BOUND_TOOLS,
            "args_has_phone": '"phone"' in (arguments_raw or ""),
            "phone_kind": _phone_kind(phone),
            "phone_len": len(phone),
        },
    )
    # endregion

    logger.info("AI requested tool '%s' with args=%s", name, arguments_raw)

    try:
        arguments = json.loads(arguments_raw or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid arguments JSON.", "raw": arguments_raw})

    if name in PHONE_BOUND_TOOLS:
        # Enforce server-side binding of phone to the authenticated user.
        arguments["phone"] = phone

        # region debug log H2
        _debug_log(
            "H2",
            "agent.py:_dispatch_tool_call",
            "phone_bound_to_user",
            {
                "tool": name,
                "bound_phone_kind": _phone_kind(str(arguments.get("phone", ""))),
                "bound_phone_len": len(str(arguments.get("phone", ""))),
            },
        )
        # endregion

    tool_fn = TOOL_FUNCTIONS.get(name)
    if not tool_fn:
        return json.dumps({"error": f"Tool '{name}' is not implemented."})

    try:
        result = tool_fn(**arguments)
        return json.dumps(result)
    except ToolExecutionError as exc:
        logger.exception("Tool '%s' failed.", name)
        return json.dumps({"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during tool '%s'.", name)
        return json.dumps({"error": f"Unexpected error: {exc}"})


def _get_client() -> AzureOpenAI:
    """Return a cached Azure OpenAI client instance."""

    global _client
    if _client is None:
        _client = build_client()
    return _client


def _get_history(phone: str) -> List[Dict[str, Any]]:
    """
    Retrieve or initialize the conversation history for a user.

    Ensures the system prompt is present as the first message.
    """

    if phone not in user_histories:
        user_histories[phone] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    "Identitatea utilizatorului este verificată. "
                    "Telefonul este furnizat de backend; nu îl cere și nu îl confirma, "
                    "apelează uneltele direct."
                ),
            },
            {"role": "system", "content": _now_context_ro()},
        ]
    return user_histories[phone]


def _repair_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure there are no dangling assistant tool_calls without tool replies.

    If inconsistencies are found, the history is reset to only the system prompt
    to avoid BadRequestError from the LLM API.
    """

    pending_ids = set()
    system_messages = [m for m in history if m.get("role") == "system"]

    for msg in history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                pending_ids.add(tc["id"])
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id in pending_ids:
                pending_ids.remove(tc_id)

    if pending_ids:
        # Reset to system prompt(s) only; drop inconsistent turns.
        return system_messages if system_messages else [{"role": "system", "content": SYSTEM_PROMPT}]
    return history


def process_chat(phone: str, user_message: str) -> str:
    """
    Process a single chat turn for a given user, including tool calls.

    Args:
        phone: Verified phone number for the authenticated user.
        user_message: Latest user input.

    Returns:
        Final assistant reply content.
    """

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not deployment:
        raise RuntimeError("AZURE_OPENAI_DEPLOYMENT is not set.")

    original_history = _get_history(phone)
    history = _repair_history(original_history)
    if history is not original_history:
        user_histories[phone] = history

    # Refresh "current date" system context on each request.
    history[:] = [
        msg
        for msg in history
        if not (msg.get("role") == "system" and str(msg.get("content", "")).startswith("Data curentă este"))
    ]
    history.append({"role": "system", "content": _now_context_ro()})

    _append_message(history, "user", user_message)

    client = _get_client()

    while True:
        response = client.chat.completions.create(
            model=deployment,
            messages=history,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message

        assistant_message: Dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        history.append(assistant_message)

        if not message.tool_calls:
            return message.content or ""

        # Handle tool calls and continue the loop.
        for tool_call in assistant_message.get("tool_calls", []):
            tool_result = _dispatch_tool_call(tool_call, phone)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_call["function"]["name"],
                    "content": tool_result,
                }
            )


@app.get("/health")
def health() -> Dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> Dict[str, str]:
    """
    Chat endpoint that processes user messages with Azure OpenAI + tools.
    """

    # region debug log H3
    _debug_log(
        "H3",
        "agent.py:chat",
        "chat_request_received",
        {
            "phone_kind": _phone_kind(request.phone),
            "phone_len": len(request.phone),
            "message_len": len(request.message),
        },
    )
    # endregion
    try:
        reply = process_chat(request.phone, request.message)
        return {"reply": reply}
    except ToolExecutionError as exc:
        logger.exception("Tool execution failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Configuration error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during chat")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
