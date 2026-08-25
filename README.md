# EDOCA

EDOCA is an engineering document assurance MVP for reviewing EPC project documents against a shared plant knowledge model and producing evidence-backed findings for engineer review.

## MVP architecture

```text
14 EPC documents
				|
				v
ingestion -> engineering-aware chunking -> entity/relationship extraction
				|                                      |
				+------------------------------> Plant Knowledge Graph (NetworkX)
																					 + evidence index
																										 |
																										 v
																			hybrid retrieval -> assurance engines
																														|
																														v
																			GPT-4o reasoning -> findings -> review
```

The code is organized around replaceable interfaces so local implementations can later be swapped for Azure AI Document Intelligence, Azure AI Search, and Azure AI Foundry.

## Project layout

```text
app.py                  FastAPI application entrypoint
src/
	api/                  HTTP routes and request/response schemas
	ingestion/            File loading and document normalization
	knowledge/             Graph, evidence, entities, and relationships
	retrieval/             Local hybrid retrieval and provider ports
	assurance/             Deterministic engineering assurance checks
	reasoning/             LLM reasoning ports and finding models
	orchestration/         End-to-end workflow coordination
data/
	documents/             Source EPC documents
	processed/             Normalized and chunked artifacts
	seed/                  Sample data and graph seed inputs
test/                    Focused unit and API tests
```

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

The initial health endpoint is available at `http://127.0.0.1:8000/health`.
