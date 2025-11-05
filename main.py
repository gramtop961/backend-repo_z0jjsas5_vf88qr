import os
from datetime import datetime, timezone
from random import randint, sample
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, AnyHttpUrl, Field

from database import db, create_document, get_documents  # type: ignore

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
    """
    Execute a live update.
    NOTE: In this sandbox we simulate new results but we persist the run and rows in MongoDB if available.
    """
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

    response = LiveUpdateResponse(
        ok=True,
        message=f"{len(rows)} ligne(s) mises à jour dans '{payload.sheet_tab}'.",
        updated_count=len(rows),
        rows=rows,
    )

    # Persist run + results if DB available
    try:
        if db is not None:
            from schemas import Run, Result  # type: ignore
            run_doc = Run(
                athlete_url=payload.athlete_url,
                sheet_url=payload.sheet_url,
                sheet_tab=payload.sheet_tab,
                ok=response.ok,
                message=response.message,
                updated_count=response.updated_count,
            )
            run_id = create_document("run", run_doc)
            for r in rows:
                res_doc = Result(
                    run_id=run_id,
                    row_number=r.row_number,
                    event=r.event,
                    date=r.date,
                    old_time=r.old_time,
                    new_time=r.new_time,
                    delta=r.delta,
                )
                create_document("result", res_doc)
    except Exception as e:
        # If database is not configured, keep working without persistence
        pass

    return response


@app.get("/runs")
def list_runs(limit: int = 10):
    """Return recent runs (most recent first) if DB is available."""
    if db is None:
        return {"ok": False, "message": "Database not configured", "runs": []}
    try:
        runs = get_documents("run", {}, limit=limit)
        # Sort by created_at desc if available
        runs.sort(key=lambda d: d.get("created_at", datetime.min), reverse=True)
        # Transform ObjectId
        for r in runs:
            if "_id" in r:
                r["id"] = str(r.pop("_id"))
        return {"ok": True, "runs": runs}
    except Exception as e:
        return {"ok": False, "message": str(e), "runs": []}


@app.get("/runs/{run_id}/rows")
def get_run_rows(run_id: str):
    """Return stored rows for a specific run if DB is available."""
    if db is None:
        return {"ok": False, "message": "Database not configured", "rows": []}
    try:
        from bson import ObjectId  # type: ignore
        rows = get_documents("result", {"run_id": run_id})
        for r in rows:
            if "_id" in r:
                r["id"] = str(r.pop("_id"))
        return {"ok": True, "rows": rows}
    except Exception as e:
        return {"ok": False, "message": str(e), "rows": []}


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
