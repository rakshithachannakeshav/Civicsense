import base64
import mimetypes
import sys
from typing import TypedDict, Literal

from pydantic import BaseModel
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, START, END


# =====================================================================
# Models
# =====================================================================
llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")


class Classification(BaseModel):
    category: Literal["road_damage", "garbage", "streetlight", "water_leak", "other"]
    severity: Literal["low", "medium", "high"]
    reason: str


classifier_llm = llm.with_structured_output(Classification)


# =====================================================================
# Department rules (made-up examples) -> searchable store
# =====================================================================
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

rules_store = InMemoryVectorStore.from_documents(
    [
        Document(page_content=r["text"],
                 metadata={k: v for k, v in r.items() if k != "text"})
        for r in RULES
    ],
    embeddings,
)


# =====================================================================
# Complaint memory (for duplicate detection). Empty at start.
# It lives in memory only, so it resets every run. A database comes later.
# =====================================================================
desc_store = InMemoryVectorStore(embeddings)   # what the problem is
loc_store = InMemoryVectorStore(embeddings)    # where it is
known_ids = []

DESC_T = 0.70   # issue similarity needed to count as the same problem
LOC_T = 0.75    # place similarity needed to count as the same place


# =====================================================================
# MAIN GRAPH: classify -> duplicate check -> route -> draft
# =====================================================================
class ComplaintState(TypedDict, total=False):
    text: str
    image_path: str
    location: str
    category: str
    severity: str
    reason: str
    complaint_id: str
    duplicate_of: str
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
    result = classifier_llm.invoke([build_message(state)])
    return {
        "category": result.category,
        "severity": result.severity,
        "reason": result.reason,
    }


def duplicate_check(state: ComplaintState):
    desc = state["reason"]
    loc = state.get("location", "unknown")
    cat = state["category"]
    desc_vec = embeddings.embed_query(desc)
    loc_vec = embeddings.embed_query(loc)

    candidates = desc_store.similarity_search_with_score_by_vector(
        desc_vec, k=5,
        filter=lambda d: d.metadata["category"] == cat,
    )
    for doc, d_score in candidates:
        cid = doc.metadata["id"]
        hits = loc_store.similarity_search_with_score_by_vector(
            loc_vec, k=1,
            filter=lambda d, i=cid: d.metadata["id"] == i,
        )
        l_score = hits[0][1]
        print(f"   [duplicate check] vs {cid}: "
              f"issue {d_score:.3f} | place {l_score:.3f}")
        if d_score >= DESC_T and l_score >= LOC_T:
            return {"duplicate_of": cid}

    # Not a duplicate: remember it for future complaints
    cid = f"C-{len(known_ids) + 1}"
    known_ids.append(cid)
    meta = {"id": cid, "category": cat}
    desc_store.add_documents([Document(page_content=desc, metadata=meta)])
    loc_store.add_documents([Document(page_content=loc, metadata=meta)])
    return {"complaint_id": cid, "duplicate_of": ""}


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
    doc, score = rules_store.similarity_search_with_score(
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
    response = llm.invoke(prompt)
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
# Demos
# =====================================================================
def run_demo():
    """Full pipeline on two complaints. Uses generate calls (2 to 3 per run)."""
    tests = [
        # 1. A new complaint, with a photo
        {"text": "Please look at this",
         "image_path": "pothole.jpg",
         "location": "80 Feet Road, Indiranagar, Bengaluru"},
        # 2. Another citizen, same photo and place, different words
        {"text": "Very dangerous pothole, someone will fall here",
         "image_path": "pothole.jpg",
         "location": "Outside the school gate, 80 Feet Road, Indiranagar"},
    ]

    for t in tests:
        print("=" * 60)
        print("Complaint:", t["text"])
        result = app.invoke(t)
        print(f"Category: {result['category']} | severity: {result['severity']}")
        if result.get("duplicate_of"):
            print("Result: DUPLICATE of", result["duplicate_of"])
            print(result["note"])
        elif result.get("letter"):
            print("Complaint ID:", result["complaint_id"])
            print("Routed to:", result["department"], "|", result["desk"],
                  "| SLA", result["sla_hours"], "h")
            print("Matched rule:", result["rule"])
            print()
            print(result["letter"])
        else:
            print(result.get("note"))


def simulate():
    """Follow-up agent on a simulated clock. Makes no model calls."""
    records = {
        "C-1": new_record("C-1", "Roads Dept", "Ward Engineer", 24),
        "C-2": new_record("C-2", "Solid Waste Dept", "Collection Desk", 48),
    }
    resolved_at = {"C-2": 45}   # C-1 is never resolved

    for hour in range(0, 85, 3):          # the "scheduler": a check every 3 hours
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