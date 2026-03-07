"""
Campus Queue Assistant — Improved Backend (Anti-Hallucination + Smart UX)
=========================================================================
Improvements over previous version:
  - Richer intent classification (join-how, join-dept, complaint, review, emergency, notification)
  - All responses are system-aware and action-oriented (no "go to reception")
  - Queue data (length, wait time) injected into join/status responses
  - "How to join" always gives step-by-step with live dept data when available
  - Complaints route to feedback/review flow, never dead-end
  - Slight phrasing variations handled by expanded keyword + regex banks
  - Ticket status only shown when the user actually asks about it
"""

import os
import re
import requests
from enum import Enum, auto
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

from analytics import AnalyticsHandler, is_analytics_message, detect_analytics_intent

load_dotenv("../backend/.env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_HISTORY         = 10
OLLAMA_URL          = "http://localhost:11434/api/chat"
MODEL_NAME          = "llama3"
MONGO_URI           = os.getenv("MONGO_URI", "mongodb://localhost:27017")

OLLAMA_TIMEOUT      = 30
OLLAMA_TEMPERATURE  = 0.3
OLLAMA_MAX_TOKENS   = 120
LLM_HISTORY_WINDOW  = 4

# ---------------------------------------------------------------------------
# App + DB
# ---------------------------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client            = AsyncIOMotorClient(MONGO_URI)
db                = client["test"]
analytics_handler = AnalyticsHandler(db)

# ---------------------------------------------------------------------------
# Per-user in-memory session
# ---------------------------------------------------------------------------

conversation_memory: dict[str, list[dict]] = {}
last_dept_mentioned: dict[str, Optional[str]] = {}

# ---------------------------------------------------------------------------
# System prompt — LLM told explicitly it has NO knowledge of live data
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the Campus Assistant AI for a university queue management system.\n\n"
    "STRICT RULES — follow these without exception:\n"
    "1. You have NO access to live queue data, ticket data, or department status.\n"
    "2. NEVER tell users to go to a reception desk, office, or physical location.\n"
    "3. NEVER state or imply that a queue is open, closed, busy, or unavailable.\n"
    "4. NEVER invent reasons like 'high volume', 'technical issue', or 'capacity reached'.\n"
    "5. NEVER guess ticket positions, wait times, or department availability.\n"
    "6. All system actions happen inside the digital Campus Queue platform — "
    "always guide users to features in the app (Dashboard, Departments, Join Queue, etc.).\n"
    "7. If asked about live system state, say you cannot answer and refer the user "
    "to their dashboard.\n\n"
    "You MAY help with:\n"
    "- Explaining how the queue system works in general terms.\n"
    "- Answering general campus or ticketing process questions.\n"
    "- Friendly small talk and greetings.\n\n"
    "Keep answers short (2-3 sentences max), friendly, and helpful."
)

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class Intent(Enum):
    IDENTITY          = auto()
    GREETING          = auto()
    ACKNOWLEDGEMENT   = auto()
    DECLINE           = auto()
    OTHER_PROMPT      = auto()
    TICKET_STATUS     = auto()
    DEPT_LIST         = auto()
    QUEUE_STATUS      = auto()   # open/closed, how-many-waiting
    JOIN_QUEUE_DEPT   = auto()   # "join electrical queue" — dept identified
    JOIN_QUEUE_HOW    = auto()   # "how do I join a queue" — no dept
    CANT_JOIN         = auto()   # "I can't join" — troubleshooting
    COMPLAINT         = auto()   # rude staff, bad service, complaint
    REVIEW            = auto()   # leave a review / give feedback
    EMERGENCY_QUEUE   = auto()   # emergency queue questions
    NOTIFICATION      = auto()   # notification / alert questions
    LEAVE_QUEUE       = auto()   # cancel / leave queue
    ANALYTICS         = auto()
    GENERAL_LLM       = auto()


# ── Keyword / pattern banks ──────────────────────────────────────────────────

_TICKET_KEYWORDS = [
    "my ticket", "my status", "my position", "my turn", "my queue",
    "my wait", "my place", "my number", "ticket status", "ticket position",
    "ticket number", "check ticket", "where am i in", "track my",
    "what is my ticket", "whats my ticket",
]

_DEPT_LIST_KEYWORDS = [
    "list departments", "show departments", "which departments",
    "available departments", "all departments", "department list",
    "which dept", "show depts", "list depts", "what departments",
    "departments available", "departments open",
]

# "Join a queue for a specific dept" — dept name extracted separately
_JOIN_DEPT_PATTERNS = [
    r"join\s+(\w+)\s+queue",
    r"queue\s+for\s+(\w+)",
    r"add me to\s+(\w+)",
    r"enroll.{0,10}(in|for|to).{0,10}(\w+)\s+queue",
    r"get in.{0,10}(\w+)\s+(queue|line)",
    r"sign me up.{0,10}(\w+)",
    r"register.{0,15}(\w+)\s+queue",
    r"(\w+)\s+queue.{0,10}(join|enter|get in|sign up)",
    r"join\s+the\s+(\w+)",
    r"i want to join\s+(\w+)",
    r"how (do i|can i|to) join\s+(\w+)",
]

# "How to join" — generic, no dept
_JOIN_HOW_KEYWORDS = [
    "how do i join", "how to join", "how can i join", "joining a queue",
    "steps to join", "process to join", "join the queue", "join a queue",
    "how do i get in", "how to get in line", "add me to queue",
    "how do i enter", "enroll in queue", "sign up for queue",
    "want to join", "i want to join queue", "i'd like to join",
    "how do i queue",
]

_QUEUE_STATUS_PATTERNS = [
    r"(is|are).{0,25}(queue|dept|department).{0,20}(open|closed|available|full)",
    r"(queue|dept|department).{0,25}(open|closed|available|full)",
    r"(why|how come).{0,30}(can.?t|cannot|not able).{0,30}(join|enter|get in)",
    r"(join|joining).{0,20}(queue|the line)",
    r"(how many|number of|count of).{0,20}(people|students|waiting|in line|in queue)",
    r"(wait|waiting).{0,20}(count|number|how many)",
    r"(queue|line).{0,20}(status|state|situation)",
    r"is (cse|ece|admin|eee|mech|civil|it|cs|electrical|mechanical|computer).{0,20}(open|closed|available)",
    r"(open|closed).{0,20}(queue|department|dept)",
    r"(i |i'm |i am )?(cannot|can.?t|unable to|not able to).{0,20}(join|enter|access).{0,30}(queue|it|this|the)",
    r"(having trouble|having an issue|having a problem).{0,30}(join|queue|enter)",
    r"(won.?t|doesn.?t).{0,20}(let me|allow me).{0,20}(join|enter)",
    r"(failed|failing).{0,20}(to join|to enter)",
]

_CANT_JOIN_PHRASES = [
    "i cannot join", "i can't join", "can't join it", "cannot join it",
    "unable to join", "not able to join", "i cannot join it",
    "won't let me join", "not joining", "failed to join",
    "trouble joining", "having trouble joining", "having an issue joining",
    "i cant join", "won't allow me", "not letting me join",
]

_COMPLAINT_KEYWORDS = [
    "rude", "bad service", "staff is rude", "staff was rude", "terrible",
    "horrible", "awful", "disappointed", "unprofessional", "disrespectful",
    "slow service", "very slow", "waste of time", "no help", "unhelpful",
    "disgusting", "worst", "not helpful", "bad experience", "poor service",
    "issue with staff", "problem with staff", "complain", "complaint",
    "unacceptable", "mistreated", "ignored",
]

_REVIEW_KEYWORDS = [
    "leave a review", "give feedback", "submit feedback", "rate the service",
    "how to review", "submit a review", "write a review", "review the service",
    "leave feedback", "give a rating", "rate department", "post a review",
]

_EMERGENCY_KEYWORDS = [
    "emergency queue", "urgent queue", "priority queue", "emergency ticket",
    "urgent ticket", "emergency service", "how does emergency", "emergency case",
    "jump the queue", "bypass queue",
]

_NOTIFICATION_KEYWORDS = [
    "notification", "notify me", "alert", "remind me", "get notified",
    "how will i know", "will i be told", "updates on my ticket",
    "turn notification", "enable notification", "push notification",
]

_LEAVE_QUEUE_KEYWORDS = [
    "leave queue", "cancel ticket", "cancel queue", "exit queue", "remove me",
    "remove from queue", "i want to leave", "cancel my ticket",
    "drop from queue", "quit queue", "withdraw",
]

_IDENTITY_KEYWORDS = [
    "who are you", "what are you", "your name", "are you a bot", "are you ai",
    "are you human", "what can you do",
]
_GREETING_KEYWORDS = [
    "hi", "hello", "hey", "greetings", "good morning", "good afternoon",
    "good evening", "howdy", "sup", "what's up", "whats up",
]
_THANKS_KEYWORDS = ["thanks", "thank you", "thx", "cheers", "appreciate", "ty"]

_HALLUCINATION_BAIT = [
    "why", "reason", "explain", "cause", "because", "happen",
    "issue", "problem", "error", "delay", "volume", "capacity",
]

CANT_JOIN_TROUBLESHOOTING = (
    "Here are a few things to try:\n"
    "1. 🔄 **Refresh the page** and try again.\n"
    "2. 🌐 **Check your internet connection** — a weak signal can prevent joining.\n"
    "3. 🔓 **Log out and log back in** to refresh your session.\n"
    "4. 🧹 **Clear your browser cache** or switch to a different browser.\n"
    "5. 📱 **Try on a different device** (phone vs laptop).\n\n"
    "If none of these help, please contact IT support via your dashboard."
)


@dataclass
class ClassifiedIntent:
    intent: Intent
    dept_hint: Optional[str] = None


def classify_intent(question: str) -> ClassifiedIntent:
    q = question.lower().strip()

    # ── Fast paths ────────────────────────────────────────────────────────────
    if any(k in q for k in _IDENTITY_KEYWORDS):
        return ClassifiedIntent(Intent.IDENTITY)

    if any(q == k or q.startswith(k + " ") for k in _GREETING_KEYWORDS):
        return ClassifiedIntent(Intent.GREETING)

    if any(k in q for k in _THANKS_KEYWORDS):
        return ClassifiedIntent(Intent.ACKNOWLEDGEMENT)

    if q in {"ok", "okay", "k", "sure", "alright", "got it"}:
        return ClassifiedIntent(Intent.ACKNOWLEDGEMENT)

    if q in {"no", "nah", "nope", "not now"}:
        return ClassifiedIntent(Intent.DECLINE)

    if q in {"other", "something else", "another question", "anything else"}:
        return ClassifiedIntent(Intent.OTHER_PROMPT)

    # ── Complaints ────────────────────────────────────────────────────────────
    if any(k in q for k in _COMPLAINT_KEYWORDS):
        return ClassifiedIntent(Intent.COMPLAINT)

    # ── Review / feedback ─────────────────────────────────────────────────────
    if any(k in q for k in _REVIEW_KEYWORDS):
        return ClassifiedIntent(Intent.REVIEW)

    # ── Emergency queue ───────────────────────────────────────────────────────
    if any(k in q for k in _EMERGENCY_KEYWORDS):
        return ClassifiedIntent(Intent.EMERGENCY_QUEUE)

    # ── Notifications ─────────────────────────────────────────────────────────
    if any(k in q for k in _NOTIFICATION_KEYWORDS):
        return ClassifiedIntent(Intent.NOTIFICATION)

    # ── Leave / cancel queue ──────────────────────────────────────────────────
    if any(k in q for k in _LEAVE_QUEUE_KEYWORDS):
        return ClassifiedIntent(Intent.LEAVE_QUEUE)

    # ── Ticket status ─────────────────────────────────────────────────────────
    if any(k in q for k in _TICKET_KEYWORDS):
        return ClassifiedIntent(Intent.TICKET_STATUS)

    # ── Department list ───────────────────────────────────────────────────────
    if any(k in q for k in _DEPT_LIST_KEYWORDS):
        return ClassifiedIntent(Intent.DEPT_LIST)

    # ── "I can't join" (troubleshooting report) ───────────────────────────────
    if any(phrase in q for phrase in _CANT_JOIN_PHRASES):
        return ClassifiedIntent(Intent.CANT_JOIN, dept_hint=_extract_dept_hint(q))

    # ── Join queue WITH a specific department ─────────────────────────────────
    # Check this before generic "how to join" so "join electrical queue" hits here
    dept = _extract_dept_hint(q)
    if dept:
        # Any join-flavoured phrase with a known dept → JOIN_QUEUE_DEPT
        join_flavours = [
            "join", "queue for", "add me", "enroll", "get in", "sign up",
            "register", "i want to", "how do i", "how to", "how can i",
        ]
        if any(f in q for f in join_flavours):
            return ClassifiedIntent(Intent.JOIN_QUEUE_DEPT, dept_hint=dept)

    # ── Generic "how to join" ─────────────────────────────────────────────────
    if any(k in q for k in _JOIN_HOW_KEYWORDS):
        return ClassifiedIntent(Intent.JOIN_QUEUE_HOW)

    # ── Queue status regex ────────────────────────────────────────────────────
    for pattern in _QUEUE_STATUS_PATTERNS:
        if re.search(pattern, q):
            return ClassifiedIntent(Intent.QUEUE_STATUS, dept_hint=_extract_dept_hint(q))

    # ── Analytics ─────────────────────────────────────────────────────────────
    if is_analytics_message(question):
        detection = detect_analytics_intent(question)
        return ClassifiedIntent(
            Intent.ANALYTICS,
            dept_hint=detection.department_hint if detection else None,
        )

    # ── Safety net: system noun + hallucination bait → DB, not LLM ────────────
    if _is_system_adjacent(q):
        return ClassifiedIntent(Intent.QUEUE_STATUS, dept_hint=_extract_dept_hint(q))

    return ClassifiedIntent(Intent.GENERAL_LLM)


def _is_system_adjacent(q: str) -> bool:
    system_nouns = ["queue", "ticket", "department", "dept", "waiting", "join", "status"]
    return (
        any(n in q for n in system_nouns)
        and any(b in q for b in _HALLUCINATION_BAIT)
    )


# Canonical short names → display names for matching
_DEPT_ALIASES: dict[str, str] = {
    "cse":        "CSE",
    "ece":        "ECE",
    "eee":        "EEE",
    "mech":       "Mechanical",
    "mechanical": "Mechanical",
    "civil":      "Civil",
    "it":         "IT",
    "admin":      "Admin",
    "electrical": "Electrical",
    "computer":   "Computer",
    "cs":         "CSE",
}


def _extract_dept_hint(q: str) -> Optional[str]:
    """Return best-guess department name from a query string."""
    detection = detect_analytics_intent(q)
    if detection and detection.department_hint:
        return detection.department_hint
    for alias, canonical in _DEPT_ALIASES.items():
        if re.search(r"\b" + alias + r"\b", q.lower()):
            return canonical
    return None


# ---------------------------------------------------------------------------
# DB query layer
# ---------------------------------------------------------------------------

async def db_get_ticket(user_id: str, role: str) -> Optional[dict]:
    if not user_id or str(user_id).lower() in {"anonymous", "null", "none", "", "undefined"}:
        return None
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    search: dict = {
        "status":    {"$in": ["waiting", "serving", "called"]},
        "createdAt": {"$gte": today},
    }
    if role == "guest":
        search["guestToken"] = user_id
    else:
        clean_id = str(user_id)
        if "ObjectId" in clean_id:
            m = re.search(r"[a-f0-9]{24}", clean_id)
            clean_id = m.group(0) if m else clean_id
        try:
            search["user"] = ObjectId(clean_id)
        except Exception:
            return None
    try:
        return await db.tickets.find_one(search)
    except Exception as e:
        print(f"[DB] db_get_ticket error: {e}")
        return None


async def db_get_queue_status(dept_hint: Optional[str]) -> Optional[dict]:
    """
    Returns dict with: dept_name, is_open, waiting_count, queue_found,
    estimated_wait_minutes (if calculable).
    """
    try:
        depts = await db.departments.find({"isActive": True}).to_list(length=100)
        if not depts:
            return None

        found_dept = None
        if dept_hint:
            hint_lower = dept_hint.lower()
            for d in depts:
                if hint_lower in d.get("name", "").lower():
                    found_dept = d
                    break

        if not found_dept:
            return None

        queue = await db.queues.find_one({"department": found_dept["_id"]})
        if not queue:
            return {
                "dept_name":               found_dept.get("name", "Unknown"),
                "is_open":                 False,
                "waiting_count":           0,
                "queue_found":             False,
                "estimated_wait_minutes":  None,
            }

        waiting_count = await db.tickets.count_documents(
            {"queue": queue["_id"], "status": "waiting"}
        )

        # Estimated wait: use avg_service_time if stored on the queue doc, else ~5 min/person
        avg_time = queue.get("avgServiceTime", 5)
        estimated_wait = waiting_count * avg_time

        return {
            "dept_name":               found_dept.get("name", "Unknown"),
            "is_open":                 bool(queue.get("isOpen", False)),
            "waiting_count":           waiting_count,
            "queue_found":             True,
            "estimated_wait_minutes":  estimated_wait,
        }
    except Exception as e:
        print(f"[DB] db_get_queue_status error: {e}")
        return None


async def db_get_department_list() -> list[str]:
    try:
        depts = await db.departments.find({"isActive": True}).to_list(length=50)
        return [d.get("name") for d in depts if d.get("name")]
    except Exception as e:
        print(f"[DB] db_get_department_list error: {e}")
        return []


# ---------------------------------------------------------------------------
# Response formatting layer
# ---------------------------------------------------------------------------

def _queue_summary_line(data: dict) -> str:
    """Short inline summary: '3 people waiting (~15 min)'."""
    count = data["waiting_count"]
    wait  = data.get("estimated_wait_minutes")
    people = f"{count} person{'s' if count != 1 else ''} waiting"
    if wait is not None:
        return f"{people} (~{wait} min estimated wait)"
    return people


def fmt_ticket_status(
    ticket: Optional[dict],
    user_id: str,
    is_join_query: bool,
    dept_name: str = "your department",
) -> str:
    if ticket:
        status = ticket.get("status", "unknown")
        num    = ticket.get("ticketNumber", "—")
        return (
            f"Your ticket **#{num}** is active in the **{dept_name}** queue. "
            f"Current status: **{status}**.\n\n"
            "You'll get notified when it's your turn. 🔔"
        )
    if not user_id or user_id.lower() in {"anonymous", "null", "none", "", "undefined"}:
        return (
            "You need to be **logged in** to check ticket status. "
            "Please sign in via your Student Dashboard and try again!"
        )
    if is_join_query:
        return (
            "You don't have an active ticket right now. "
            "To join a queue:\n"
            "1️⃣ Go to **Departments**\n"
            "2️⃣ Select your department\n"
            "3️⃣ Tap **Join Queue**"
        )
    return (
        "You don't have any active tickets right now. "
        "Would you like to **join a queue**? Just tell me which department!"
    )


def fmt_join_with_dept(data: Optional[dict], dept_hint: Optional[str]) -> str:
    """Response when user wants to join a specific department's queue."""
    if data is None:
        name = dept_hint or "that department"
        return (
            f"I couldn't find a department matching **{name}**. "
            "Please check the name or tap 🏢 **Departments** to see all available options."
        )

    dept    = data["dept_name"]
    is_open = data["is_open"]

    if not data.get("queue_found"):
        return (
            f"The **{dept}** department doesn't have an active queue set up right now. "
            "Check back later or tap 🏢 **Departments** to see what's available."
        )

    if is_open:
        summary = _queue_summary_line(data)
        return (
            f"To join the **{dept}** queue:\n"
            "1️⃣ Tap 🏢 **Departments**\n"
            f"2️⃣ Select **{dept}**\n"
            "3️⃣ Press **Join Queue**\n\n"
            f"📊 Right now: {summary}."
        )
    else:
        return (
            f"The **{dept}** queue is currently **closed** 🔴 — you can't join right now. "
            "Check your dashboard for updates on when it reopens."
        )


def fmt_join_how() -> str:
    """Generic step-by-step for joining any queue."""
    return (
        "You can join a queue in **3 easy steps**:\n\n"
        "1️⃣ Tap 🏢 **Departments**\n"
        "2️⃣ Choose your department\n"
        "3️⃣ Press **Join Queue**\n\n"
        "Tell me which department you need and I'll show you the live queue info! 😊"
    )


def fmt_queue_status(
    data: Optional[dict],
    dept_hint: Optional[str],
    original_question: str,
) -> str:
    if data is None:
        if dept_hint:
            return (
                f"I couldn't find a department matching **{dept_hint}**. "
                "Try 🏢 **Departments** to see all available options."
            )
        return (
            "Which department are you asking about? "
            "For example: *\"Is the CSE queue open?\"*"
        )

    dept    = data["dept_name"]
    is_open = data["is_open"]

    if not data.get("queue_found"):
        return (
            f"The **{dept}** department exists but doesn't have an active queue right now."
        )

    status_word = "**open** ✅" if is_open else "**closed** 🔴"
    summary     = _queue_summary_line(data)

    q_lower = original_question.lower()

    # User REPORTS they can't join → troubleshooting
    if any(phrase in q_lower for phrase in _CANT_JOIN_PHRASES):
        if is_open:
            return (
                f"The **{dept}** queue is open ✅ and should be joinable "
                f"({summary}) — so this looks like a technical issue on your end.\n\n"
                f"{CANT_JOIN_TROUBLESHOOTING}"
            )
        return (
            f"The **{dept}** queue is **closed** 🔴 right now — that's why you can't join. "
            "Check your dashboard later or try a different department."
        )

    # User asks WHY they can't join
    if re.search(r"(why|how come).{0,30}(can.?t|cannot|not able)", q_lower):
        if is_open:
            return (
                f"The **{dept}** queue is actually **open** right now! {summary}.\n\n"
                f"If you're still unable to join:\n{CANT_JOIN_TROUBLESHOOTING}"
            )
        return (
            f"The **{dept}** queue is **closed** 🔴. "
            "That's why you can't join — check your dashboard for updates."
        )

    # User asks CAN they join
    if re.search(r"can.{0,10}(i|we).{0,10}join", q_lower):
        if is_open:
            return (
                f"Yes! The **{dept}** queue is open ✅. {summary}.\n"
                "Go to 🏢 **Departments → {dept} → Join Queue**."
            )
        return (
            f"The **{dept}** queue is **closed** 🔴 right now — you can't join yet. "
            "Check your dashboard for updates."
        )

    # Default plain status
    return f"The **{dept}** queue is {status_word}. {summary}."


def fmt_cant_join(data: Optional[dict], dept_hint: Optional[str]) -> str:
    """Dedicated troubleshooting path when user explicitly says they can't join."""
    if data is None:
        # No dept resolved — give general troubleshooting
        return (
            "Sorry to hear you're having trouble joining! "
            f"{CANT_JOIN_TROUBLESHOOTING}"
        )
    dept    = data["dept_name"]
    is_open = data["is_open"]
    summary = _queue_summary_line(data)

    if is_open:
        return (
            f"The **{dept}** queue is open ✅ ({summary}), "
            "so this sounds like a technical issue on your end.\n\n"
            f"{CANT_JOIN_TROUBLESHOOTING}"
        )
    return (
        f"The **{dept}** queue is **closed** 🔴 right now — that's why you can't join. "
        "Watch your dashboard or enable notifications to be alerted when it reopens. 🔔"
    )


def fmt_dept_list(names: list[str]) -> str:
    if not names:
        return "There are no active departments at the moment."
    formatted = " • ".join(f"**{n}**" for n in names)
    return (
        f"Active departments: {formatted}.\n\n"
        "Tell me which department you need and I'll check its queue for you! 😊"
    )


def fmt_complaint() -> str:
    return (
        "I'm sorry you had a bad experience. Your feedback really matters to us. 💙\n\n"
        "Here's what you can do:\n"
        "⭐ **Leave a review** — available after your queue visit in the app\n"
        "📩 **Report an issue** — go to your dashboard and tap **Feedback / Report**\n\n"
        "Would you like help navigating to the feedback section?"
    )


def fmt_review() -> str:
    return (
        "You can share your feedback after your visit:\n\n"
        "1️⃣ Complete your queue visit\n"
        "2️⃣ Open your **Ticket History** in the dashboard\n"
        "3️⃣ Tap **Leave a Review** on the completed ticket\n\n"
        "Your reviews help improve the service for everyone! ⭐"
    )


def fmt_emergency_queue() -> str:
    return (
        "**Emergency Queue** is for urgent or priority cases. 🚨\n\n"
        "To access it:\n"
        "1️⃣ Go to 🏢 **Departments**\n"
        "2️⃣ Select your department\n"
        "3️⃣ Tap **Emergency Queue** if available\n\n"
        "Note: Emergency queues are only open when authorised by staff."
    )


def fmt_notification() -> str:
    return (
        "The system will **automatically notify you** when your turn is near! 🔔\n\n"
        "To manage notifications:\n"
        "⚙️ Go to **Settings → Notifications** in the app\n"
        "You can enable push notifications, email alerts, or SMS reminders.\n\n"
        "Make sure notifications are allowed on your device."
    )


def fmt_leave_queue() -> str:
    return (
        "To **cancel or leave a queue**:\n\n"
        "1️⃣ Open your **Active Ticket** from the dashboard\n"
        "2️⃣ Tap **Cancel Ticket**\n"
        "3️⃣ Confirm cancellation\n\n"
        "⚠️ Once cancelled, your position is released and cannot be restored."
    )


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------

def call_ollama(messages: list[dict]) -> str:
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":    MODEL_NAME,
                "messages": messages,
                "stream":   False,
                "options":  {
                    "temperature": OLLAMA_TEMPERATURE,
                    "num_predict": OLLAMA_MAX_TOKENS,
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )
        if response.status_code == 200:
            return response.json().get("message", {}).get("content", "").strip()
        print(f"[Ollama] Non-200 status: {response.status_code}")
    except requests.exceptions.Timeout:
        return "⚠️ The AI took too long to respond. Please try again."
    except requests.exceptions.ConnectionError:
        return "⚠️ I can't reach the AI service right now. Please try again in a moment."
    except Exception as e:
        print(f"[Ollama] Unexpected error: {e}")
    return ""


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _init_user(user_key: str) -> None:
    if user_key not in conversation_memory:
        conversation_memory[user_key] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_key not in last_dept_mentioned:
        last_dept_mentioned[user_key] = None


def _save_turn(user_key: str, user_msg: str, bot_msg: str) -> None:
    mem = conversation_memory[user_key]
    mem.append({"role": "user",      "content": user_msg})
    mem.append({"role": "assistant", "content": bot_msg})
    if len(mem) > MAX_HISTORY * 2 + 1:
        conversation_memory[user_key] = [mem[0]] + mem[-(MAX_HISTORY * 2):]


def _ollama_messages(user_key: str, user_msg: str) -> list[dict]:
    mem     = conversation_memory[user_key]
    trimmed = [mem[0]] + mem[-(LLM_HISTORY_WINDOW * 2):]
    trimmed.append({"role": "user", "content": user_msg})
    return trimmed


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str
    userId:   Optional[str] = "anonymous"
    role:     Optional[str] = "guest"


# ---------------------------------------------------------------------------
# Quick-reply options
# ---------------------------------------------------------------------------

QUICK_OPTIONS = [
    {"label": "🎟️ My Ticket",    "value": "my ticket status"},
    {"label": "🏢 Departments",   "value": "list departments"},
    {"label": "➕ Join Queue",    "value": "how do I join a queue"},
    {"label": "📊 Wait Times",    "value": "average wait time for cse"},
    {"label": "🕐 Busy Hours",    "value": "when is cse least crowded"},
    {"label": "🔔 Notifications", "value": "how do notifications work"},
    {"label": "❓ Other",         "value": "other"},
]


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(data: ChatRequest):
    user_key = data.userId or "anonymous"
    question = data.question.strip()

    _init_user(user_key)

    classified = classify_intent(question)
    intent     = classified.intent

    if classified.dept_hint:
        last_dept_mentioned[user_key] = classified.dept_hint

    reply = ""

    # ── 1. Identity ───────────────────────────────────────────────────────────
    if intent == Intent.IDENTITY:
        reply = (
            "I'm the **Campus Assistant AI** 👋 — your smart guide for the Campus Queue system.\n\n"
            "I can help you:\n"
            "🎟️ Check ticket status • 🏢 Browse departments\n"
            "➕ Join queues • 📊 See wait times & busy hours\n"
            "🔔 Manage notifications • ⭐ Leave reviews\n\n"
            "What can I help you with today?"
        )

    # ── 2. Greeting ───────────────────────────────────────────────────────────
    elif intent == Intent.GREETING:
        reply = (
            "Hello! 👋 I'm your Campus Queue Assistant. "
            "I can check queues, guide you through joining, show wait times, and more! "
            "What do you need today?"
        )

    # ── 3. Acknowledgement ────────────────────────────────────────────────────
    elif intent == Intent.ACKNOWLEDGEMENT:
        reply = "👍 Got it! Anything else I can help you with?"

    # ── 4. Decline ────────────────────────────────────────────────────────────
    elif intent == Intent.DECLINE:
        reply = "No problem! Come back anytime you need queue help. 😊"

    # ── 5. Other prompt ───────────────────────────────────────────────────────
    elif intent == Intent.OTHER_PROMPT:
        reply = (
            "Sure! Here are some things you can ask me:\n\n"
            "🎟️ *\"What's my ticket status?\"*\n"
            "🏢 *\"List all departments\"*\n"
            "➕ *\"How do I join the CSE queue?\"*\n"
            "📊 *\"Average wait time for ECE\"*\n"
            "🕐 *\"When is Admin least crowded?\"*\n"
            "🔔 *\"How do notifications work?\"*\n"
            "⭐ *\"How do I leave a review?\"*\n\n"
            "What would you like to know?"
        )

    # ── 6. Ticket status — DB only ────────────────────────────────────────────
    elif intent == Intent.TICKET_STATUS:
        ticket    = await db_get_ticket(data.userId, data.role)
        dept_name = "your department"
        if ticket:
            queue = await db.queues.find_one({"_id": ticket.get("queue")})
            if queue:
                dept = await db.departments.find_one({"_id": queue.get("department")})
                if dept:
                    dept_name = dept.get("name", dept_name)
        is_join = any(k in question.lower() for k in ["join", "joining"])
        reply = fmt_ticket_status(ticket, data.userId, is_join, dept_name)

    # ── 7. Department list — DB only ──────────────────────────────────────────
    elif intent == Intent.DEPT_LIST:
        names = await db_get_department_list()
        reply = fmt_dept_list(names)

    # ── 8. Join queue — department specified ──────────────────────────────────
    elif intent == Intent.JOIN_QUEUE_DEPT:
        dept_hint = classified.dept_hint or last_dept_mentioned.get(user_key)
        data_row  = await db_get_queue_status(dept_hint)
        reply     = fmt_join_with_dept(data_row, dept_hint)

    # ── 9. Join queue — generic "how to" ──────────────────────────────────────
    elif intent == Intent.JOIN_QUEUE_HOW:
        reply = fmt_join_how()

    # ── 10. Can't join — troubleshooting ──────────────────────────────────────
    elif intent == Intent.CANT_JOIN:
        dept_hint = classified.dept_hint or last_dept_mentioned.get(user_key)
        data_row  = await db_get_queue_status(dept_hint)
        reply     = fmt_cant_join(data_row, dept_hint)

    # ── 11. Queue status — DB only ────────────────────────────────────────────
    elif intent == Intent.QUEUE_STATUS:
        dept_hint = classified.dept_hint or last_dept_mentioned.get(user_key)
        data_row  = await db_get_queue_status(dept_hint)
        reply     = fmt_queue_status(data_row, dept_hint, question)

    # ── 12. Complaint ─────────────────────────────────────────────────────────
    elif intent == Intent.COMPLAINT:
        reply = fmt_complaint()

    # ── 13. Review / feedback ─────────────────────────────────────────────────
    elif intent == Intent.REVIEW:
        reply = fmt_review()

    # ── 14. Emergency queue ───────────────────────────────────────────────────
    elif intent == Intent.EMERGENCY_QUEUE:
        reply = fmt_emergency_queue()

    # ── 15. Notifications ─────────────────────────────────────────────────────
    elif intent == Intent.NOTIFICATION:
        reply = fmt_notification()

    # ── 16. Leave / cancel queue ──────────────────────────────────────────────
    elif intent == Intent.LEAVE_QUEUE:
        reply = fmt_leave_queue()

    # ── 17. Analytics — DB only ───────────────────────────────────────────────
    elif intent == Intent.ANALYTICS:
        dept_hint       = classified.dept_hint or last_dept_mentioned.get(user_key)
        analytics_reply = await analytics_handler.handle(
            question,
            dept_hint_override=dept_hint,
        )
        reply = analytics_reply or (
            "I couldn't find analytics data for that. "
            "Try: *\"average wait time for CSE\"* or *\"when is Admin least crowded?\"*"
        )

    # ── 18. General LLM fallback ──────────────────────────────────────────────
    elif intent == Intent.GENERAL_LLM:
        messages     = _ollama_messages(user_key, question)
        ollama_reply = call_ollama(messages)
        reply        = ollama_reply or (
            "I'm not sure about that one. "
            "Try asking me about ticket statuses, department queues, or wait times!"
        )

    _save_turn(user_key, question, reply)

    return {"answer": reply, "options": QUICK_OPTIONS}


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)