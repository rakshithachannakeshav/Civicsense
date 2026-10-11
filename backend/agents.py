import base64
import math
import mimetypes
import os
import sys
from functools import lru_cache
from typing import TypedDict, Literal

from pydantic import BaseModel
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, START, END


# =====================================================================
# Settings
# =====================================================================
# FAKE_LLM=1 replaces the classifier and drafter with simple rules, so you
# can build and test the web app without using generate quota.
# Embeddings are NOT faked: the duplicate check and department lookup
# still need GOOGLE_API_KEY.
FAKE_LLM = os.getenv("FAKE_LLM") == "1"

DESC_T = 0.70   # issue similarity needed to count as the same problem
LOC_T = 0.75    # place similarity needed to count as the same place


class Classification(BaseModel):
    category: Literal["road_damage", "garbage", "streetlight", "water_leak", "other"]
    severity: Literal["low", "medium", "high"]
    reason: str


# =====================================================================
# Lazy setup: nothing here calls an API until first use
# =====================================================================
@lru_cache(maxsize=None)
def get_llm():
    return ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)


@lru_cache(maxsize=None)
def get_classifier_llm():
    return get_llm().with_structured_output(Classification)


@lru_cache(maxsize=None)
def get_embeddings():
    return GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")


# Department rules (made-up examples)
RULES = [
    {"category": "road_damage", "department": "Roads Dept",
     "desk": "Major Roads Cell", "sla_hours": 24,
     "text": "Potholes, craters and damage on main arterial roads, ring roads, "
             "flyovers and bus routes with heavy traffic."},
    {"category": "road_damage", "department": "Roads Dept",
     "desk": "Ward Engineer", "sla_hours": 72,
     "text": "Potholes and damage on internal lanes, residential streets, "
             "cross roads and footpaths."},
    {"category": "garbage", "department": "Solid Waste Dept",
     "desk": "Collection Desk", "sla_hours": 48,
     "text": "Garbage not collected, missed door-to-door pickup, overflowing bins."},
    {"category": "garbage", "department": "Solid Waste Dept",
     "desk": "Bulk Waste Cell", "sla_hours": 72,
     "text": "Illegal dumping, construction debris, large piles of waste "
             "and dead animals on the road."},
    {"category": "streetlight", "department": "Street Lighting Dept",
     "desk": "Maintenance Desk", "sla_hours": 72,
     "text": "Street lamp not working, flickering light, dark road at night."},
    {"category": "water_leak", "department": "Water Supply Dept",
     "desk": "Emergency Desk", "sla_hours": 12,
     "text": "Burst pipes, water gushing onto the road, flooding "
             "and major leaks that waste large amounts of water."},
    {"category": "water_leak", "department": "Water Supply Dept",
     "desk": "Service Desk", "sla_hours": 72,
     "text": "Slow leaks, low water pressure, dirty or discoloured water, "
             "no supply to a house."},
]


@lru_cache(maxsize=None)
def get_rules_store():
    return InMemoryVectorStore.from_documents(
        [
            Document(page_content=r["text"],
                     metadata={k: v for k, v in r.items() if k != "text"})
            for r in RULES
        ],
        get_embeddings(),
    )


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# =====================================================================
# Fake versions (used only when FAKE_LLM=1)
# =====================================================================
def fake_classify(text: str) -> Classification:
    t = text.lower()
    if any(w in t for w in ["pothole", "crater", "road"]):
        category = "road_damage"
    elif any(w in t for w in ["garbage", "rubbish", "waste"]):
        category = "garbage"
    elif any(w in t for w in ["streetlight", "lamp", "light"]):
        category = "streetlight"
    elif any(w in t for w in ["pipe", "leak", "water"]):
        category = "water_leak"
    else:
        category = "other"
    high = any(w in t for w in ["dangerous", "school", "burst", "flood", "accident"])
    return Classification(
        category=category,
        severity="high" if high else "medium",
        reason=text,
    )


def fake_letter(state) -> str:
    return (
        f"[Date]\n\nTo: {state['desk']}, {state['department']}\n\n"
        f"Subject: {state['category'].replace('_', ' ').title()} at "
        f"{state.get('location', 'unknown')}\n\n"
        f"Dear Sir/Madam,\n\n{state['reason']}. "
        f"Please take action within {state['sla_hours']} hours.\n\n"
        f"Sincerely,\n[Citizen Name]\n\n(Sample letter: FAKE_LLM mode)"
    )


# =====================================================================
# MAIN GRAPH: classify -> duplicate check -> route -> draft
# =====================================================================
class ComplaintState(TypedDict, total=False):
    text: str
    image_path: str
    location: str
    complaint_id: str      # this complaint's own reference, e.g. C-7
    known: list            # earlier complaints to compare against (from the database)
    category: str
    severity: str
    reason: str
    duplicate_of: str
    desc_vec: list         # saved with the complaint for future comparisons
    loc_vec: list
    department: str
    desk: str
    sla_hours: int
    rule: str
    note: str
    letter: str


def build_message(state: ComplaintState):
    instructions = (
        "You triage civic complaints for an Indian city. "
        "Classify the complaint using BOTH the text and the photo if one is given. "
        "Use 'other' only if neither makes the issue clear."
    )
    content = [
        {"type": "text",
         "text": instructions + f"\n\nComplaint text: {state['text']}"}
    ]
    path = state.get("image_path")
    if path:
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
    return HumanMessage(content=content)


def classifier(state: ComplaintState):
    if FAKE_LLM:
        result = fake_classify(state["text"])
    else:
        result = get_classifier_llm().invoke([build_message(state)])
    return {
        "category": result.category,
        "severity": result.severity,
        "reason": result.reason,
    }


def duplicate_check(state: ComplaintState):
    embeddings = get_embeddings()
    desc_vec = embeddings.embed_query(state["reason"])
    loc_vec = embeddings.embed_query(state.get("location", "unknown"))
    cat = state["category"]

    for k in state.get("known", []):
        if k["category"] != cat:
            continue
        d_score = cosine(desc_vec, k["desc_vec"])
        l_score = cosine(loc_vec, k["loc_vec"])
        print(f"   [duplicate check] vs {k['ref']}: "
              f"issue {d_score:.3f} | place {l_score:.3f}")
        if d_score >= DESC_T and l_score >= LOC_T:
            return {"duplicate_of": k["ref"]}

    # Not a duplicate: hand the vectors back so the caller can save them
    return {"duplicate_of": "", "desc_vec": desc_vec, "loc_vec": loc_vec}


def link_duplicate(state: ComplaintState):
    return {
        "department": "Linked",
        "note": f"Duplicate of {state['duplicate_of']}. Added as a supporting "
                f"report. No new letter drafted.",
    }


def router(state: ComplaintState):
    query = (
        f"{state['text']}. {state['reason']}. "
        f"Location: {state.get('location', 'unknown')}"
    )
    doc, score = get_rules_store().similarity_search_with_score(
        query,
        k=1,
        filter=lambda d: d.metadata["category"] == state["category"],
    )[0]
    m = doc.metadata
    severity_cap = {"high": 24, "medium": 72, "low": 168}[state["severity"]]
    return {
        "department": m["department"],
        "desk": m["desk"],
        "sla_hours": min(m["sla_hours"], severity_cap),
        "rule": doc.page_content,
    }


def drafter(state: ComplaintState):
    if FAKE_LLM:
        return {"letter": fake_letter(state)}
    prompt = f"""Write a formal complaint letter to the {state['department']}, {state['desk']}.

Facts you may use:
- Issue type: {state['category']}
- Severity: {state['severity']}
- Location: {state.get('location', 'not provided')}
- Citizen's description: {state['text']}
- Assessment of the issue: {state['reason']}

Rules:
- Under 120 words, polite and direct.
- Ask for action within {state['sla_hours']} hours.
- Describe the problem using the assessment. Never write phrases like "look at this".
- Do not invent facts, names, dates or reference numbers.
- Use [Citizen Name] and [Date] as placeholders.
"""
    response = get_llm().invoke(prompt)
    return {"letter": str(response.text)}


def ask_for_details(state: ComplaintState):
    return {
        "department": "Pending",
        "note": "Could not tell the issue type. Ask the citizen for more details.",
    }


def after_classifier(state: ComplaintState):
    return "ask_for_details" if state["category"] == "other" else "duplicate_check"


def after_duplicate_check(state: ComplaintState):
    return "link_duplicate" if state.get("duplicate_of") else "router"


graph = StateGraph(ComplaintState)
graph.add_node("classifier", classifier)
graph.add_node("duplicate_check", duplicate_check)
graph.add_node("link_duplicate", link_duplicate)
graph.add_node("router", router)
graph.add_node("drafter", drafter)
graph.add_node("ask_for_details", ask_for_details)

graph.add_edge(START, "classifier")
graph.add_conditional_edges(
    "classifier",
    after_classifier,
    {"ask_for_details": "ask_for_details", "duplicate_check": "duplicate_check"},
)
graph.add_conditional_edges(
    "duplicate_check",
    after_duplicate_check,
    {"link_duplicate": "link_duplicate", "router": "router"},
)
graph.add_edge("router", "drafter")
graph.add_edge("drafter", END)
graph.add_edge("link_duplicate", END)
graph.add_edge("ask_for_details", END)

app = graph.compile()


def process_complaint(
    text: str,
    location: str = "",
    image_path: str | None = None,
    known: list | None = None,
    complaint_id: str = "C-new",
) -> dict:
    """The one function Django calls. Returns the final state as a dict.

    known: earlier complaints as dicts with keys ref, category, desc_vec, loc_vec.
    """
    state = {
        "text": text,
        "location": location or "unknown",
        "known": known or [],
        "complaint_id": complaint_id,
    }
    if image_path:
        state["image_path"] = image_path
    return app.invoke(state)


# =====================================================================
# FOLLOW-UP GRAPH: tracks deadlines, reminds, escalates
# One run of this graph = one check of one complaint.
# A scheduler calls it repeatedly; state is saved in between.
# =====================================================================
MAX_LEVEL = 2             # 0 = desk, 1 = department head, 2 = commissioner
ESCALATION_WINDOW = 12    # hours each higher authority gets (example value)


class FollowUpState(TypedDict, total=False):
    id: str
    department: str
    desk: str
    status: str       # open | resolved | closed | critical
    level: int
    window: int       # hours allowed at the current level
    due_hour: int
    reminded: bool
    now: int          # the clock, in hours since start (simulated)
    history: list


def holder(level, department, desk):
    if level == 0:
        return f"{desk} ({department})"
    if level == 1:
        return f"Head of {department}"
    return "Commissioner's Office"


def note(state, message):
    return state["history"] + [f"[hour {state['now']:>3}] {message}"]


def decide_action(state: FollowUpState):
    if state["status"] in ("closed", "critical"):
        return "idle"
    if state["status"] == "resolved":
        return "close"
    remaining = state["due_hour"] - state["now"]
    if remaining <= 0:
        return "escalate" if state["level"] < MAX_LEVEL else "alert_top"
    if remaining <= 0.25 * state["window"] and not state["reminded"]:
        return "remind"
    return "idle"


def close_complaint(state: FollowUpState):
    who = holder(state["level"], state["department"], state["desk"])
    return {"status": "closed",
            "history": note(state, f"Resolved. Closed (was with {who}).")}


def send_reminder(state: FollowUpState):
    who = holder(state["level"], state["department"], state["desk"])
    return {"reminded": True,
            "history": note(state, f"Reminder sent to {who}. "
                                   f"Due at hour {state['due_hour']}.")}


def escalate(state: FollowUpState):
    new_level = state["level"] + 1
    who = holder(new_level, state["department"], state["desk"])
    new_due = state["now"] + ESCALATION_WINDOW
    return {
        "level": new_level,
        "window": ESCALATION_WINDOW,
        "due_hour": new_due,
        "reminded": False,
        "history": note(state, f"OVERDUE. Escalated to {who}. "
                               f"New deadline: hour {new_due}."),
    }


def alert_top(state: FollowUpState):
    return {"status": "critical",
            "history": note(state, "Overdue at the top level. "
                                   "Flagged CRITICAL for manual action.")}


fu_graph = StateGraph(FollowUpState)
fu_graph.add_node("close_complaint", close_complaint)
fu_graph.add_node("send_reminder", send_reminder)
fu_graph.add_node("escalate", escalate)
fu_graph.add_node("alert_top", alert_top)
fu_graph.add_conditional_edges(
    START,
    decide_action,
    {
        "close": "close_complaint",
        "remind": "send_reminder",
        "escalate": "escalate",
        "alert_top": "alert_top",
        "idle": END,
    },
)
for _name in ["close_complaint", "send_reminder", "escalate", "alert_top"]:
    fu_graph.add_edge(_name, END)
followup_app = fu_graph.compile()


def new_record(cid, department, desk, sla_hours, created_hour=0):
    """What gets saved when a new complaint is routed (a database row later)."""
    return {
        "id": cid, "department": department, "desk": desk,
        "status": "open", "level": 0, "window": sla_hours,
        "due_hour": created_hour + sla_hours, "reminded": False,
        "history": [f"[hour {created_hour:>3}] Complaint filed. "
                    f"Due in {sla_hours} h."],
    }


# =====================================================================
# Command-line demos
#   python agents.py            full pipeline on four sample complaints
#   python agents.py followup   follow-up simulation (no model calls)
# =====================================================================
def run_demo():
    samples = [
        ("Huge pothole near the school gate, very dangerous",
         "80 Feet Road, Indiranagar, Bengaluru"),
        ("Dangerous pothole outside the school, bikes are slipping",
         "Outside the school gate, 80 Feet Road, Indiranagar"),
        ("Garbage not collected for four days",
         "5th Cross, Jayanagar 4th Block, Bengaluru"),
        ("something is wrong here", "unknown"),
    ]
    print("Mode:", "FAKE_LLM (rules)" if FAKE_LLM else "real model")
    known = []   # the demo's stand-in for the database
    for n, (text, location) in enumerate(samples, start=1):
        cid = f"C-{n}"
        print("=" * 60)
        print("Complaint:", text)
        result = process_complaint(text, location, known=known, complaint_id=cid)
        print(f"Category: {result['category']} | severity: {result['severity']}")
        if result.get("duplicate_of"):
            print("Result: DUPLICATE of", result["duplicate_of"])
        elif result.get("letter"):
            print("Complaint ID:", cid)
            print("Routed to:", result["department"], "|", result["desk"],
                  "| SLA", result["sla_hours"], "h")
            print()
            print(result["letter"])
            known.append({
                "ref": cid, "category": result["category"],
                "desc_vec": result["desc_vec"], "loc_vec": result["loc_vec"],
            })
        else:
            print(result.get("note"))


def simulate():
    records = {
        "C-1": new_record("C-1", "Roads Dept", "Ward Engineer", 24),
        "C-2": new_record("C-2", "Solid Waste Dept", "Collection Desk", 48),
    }
    resolved_at = {"C-2": 45}   # C-1 is never resolved

    for hour in range(0, 85, 3):
        for cid in list(records):
            rec = records[cid]
            if rec["status"] == "open" and hour >= resolved_at.get(cid, 10**9):
                rec["status"] = "resolved"
            records[cid] = followup_app.invoke({**rec, "now": hour})

    for cid, rec in records.items():
        print("=" * 60)
        print(cid, "| final status:", rec["status"])
        for line in rec["history"]:
            print("  ", line)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "followup":
        simulate()
    else:
        run_demo()