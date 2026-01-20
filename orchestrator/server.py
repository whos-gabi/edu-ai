"""
Tooling layer for the Orchestrator.

This module defines the callable tools exposed to the language model,
including JSON schemas that can be passed to Azure OpenAI. Tools cover:
- Grade retrieval
- Absence checks
- Regulation search over Azure AI Search

Environment variables (load via python-dotenv):
- GRADEBOOK_API_BASE_URL: Base URL for the gradebook service.
- GRADEBOOK_API_KEY: API key header for the gradebook service.
- AZURE_SEARCH_ENDPOINT: Endpoint for Azure AI Search service.
- AZURE_SEARCH_KEY: Admin/query key for Azure AI Search.
- AZURE_SEARCH_INDEX: Index name containing regulations.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from prompts import TOOL_DESCRIPTIONS

load_dotenv()

logger = logging.getLogger("orchestrator.server")

GRADEBOOK_API_BASE_URL = os.getenv("GRADEBOOK_API_BASE_URL")
GRADEBOOK_API_KEY = os.getenv("GRADEBOOK_API_KEY")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")


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


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot fulfill the request due to external errors."""


def _call_gradebook_api(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke the gradebook API with shared headers and basic error handling.

    Args:
        path: Route path (e.g., "/students/grades").
        params: Query parameters to pass through.

    Returns:
        Parsed JSON payload.
    """

    if not GRADEBOOK_API_KEY:
        raise ToolExecutionError("GRADEBOOK_API_KEY is missing.")

    url = f"{GRADEBOOK_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {"x-api-key": GRADEBOOK_API_KEY}

    # region debug log H4
    _debug_log(
        "H4",
        "server.py:_call_gradebook_api",
        "gradebook_request_pre",
        {
            "base_url_set": bool(GRADEBOOK_API_BASE_URL),
            "base_url_host": urlparse(GRADEBOOK_API_BASE_URL or "").netloc,
            "path": path,
            "params_keys": sorted(params.keys()),
            "phone_len": len(str(params.get("phone", ""))),
        },
    )
    # endregion

    logger.info("Calling gradebook API %s with params=%s", url, params)
    response = requests.get(url, headers=headers, params=params, timeout=15)

    if not response.ok:
        raise ToolExecutionError(
            f"Gradebook API error {response.status_code}: {response.text}"
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ToolExecutionError("Gradebook API returned non-JSON response.") from exc


def get_student(phone: str) -> Dict[str, Any]:
    """
    Fetch student core data by phone (includes class and homeroom teacher).

    Args:
        phone: Phone number including country code (e.g., "+407...").

    Returns:
        Student metadata payload.
    """

    return _call_gradebook_api("/students/by-phone", params={"phone": phone})


def get_subjects(phone: str) -> Dict[str, Any]:
    """
    Fetch subjects for a student's class, including teacher names.

    Args:
        phone: Phone number including country code (e.g., "+407...").

    Returns:
        Subjects and teachers payload.
    """

    return _call_gradebook_api("/students/subjects", params={"phone": phone})


def get_timetable(phone: str) -> Dict[str, Any]:
    """
    Fetch timetable grouped by day for the student's class.

    Args:
        phone: Phone number including country code (e.g., "+407...").

    Returns:
        Timetable payload.
    """

    return _call_gradebook_api("/students/timetable", params={"phone": phone})


def get_grades(phone: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch grades for a student by phone number.

    If a subject is provided, returns grades for that subject including average.
    Otherwise, returns a summary grouped by subject.

    Args:
        phone: Phone number including country code (e.g., "+407...").
        subject: Optional subject name to scope the query.

    Returns:
        Grade data from the gradebook service.
    """

    if subject:
        return _call_gradebook_api(
            "/students/grades", params={"phone": phone, "subject": subject}
        )
    return _call_gradebook_api("/students/grades/summary", params={"phone": phone})


def check_absences(phone: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch absences for a student by phone number.

    If a subject is provided, returns absences for that subject.
    Otherwise, returns a summary grouped by subject.

    Args:
        phone: Phone number including country code (e.g., "+407...").
        subject: Optional subject name to scope the query.

    Returns:
        Absence data from the gradebook service.
    """

    if subject:
        return _call_gradebook_api(
            "/students/absences", params={"phone": phone, "subject": subject}
        )
    return _call_gradebook_api("/students/absences/summary", params={"phone": phone})


def search_regulations(query: str, top: int = 3) -> Dict[str, Any]:
    """
    Perform a vector/text search over the school regulations index.

    Args:
        query: Natural language query.
        top: Maximum number of documents to return.

    Returns:
        Search results payload.
    """

    if not all([AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_INDEX]):
        raise ToolExecutionError(
            "Azure Search configuration is incomplete. "
            "Expected AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_INDEX."
        )

    url = (
        f"{AZURE_SEARCH_ENDPOINT.rstrip('/')}/indexes/"
        f"{AZURE_SEARCH_INDEX}/docs/search"
    )
    params = {"api-version": "2021-04-30-Preview"}
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_KEY,
    }
    payload = {"search": query, "top": top}

    logger.info("Calling Azure Search with query=%s top=%s", query, top)
    response = requests.post(url, params=params, headers=headers, json=payload, timeout=15)

    if not response.ok:
        raise ToolExecutionError(
            f"Azure Search error {response.status_code}: {response.text}"
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ToolExecutionError("Azure Search returned non-JSON response.") from exc


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_student",
            "description": TOOL_DESCRIPTIONS["get_student"],
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Numărul de telefon al elevului (ex: +40701234567).",
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subjects",
            "description": TOOL_DESCRIPTIONS["get_subjects"],
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Numărul de telefon al elevului (ex: +40701234567).",
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timetable",
            "description": TOOL_DESCRIPTIONS["get_timetable"],
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Numărul de telefon al elevului (ex: +40701234567).",
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_grades",
            "description": TOOL_DESCRIPTIONS["get_grades"],
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Numărul de telefon al elevului (ex: +40701234567).",
                    },
                    "subject": {
                        "type": "string",
                        "description": (
                            "Numele materiei (ex: Matematică). Dacă nu este furnizat, se întoarce sumarul."
                        ),
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_absences",
            "description": TOOL_DESCRIPTIONS["check_absences"],
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Numărul de telefon al elevului (ex: +40701234567).",
                    },
                    "subject": {
                        "type": "string",
                        "description": (
                            "Numele materiei (ex: Limba Română). Dacă nu este furnizat, se întoarce sumarul."
                        ),
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_regulations",
            "description": TOOL_DESCRIPTIONS["search_regulations"],
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Întrebarea utilizatorului în limbaj natural.",
                    },
                    "top": {
                        "type": "integer",
                        "description": "Numărul maxim de rezultate (implicit 3).",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
]
