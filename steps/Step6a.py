from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

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

queries = [
    ("road_damage", "Huge pothole on the main road near the flyover, buses slowing down"),
    ("road_damage", "Crater in our small residential lane where kids cycle"),
    ("water_leak", "Pipe burst, water gushing onto the road"),
    ("water_leak", "Tap water pressure has been very low since Monday"),
]

for category, query in queries:
    doc, score = store.similarity_search_with_score(
        query,
        k=1,
        filter=lambda d, c=category: d.metadata["category"] == c,
    )[0]
    print(query)
    print("  ->", doc.metadata["department"], "|", doc.metadata["desk"],
          "| SLA", doc.metadata["sla_hours"], "h | score", round(score, 3))
    print()