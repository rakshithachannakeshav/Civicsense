import base64
import mimetypes
from typing import TypedDict, Literal

from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END


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
    image_path: str     # optional photo
    location: str
    category: str
    severity: str
    reason: str
    department: str
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


def router(state: ComplaintState):
    mapping = {
        "road_damage": "Roads Dept",
        "garbage": "Solid Waste Dept",
        "streetlight": "Street Lighting Dept",
        "water_leak": "Water Supply Dept",
    }
    return {"department": mapping[state["category"]]}


def drafter(state: ComplaintState):
    prompt = f"""Write a formal complaint letter to the {state['department']}.

Facts you may use:
- Issue type: {state['category']}
- Severity: {state['severity']}
- Location: {state.get('location', 'not provided')}
- Citizen's description: {state['text']}
-Assessment of the issue: {state['reason']}

Rules:
- Under 120 words, polite and direct.
- Ask for action within a timeframe that matches the severity
  (high: 24 hours, medium: 3 days, low: 7 days).
- Do not invent facts, names, dates or reference numbers.
- Use [Citizen Name] and [Date] as placeholders.
- Describe the problem using the assessment. Never write phrases like "look at this".
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
]

for t in tests:
    result = app.invoke(t)
    print("=" * 60)
    print(result["category"], "|", result["severity"], "|", result["department"])
    print("Reason:", result["reason"])
    print()
    print(result.get("letter") or result.get("note"))