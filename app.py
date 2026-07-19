from pathlib import Path
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend import run_travel_agent

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0"
)


app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest):
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty."
                }
            )

        # Call the backend agent
        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id
        )

        # Prepare response with all fields from the enhanced backend
        response_content = {
            "success": True,
            "thread_id": result.get("thread_id"),
            "answer": result.get("answer", "No response generated."),
            "flight_results": result.get("flight_results", ""),
            "hotel_results": result.get("hotel_results", ""),
            "itinerary": result.get("itinerary", ""),
            "llm_calls": result.get("llm_calls", 0),
            "is_complete": result.get("is_complete", False),
            "missing_info": result.get("missing_info", [])
        }

        # Log the response for debugging
        print(f"📤 Response: is_complete={response_content['is_complete']}, missing={response_content['missing_info']}")

        return JSONResponse(content=response_content)

    except Exception as e:
        print("❌ ERROR:", e)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "answer": f"I apologize, but I encountered an error: {str(e)}",
                "is_complete": False,
                "missing_info": ["system_error"]
            }
        )


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "AI Travel Planner API is running",
        "version": "1.0.0"
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


@app.get("/api/thread/{thread_id}")
async def get_thread_state(thread_id: str):
    """Debug endpoint to check thread state"""
    try:
        from backend import travel_graph
        config = {"configurable": {"thread_id": thread_id}}
        state = travel_graph.get_state(config)
        
        if state and state.values:
            return JSONResponse({
                "success": True,
                "thread_id": thread_id,
                "state": {
                    "from_city": state.values.get("from_city"),
                    "to_city": state.values.get("to_city"),
                    "budget": state.values.get("budget"),
                    "duration": state.values.get("duration"),
                    "start_date": state.values.get("start_date"),
                    "end_date": state.values.get("end_date"),
                    "is_complete": state.values.get("is_complete", False),
                    "missing_info": state.values.get("missing_info", [])
                }
            })
        else:
            return JSONResponse({
                "success": False,
                "thread_id": thread_id,
                "message": "Thread not found or has no state"
            })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@app.get("/api/clear_thread/{thread_id}")
async def clear_thread_state(thread_id: str):
    """Clear thread state (for testing)"""
    try:
        from backend import travel_graph
        config = {"configurable": {"thread_id": thread_id}}
        # Get current state
        state = travel_graph.get_state(config)
        if state:
            # Update state with empty values
            travel_graph.update_state(
                config,
                {
                    "from_city": None,
                    "to_city": None,
                    "budget": None,
                    "duration": None,
                    "start_date": None,
                    "end_date": None,
                    "missing_info": [],
                    "is_complete": False
                }
            )
            return JSONResponse({
                "success": True,
                "thread_id": thread_id,
                "message": "Thread state cleared successfully"
            })
        else:
            return JSONResponse({
                "success": False,
                "thread_id": thread_id,
                "message": "Thread not found"
            })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",  # Changed to 0.0.0.0 to allow external access
        port=8000,
        reload=True
    )