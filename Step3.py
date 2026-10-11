from typing import TypedDict, Literal
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

# What we want the model to give back: a fixed shape, not free text
class Classification(BaseModel):
    category: Literal["road_damage", "garbage", "streetlight", "water_leak", "other"]
    severity: Literal["low", "medium", "high"]
    reason: str

llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)
classifier_llm = llm.with_structured_output(Classification)

class ComplaintState(TypedDict, total=False):
    text: str
    category: str
    severity: str
    reason: str
    department: str
    note: str

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
graph.add_node("ask_for_details", ask_for_details)
graph.add_edge(START, "classifier")
graph.add_conditional_edges(
    "classifier",
    decide_next,
    {"router": "router", "ask_for_details": "ask_for_details"},
)
graph.add_edge("router", END)
graph.add_edge("ask_for_details", END)
app = graph.compile()

for text in [
    "Big crater near the school gate, two-wheelers keep skidding",
    "The lamp outside my building has been dark for a week",
    "Pipe burst near the bus stop, water everywhere",
    "something is wrong here",
]:
    print(text)
    print(app.invoke({"text": text}), "\n")