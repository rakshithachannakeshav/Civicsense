from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")

# Complaints already in the system: (category, location, description)
stored = [
    ("road_damage", "80 Feet Road, Indiranagar, near the school gate",
     "Deep pothole filled with water in the traffic lane"),
    ("garbage", "5th Cross, Jayanagar 4th Block",
     "Garbage not collected for four days"),
    ("water_leak", "Near the bus stop, Koramangala",
     "Pipe burst, water flooding the road"),
]

desc_docs, loc_docs = [], []
for i, (cat, loc, desc) in enumerate(stored):
    meta = {"id": f"C-{i + 1}", "category": cat}
    desc_docs.append(Document(page_content=desc, metadata=meta))
    loc_docs.append(Document(page_content=loc, metadata=meta))

desc_store = InMemoryVectorStore.from_documents(desc_docs, embeddings)
loc_store = InMemoryVectorStore.from_documents(loc_docs, embeddings)

new_complaints = [
    ("road_damage", "Outside the school gate on 80 Feet Road, Indiranagar",
     "Big crater with water in it, bikes are slipping"),
    ("garbage", "5th Cross, Jayanagar 4th Block",
     "Rubbish piling up since Friday, no pickup"),
    ("road_damage", "Church Street, Shivajinagar",
     "Deep pothole filled with water"),
    ("water_leak", "Near the bus stop, Koramangala",
     "Tap water has been dirty since morning"),
    ("streetlight", "MG Road, Bengaluru",
     "Street lamp not working"),
]

DESC_T = 0.75   # starting guesses: tune these from the printed scores
LOC_T = 0.80

for cat, loc, desc in new_complaints:
    print(desc, "|", loc)
    desc_vec = embeddings.embed_query(desc)
    loc_vec = embeddings.embed_query(loc)

    candidates = desc_store.similarity_search_with_score_by_vector(
        desc_vec, k=5,
        filter=lambda d, c=cat: d.metadata["category"] == c,
    )
    if not candidates:
        print("  -> no stored complaints in this category: NEW\n")
        continue

    verdict = "NEW"
    for doc, d_score in candidates:
        cid = doc.metadata["id"]
        _, l_score = loc_store.similarity_search_with_score_by_vector(
            loc_vec, k=1,
            filter=lambda d, i=cid: d.metadata["id"] == i,
        )[0]
        print(f"  vs {cid}: issue {round(d_score, 3)} | place {round(l_score, 3)}")
        if d_score >= DESC_T and l_score >= LOC_T:
            verdict = f"DUPLICATE of {cid}"
    print("  ->", verdict, "\n")