from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# 1. STATE: what the agents share
class ComplaintState(TypedDict, total=False):
    text: str
    category: str
    department: str

# 2. NODES: each returns only the fields it updates
def classifier(state: ComplaintState):
    text = state["text"].lower()
    if "pothole" in text or "road" in text:
        return {"category": "road_damage"}
    if "garbage" in text or "waste" in text:
        return {"category": "garbage"}
    return {"category": "other"}

def router(state: ComplaintState):
    mapping = {"road_damage": "Roads Dept", "garbage": "Solid Waste Dept"}
    return {"department": mapping.get(state["category"], "General Grievance Cell")}

# 3. EDGES: the order they run in
graph = StateGraph(ComplaintState)
graph.add_node("classifier", classifier)
graph.add_node("router", router)
graph.add_edge(START, "classifier")
graph.add_edge("classifier", "router")
graph.add_edge("router", END)

app = graph.compile()

result = app.invoke({"text": "Streetlight is broken"})
print(result)