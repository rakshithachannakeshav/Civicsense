import base64
import mimetypes
from typing import TypedDict, Literal

from pydantic import BaseModel
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, START, END


# ---------- Department rules (made-up examples) ----------
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

docs = [
    Document(
        page_content=r["text"],
        metadata={k: v for k, v in r.items() if k != "text"},
    )
    for r in RULES
]

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
store = InMemoryVectorStore.from_documents(docs, embeddings)


# ---------- Model ----------
class Classification(BaseModel):
    category: Literal["road_damage", "garbage", "streetlight", "water_leak", "other"]
    severity: Literal["low", "medium", "high"]
    reason: str


llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)
classifier_llm = llm.with_structured_output(Classification)


# ---------- Shared state ----------
class ComplaintState(TypedDict, total=False):
    text: str
    image_path: str
    location: str
    category: str
    severity: str
    reason: str
    department: str
    desk: str          # NEW: which desk inside the department
    sla_hours: int     # NEW: deadline from the matched rule
    rule: str          # NEW: the rule text that matched (for transparency)
    note: str
    letter: str


# ---------- Agents ----------
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


# NEW: the router now searches the rules instead of using a dictionary
def router(state: ComplaintState):
    query = (
        f"{state['text']}. {state['reason']}. "
        f"Location: {state.get('location', 'unknown')}"
    )
    doc, score = store.similarity_search_with_score(
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


def decide_next(state: ComplaintState):
    return "ask_for_details" if state["category"] == "other" else "router"


# ---------- Graph ----------
graph = StateGraph(ComplaintState)
graph.add_node("classifier", classifier)
graph.add_node("router", router)
graph.add_node("drafter", drafter)
graph.add_node("ask_for_details", ask_for_details)

graph.add_edge(START, "classifier")
graph.add_conditional_edges(
    "classifier",
    decide_next,
    {"router": "router", "ask_for_details": "ask_for_details"},
)
graph.add_edge("router", "drafter")
graph.add_edge("drafter", END)
graph.add_edge("ask_for_details", END)

app = graph.compile()


# ---------- Test ----------
tests = [
    {"text": "Please look at this",
     "image_path": "pothole.jpg",
     "location": "80 Feet Road, Indiranagar, Bengaluru"},
    # {"text": "Pipe burst near the bus stop, water everywhere",
    #  "location": "Near the bus stop, Koramangala, Bengaluru"},
]

for t in tests:
    result = app.invoke(t)
    print("=" * 60)
    print(result["category"], "|", result["severity"])
    print("Routed to:", result["department"], "|", result.get("desk"),
          "| SLA", result.get("sla_hours"), "h")
    print("Matched rule:", result.get("rule"))
    print("Reason:", result.get("reason"))
    print()
    print(result.get("letter") or result.get("note"))