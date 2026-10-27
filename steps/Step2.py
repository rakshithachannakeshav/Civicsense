from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class ComplaintState(TypedDict, total=False):
    text: str
    category: str
    department: str
    note: str            # NEW: a message for humans

def classifier(state: ComplaintState):
    text = state["text"].lower()
    if "pothole" in text or "road" in text:
        return {"category": "road_damage"}
    if "garbage" in text or "waste" in text:
        return {"category": "garbage"}
    return {"category": "other"}

def router(state: ComplaintState):
    mapping = {"road_damage": "Roads Dept", "garbage": "Solid Waste Dept"}
    return {"department": mapping[state["category"]]}

# NEW node: runs only when the classifier is unsure
def ask_for_details(state: ComplaintState):
    return {
        "department": "Pending",
        "note": "Could not tell the issue type. Ask the citizen for more details.",
    }

# NEW: the decision function. It returns the NAME of the next node.
def decide_next(state: ComplaintState):
    if state["category"] == "other":
        return "ask_for_details"
    return "router"

graph = StateGraph(ComplaintState)
graph.add_node("classifier", classifier)
graph.add_node("router", router)
graph.add_node("ask_for_details", ask_for_details)

graph.add_edge(START, "classifier")
graph.add_conditional_edges(          # NEW: replaces classifier -> router
    "classifier",
    decide_next,
    {"router": "router", "ask_for_details": "ask_for_details"},
)
graph.add_edge("router", END)
graph.add_edge("ask_for_details", END)

app = graph.compile()

for text in [
    "Huge pothole on 80 Feet Road",
    "garbage piled up near the park",
    "streetlight is broken",
]:
    print(app.invoke({"text": text}))