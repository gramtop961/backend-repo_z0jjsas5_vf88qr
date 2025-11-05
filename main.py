import os
from datetime import datetime, timezone
from random import randint, sample
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, AnyHttpUrl, Field

app = FastAPI(title="SwimRank Updater API")

# CORS: allow all origins for sandbox/demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LiveUpdateRequest(BaseModel):
    athlete_url: AnyHttpUrl = Field(..., description="Swimrankings athlete profile URL")
    sheet_url: AnyHttpUrl = Field(..., description="Google Sheets document URL")
    sheet_tab: str = Field(..., min_length=1, description="Target sheet tab name")


class UpdatedRow(BaseModel):
    row_number: int
    event: str
    date: str
    old_time: Optional[str] = None
    new_time: str
    delta: Optional[str] = None


class LiveUpdateResponse(BaseModel):
    ok: bool
    message: str
    updated_count: int
    rows: List[UpdatedRow] = []


@app.get("/")
def read_root():
    return {"message": "SwimRank Updater backend ready"}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/live-update", response_model=LiveUpdateResponse)
def live_update(payload: LiveUpdateRequest):
    # Simulate a small, realistic set of updated rows
    events = [
        "50m Freestyle",
        "100m Freestyle",
        "200m Freestyle",
        "100m Backstroke",
        "200m Individual Medley",
    ]

    count = randint(1, 3)
    chosen = sample(events, k=count)

    rows: List[UpdatedRow] = []
    base_row = randint(4, 18)
    for idx, ev in enumerate(chosen):
        old_ms = randint(30000, 80000)
        gain_ms = randint(200, 1500)
        new_ms = old_ms - gain_ms
        def fmt(ms: int) -> str:
            s, ms_part = divmod(ms, 1000)
            m, s = divmod(s, 60)
            return f"{m}:{str(s).zfill(2)}.{str(ms_part).zfill(3)}"
        rows.append(UpdatedRow(
            row_number=base_row + idx,
            event=ev,
            date=datetime.now().strftime("%Y-%m-%d"),
            old_time=fmt(old_ms),
            new_time=fmt(new_ms),
            delta=f"-{gain_ms/1000:.2f}s",
        ))

    return LiveUpdateResponse(
        ok=True,
        message=f"{len(rows)} ligne(s) mises à jour dans '{payload.sheet_tab}'.",
        updated_count=len(rows),
        rows=rows,
    )


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db  # type: ignore
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "(env not set)"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:  # pragma: no cover
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except ImportError:
        response["database"] = "❌ Database module not found"
    except Exception as e:  # pragma: no cover
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Reconfirm environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
