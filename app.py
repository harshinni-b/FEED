from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as edoca_router


app = FastAPI(
	title="EDOCA Engineering Document Assurance API",
	version="0.1.0",
	description="Evidence-grounded engineering document consistency assurance API for the local EDOCA demo.",
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(edoca_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
	return {"status": "ok"}
