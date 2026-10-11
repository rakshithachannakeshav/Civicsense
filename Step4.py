from typing import TypedDict, Literal
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

class Classification(BaseModel):
    category: Literal["road_damage", "garbage", "streetlight", "water_leak", "other"]
    severity: Literal["low", "medium", "high"]
    reason: str

llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)
classifier_llm = llm.with_structured_output(Classification)

class ComplaintState(TypedDict, total=False):
    text: str
    location: str      # NEW: where the problem is
    category: str
    severity: str
    reason: str
    department: str
    note: str
    letter: str        # NEW: the drafted complaint

def classifier(state: ComplaintState):
    prompt = (
        "You triage civic complaints for an Indian city. "
        "Classify this complaint. Use 'other' if the issue is unclear.\n\n"
        f"Complaint: {state['text']}"
    )
    result = classifier_llm.invoke(prompt)
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

# NEW: the second AI agent
def drafter(state: ComplaintState):
    prompt = f"""Write a formal complaint letter to the {state['department']}.

Facts you may use:
- Issue type: {state['category']}
- Severity: {state['severity']}
- Location: {state.get('location', 'not provided')}
- Citizen's description: {state['text']}

Rules:
- Under 120 words, polite and direct.
- Ask for action within a timeframe that matches the severity
  (high: 24 hours, medium: 3 days, low: 7 days).
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

graph = StateGraph(ComplaintState)
graph.add_node("classifier", classifier)
graph.add_node("router", router)
graph.add_node("drafter", drafter)                 # NEW
graph.add_node("ask_for_details", ask_for_details)

graph.add_edge(START, "classifier")
graph.add_conditional_edges(
    "classifier",
    decide_next,
    {"router": "router", "ask_for_details": "ask_for_details"},
)
graph.add_edge("router", "drafter")                # NEW: was router -> END
graph.add_edge("drafter", END)                     # NEW
graph.add_edge("ask_for_details", END)
app = graph.compile()

tests = [
    {"text": "Big crater near the school gate, two-wheelers keep skidding",
     "location": "Near Govt. High School, 80 Feet Road, Indiranagar, Bengaluru"},
    {"text": "Garbage has not been collected on our street for four days",
     "location": "5th Cross, Jayanagar 4th Block, Bengaluru"},
    {"text": "something is wrong here",
     "location": "unknown"},
]

for t in tests:
    result = app.invoke(t)
    print("=" * 60)
    print(result["category"], "|", result["severity"], "|", result["department"])
    print(result.get("letter") or result.get("note"))