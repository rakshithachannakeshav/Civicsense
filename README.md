# CivicSense

A multi-agent system that triages civic complaints. A citizen submits a photo
and a short note, and the agents classify the issue, route it to the right
department and draft a formal complaint letter.

Built for the Agentic AI course (AAT) at BMSCE.

## How it works

```
START -> classifier -> router -> drafter -> END
              |
              +-> ask_for_details -> END   (when the issue is unclear)
```

- **Classifier** reads the text and the photo (Gemini, multimodal) and returns
  a category, a severity and a reason, as structured output.
- **Router** maps the category to a department.
- **Drafter** writes a formal letter. Its deadline depends on severity.
- **ask_for_details** handles complaints the classifier cannot place, instead
  of guessing a department.

Agents share one state object, passed through a LangGraph `StateGraph` with a
conditional edge after the classifier.

## Run it

```powershell
pip install langgraph langchain-google-genai
$env:GOOGLE_API_KEY = "your-key"
python Step5.py
```

Put a photo named `pothole.jpg` in the project folder. The `StepN.py` files
build the project in stages, from a keyword-based graph (Step 1) to the
multimodal version (Step 5).

## Roadmap

- [x] Graph, conditional routing, LLM classifier, drafting agent, photo input
- [ ] Department rules lookup (RAG)
- [ ] Duplicate complaint detection
- [ ] Follow-up and escalation agent
- [ ] Django API and React dashboard

## Note

Department names and rules are examples, not official data.