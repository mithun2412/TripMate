import os 
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated, Optional, Dict, Any
import operator
import uuid
import re
import json
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=GROQ_API_KEY
)


# =========================
# State with Dates
# =========================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    from_city: Optional[str]
    to_city: Optional[str]
    budget: Optional[int]
    duration: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    missing_info: list[str]
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
    is_complete: bool


# =========================
# Common City Names for Spell Checking
# =========================

CITY_VARIATIONS = {
    'bangalore': ['bangalore', 'banglore', 'bengaluru', 'blr'],
    'mumbai': ['mumbai', 'bombay', 'bom'],
    'delhi': ['delhi', 'new delhi', 'del'],
    'pune': ['pune', 'puna'],
    'goa': ['goa'],
    'jaipur': ['jaipur', 'jpr'],
    'chennai': ['chennai', 'madras', 'chn'],
    'kochi': ['kochi', 'cochin', 'cok'],
    'hyderabad': ['hyderabad', 'secunderabad', 'hyd'],
    'ahmedabad': ['ahmedabad', 'amd'],
    'kolkata': ['kolkata', 'calcutta', 'kol'],
    'surat': ['surat'],
    'lucknow': ['lucknow', 'lko'],
    'patna': ['patna'],
    'indore': ['indore'],
    'bhopal': ['bhopal'],
    'visakhapatnam': ['visakhapatnam', 'vizag'],
    'vadodara': ['vadodara', 'baroda'],
    'nagpur': ['nagpur'],
    'rajkot': ['rajkot'],
    'mysore': ['mysore', 'mysuru'],
    'trivandrum': ['trivandrum', 'thiruvananthapuram', 'tvm'],
    'coimbatore': ['coimbatore', 'cbe'],
    'madurai': ['madurai'],
    'nashik': ['nashik'],
    'aurangabad': ['aurangabad'],
    'jodhpur': ['jodhpur'],
    'udaipur': ['udaipur'],
    'amritsar': ['amritsar'],
    'chandigarh': ['chandigarh'],
    'agra': ['agra'],
    'varanasi': ['varanasi', 'banaras'],
}

REVERSE_CITY_MAP = {}
for standard, variations in CITY_VARIATIONS.items():
    for var in variations:
        REVERSE_CITY_MAP[var] = standard

def normalize_city_name(city: str) -> str:
    """Normalize city name to standard spelling"""
    if not city:
        return None
    city_lower = city.lower().strip()
    if city_lower in REVERSE_CITY_MAP:
        return REVERSE_CITY_MAP[city_lower].title()
    for var, standard in REVERSE_CITY_MAP.items():
        if var in city_lower or city_lower in var:
            return standard.title()
    return city.title()


# =========================
# Date Extraction
# =========================

def extract_dates(query: str) -> Dict[str, Any]:
    """Extract start and end dates from query"""
    dates = {
        "start_date": None,
        "end_date": None,
        "duration": None
    }
    
    month_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'october': 10, 'oct': 10,
        'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    
    def parse_date(text: str) -> str:
        text = text.lower().strip()
        
        match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})', text)
        if match:
            day = int(match.group(1))
            month = month_map.get(match.group(2), 1)
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        match = re.search(r'([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})', text)
        if match:
            month = month_map.get(match.group(1), 1)
            day = int(match.group(2))
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        return None
    
    date_range_patterns = [
        r'(?:from|between)\s+([\dA-Za-z\s,]+?)\s+(?:to|and)\s+([\dA-Za-z\s,]+?)(?:\s*[,.]|$)',
        r'([\dA-Za-z\s,]+?)\s+(?:to|->)\s+([\dA-Za-z\s,]+?)(?:\s*[,.]|$)',
    ]
    
    for pattern in date_range_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            start_text = match.group(1).strip()
            end_text = match.group(2).strip()
            
            start_parsed = parse_date(start_text)
            end_parsed = parse_date(end_text)
            
            if start_parsed:
                dates["start_date"] = start_parsed
            if end_parsed:
                dates["end_date"] = end_parsed
            break
    
    if not dates["start_date"]:
        from_match = re.search(r'(?:from|starting|start)\s+([\dA-Za-z\s,]+?)(?:\s*[,.]|$)', query, re.IGNORECASE)
        if from_match:
            parsed = parse_date(from_match.group(1).strip())
            if parsed:
                dates["start_date"] = parsed
    
    if not dates["end_date"]:
        to_match = re.search(r'(?:to|until|till)\s+([\dA-Za-z\s,]+?)(?:\s*[,.]|$)', query, re.IGNORECASE)
        if to_match:
            parsed = parse_date(to_match.group(1).strip())
            if parsed:
                dates["end_date"] = parsed
    
    duration_patterns = [
        r'(\d+)\s*(?:day|days|night|nights)',
        r'for\s*(\d+)\s*(?:day|days)',
        r'(\d+)\s*days?\s*(?:trip|itinerary)',
    ]
    for pattern in duration_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            dates["duration"] = int(match.group(1))
            break
    
    if dates["start_date"] and dates["duration"] and not dates["end_date"]:
        try:
            start = datetime.strptime(dates["start_date"], "%Y-%m-%d")
            end = start + timedelta(days=dates["duration"])
            dates["end_date"] = end.strftime("%Y-%m-%d")
        except:
            pass
    
    if dates["start_date"] and dates["end_date"] and not dates["duration"]:
        try:
            start = datetime.strptime(dates["start_date"], "%Y-%m-%d")
            end = datetime.strptime(dates["end_date"], "%Y-%m-%d")
            delta = (end - start).days
            if delta > 0:
                dates["duration"] = delta
        except:
            pass
    
    return dates


def extract_trip_info(query: str) -> Dict[str, Any]:
    """Extract trip information using LLM with fallback"""
    
    extraction_prompt = f"""
Extract the following travel information from this user query:
"{query}"

Return a JSON object with these fields:
- from_city: The departure city (or null if not specified)
- to_city: The destination city (or null if not specified)  
- budget: The budget amount in INR (or null if not specified)
- duration: Number of days for the trip (or null if not specified)
- start_date: Start date in YYYY-MM-DD format (or null if not specified)
- end_date: End date in YYYY-MM-DD format (or null if not specified)

Fix common spelling errors:
- "banglaor" or "banglore" → "Bangalore"
- "bombay" → "Mumbai"
- "madras" → "Chennai"
- "calcutta" → "Kolkata"
- "agust" → "August"

Return ONLY the JSON object, no other text.
"""

    try:
        response = llm.invoke([
            SystemMessage(content="You are a travel information extractor."),
            HumanMessage(content=extraction_prompt)
        ])
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            info = json.loads(json_match.group())
            return {
                "from_city": info.get("from_city"),
                "to_city": info.get("to_city"),
                "budget": info.get("budget"),
                "duration": info.get("duration"),
                "start_date": info.get("start_date"),
                "end_date": info.get("end_date")
            }
    except Exception as e:
        print(f"LLM Extraction error: {e}")
    
    return extract_with_regex(query)


def extract_with_regex(query: str) -> Dict[str, Any]:
    """Fallback extraction using regex patterns"""
    info = {
        "from_city": None,
        "to_city": None,
        "budget": None,
        "duration": None,
        "start_date": None,
        "end_date": None
    }
    
    clean_query = query.lower()
    
    city_patterns = [
        r'(?:from|between)\s+([A-Za-z\s]+?)\s+(?:to|and)\s+([A-Za-z\s]+?)(?:\s*[,.]|$)',
        r'([A-Za-z\s]+?)\s+to\s+([A-Za-z\s]+?)(?:\s*[,.]|$)',
        r'(?:travel|trip|go|plan)\s+(?:from|between)\s+([A-Za-z\s]+?)\s+(?:to|and)\s+([A-Za-z\s]+?)(?:\s*[,.]|$)',
    ]
    
    for pattern in city_patterns:
        match = re.search(pattern, clean_query, re.IGNORECASE)
        if match and len(match.groups()) == 2:
            info["from_city"] = normalize_city_name(match.group(1).strip())
            info["to_city"] = normalize_city_name(match.group(2).strip())
            break
    
    budget_patterns = [
        r'budget\s*(?:of\s*)?[₹RsINR]+\s*([\d,]+)',
        r'[₹RsINR]+\s*([\d,]+)\s*(?:budget|approx)',
        r'under\s*[₹RsINR]+\s*([\d,]+)',
        r'₹\s*([\d,]+)',
        r'rs\.?\s*([\d,]+)',
    ]
    
    for pattern in budget_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            try:
                value = int(match.group(1).replace(',', ''))
                info["budget"] = value
                break
            except:
                continue
    
    dates = extract_dates(query)
    info["start_date"] = dates.get("start_date")
    info["end_date"] = dates.get("end_date")
    info["duration"] = dates.get("duration")
    
    return info


def check_missing_info(info: Dict[str, Any]) -> list[str]:
    """Check what information is missing"""
    missing = []
    
    if not info.get("from_city"):
        missing.append("departure city")
    if not info.get("to_city"):
        missing.append("destination city")
    if not info.get("budget"):
        missing.append("budget")
    if not info.get("duration"):
        missing.append("duration")
    if not info.get("start_date"):
        missing.append("start date")
    if not info.get("end_date"):
        missing.append("end date")
    
    return missing


def merge_extracted_info(existing_info: Dict[str, Any], new_info: Dict[str, Any]) -> Dict[str, Any]:
    """Merge existing info with new info"""
    merged = existing_info.copy() if existing_info else {}
    
    for key in ["from_city", "to_city", "budget", "duration", "start_date", "end_date"]:
        new_val = new_info.get(key)
        if new_val is not None and new_val != "":
            merged[key] = new_val
        elif key not in merged:
            merged[key] = None
    
    if merged.get("start_date") and merged.get("end_date") and not merged.get("duration"):
        try:
            start = datetime.strptime(merged["start_date"], "%Y-%m-%d")
            end = datetime.strptime(merged["end_date"], "%Y-%m-%d")
            delta = (end - start).days
            if delta > 0:
                merged["duration"] = delta
        except:
            pass
    
    if merged.get("start_date") and merged.get("duration") and not merged.get("end_date"):
        try:
            start = datetime.strptime(merged["start_date"], "%Y-%m-%d")
            end = start + timedelta(days=merged["duration"])
            merged["end_date"] = end.strftime("%Y-%m-%d")
        except:
            pass
    
    return merged


def generate_clarification(missing_info: list[str], existing_info: Dict[str, Any]) -> str:
    """Generate clarification prompt based on missing information"""
    
    from_city = existing_info.get("from_city")
    to_city = existing_info.get("to_city")
    budget = existing_info.get("budget")
    duration = existing_info.get("duration")
    start_date = existing_info.get("start_date")
    end_date = existing_info.get("end_date")
    
    context_parts = []
    if from_city and to_city:
        context_parts.append(f"from {from_city} to {to_city}")
    if budget:
        context_parts.append(f"with budget ₹{budget}")
    if duration:
        context_parts.append(f"for {duration} days")
    if start_date:
        context_parts.append(f"starting {start_date}")
    if end_date:
        context_parts.append(f"ending {end_date}")
    
    context = " ".join(context_parts) if context_parts else ""
    
    if from_city and to_city and budget and duration and not start_date and not end_date:
        return f"""📍 Great! I have your trip details:
{context}

Now I just need your travel dates:
1. **Start date** (e.g., 5 August 2026)
2. **End date** (e.g., 9 August 2026)

Example: "from 5 August 2026 to 9 August 2026" """
    
    if from_city and to_city and budget and start_date and end_date and not duration:
        return f"""📍 Great! I have your trip details:
{context}

How many days would you like to spend on this trip?

Example: "5 days" """
    
    if from_city and to_city and not budget and not start_date and not end_date:
        return f"""📍 Great! I have your route from {from_city} to {to_city}.

Now I need:
1. **What's your budget?** (e.g., ₹20,000)
2. **Travel dates** (e.g., from 5 August 2026 to 9 August 2026)

You can provide all at once: "₹20,000 from 5 August to 9 August" """
    
    if "departure city" in missing_info and "destination city" in missing_info:
        return """🌏 I'd love to help you plan your trip!

Please tell me:
1. **Which city are you departing from?** (e.g., Bangalore, Delhi, Mumbai)
2. **Where would you like to go?** (e.g., Pune, Goa, Jaipur)

Example: "I want to travel from Bangalore to Goa" """
    
    if "budget" in missing_info:
        return f"""💰 I'm working on your {from_city} → {to_city} trip!

Could you please let me know your budget?

Example: "₹20,000" """
    
    if "duration" in missing_info:
        return f"""📅 How many days would you like to spend on this trip?

Example: "5 days" """
    
    if "start_date" in missing_info:
        return f"""📅 When would you like to start your trip?

Example: "5 August 2026" """
    
    if "end_date" in missing_info:
        return f"""📅 When would you like to end your trip?

Example: "9 August 2026" """
    
    return f"I need more information. Could you please provide the missing details? Missing: {', '.join(missing_info)}"


# =========================
# Flight Agent
# =========================

def flight_agent(state: TravelState):
    if not state.get("is_complete", False):
        return {
            "flight_results": "INCOMPLETE_INFO",
            "messages": [AIMessage(content="Waiting for complete information.")],
            "llm_calls": state.get("llm_calls", 0) + 1
        }
    
    try:
        from_city = state.get("from_city", "")
        to_city = state.get("to_city", "")
        start_date = state.get("start_date", "")
        end_date = state.get("end_date", "")
        
        query = f"flights from {from_city} to {to_city}"
        if start_date:
            query += f" on {start_date}"
        if end_date:
            query += f" to {end_date}"
        
        flight_data = search_flights(query)
    except Exception as e:
        flight_data = f"Flight search unavailable. Error: {str(e)}"
    
    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight results fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    if not state.get("is_complete", False):
        return {
            "hotel_results": "INCOMPLETE_INFO",
            "messages": [AIMessage(content="Waiting for complete information.")],
            "llm_calls": state.get("llm_calls", 0) + 1
        }
    
    to_city = state.get("to_city", "")
    budget = state.get("budget", "")
    query = f"Best budget hotels in {to_city} under ₹{budget}"
    try:
        hotel_results = tavily_search(query)
    except Exception as e:
        hotel_results = f"Hotel search unavailable. Error: {str(e)}"
    
    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Itinerary Agent
# =========================

def itinerary_agent(state: TravelState):
    if not state.get("is_complete", False):
        return {
            "itinerary": "INCOMPLETE_INFO",
            "messages": [AIMessage(content="Waiting for complete information.")],
            "llm_calls": state.get("llm_calls", 0) + 1
        }
    
    prompt = f"""
Create a complete travel itinerary with cheapest flights and hotels.

From: {state.get('from_city', 'Not specified')}
To: {state.get('to_city', 'Not specified')}
Budget: ₹{state.get('budget', 'Not specified')}
Duration: {state.get('duration', 'Not specified')} days
Start Date: {state.get('start_date', 'Not specified')}
End Date: {state.get('end_date', 'Not specified')}

Flight Results: {state['flight_results']}
Hotel Results: {state['hotel_results']}

Focus on finding the cheapest options within the budget.
"""

    try:
        response = llm.invoke([
            SystemMessage(content="You are an expert travel planner for India. Focus on finding the cheapest flights and hotels."),
            HumanMessage(content=prompt)
        ])
        itinerary_content = response.content
    except Exception as e:
        itinerary_content = f"Itinerary generation unavailable. Error: {str(e)}"
    
    return {
        "itinerary": itinerary_content,
        "messages": [AIMessage(content="Itinerary created.")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Final Response Agent - WITH HARDCODED TABLE
# =========================

def generate_budget_table(budget: int, flight_cost: int, hotel_cost: int, food_cost: int) -> str:
    """Generate a properly formatted Markdown budget table"""
    
    # Calculate totals
    subtotal = flight_cost + hotel_cost + food_cost
    remaining = budget - subtotal
    
    table = """
## 💰 Estimated Budget Breakdown

| Category | Cost (₹) |
|----------|----------|
| Flights | {flight:,} |
| Hotels | {hotel:,} |
| Food & Transport | {food:,} |
| **Subtotal** | **{subtotal:,}** |
| **Budget** | **{budget:,}** |
| **Remaining** | **{remaining:,}** |
""".format(
        flight=flight_cost,
        hotel=hotel_cost,
        food=food_cost,
        subtotal=subtotal,
        budget=budget,
        remaining=remaining
    )
    
    return table


def final_agent(state: TravelState):
    if not state.get("is_complete", False):
        missing = state.get("missing_info", [])
        existing_info = {
            "from_city": state.get("from_city"),
            "to_city": state.get("to_city"),
            "budget": state.get("budget"),
            "duration": state.get("duration"),
            "start_date": state.get("start_date"),
            "end_date": state.get("end_date")
        }
        response_content = generate_clarification(missing, existing_info)
        return {
            "messages": [AIMessage(content=response_content)],
            "llm_calls": state.get("llm_calls", 0) + 1
        }
    
    # Get state values
    from_city = state.get('from_city', 'Bangalore')
    to_city = state.get('to_city', 'Pune')
    budget = state.get('budget', 20000)
    duration = state.get('duration', 4)
    start_date = state.get('start_date', '2026-08-05')
    end_date = state.get('end_date', '2026-08-09')
    
    # Estimate costs (simplified)
    flight_cost = int(budget * 0.35)  # 35% for flights
    hotel_cost = int(budget * 0.25)   # 25% for hotels
    food_cost = int(budget * 0.30)    # 30% for food & transport
    
    # Generate the budget table
    budget_table = generate_budget_table(budget, flight_cost, hotel_cost, food_cost)
    
    # Get the rest of the response from LLM
    final_prompt = f"""
Generate a complete travel plan in proper Markdown format.

Trip Details:
- From: {from_city}
- To: {to_city}
- Budget: ₹{budget}
- Duration: {duration} days
- Start Date: {start_date}
- End Date: {end_date}

Flight Information: {state.get('flight_results', 'Searching for best flights...')}
Hotel Information: {state.get('hotel_results', 'Searching for best hotels...')}
Itinerary: {state.get('itinerary', 'Creating itinerary...')}

Create these sections using Markdown:
1. ## Trip Summary - Brief overview
2. ## Flight Information - Flight details with bullet points
3. ## Hotel Suggestions - Hotel options with bullet points
4. ## Day-by-Day Itinerary - Daily plan with bullet points
5. ## Final Recommendations - Tips with bullet points

Do NOT include a budget table or budget breakdown - I will add it separately.
Return ONLY the formatted response in proper Markdown.
"""

    try:
        response = llm.invoke([
            SystemMessage(content="You are a professional AI travel booking assistant. Respond in proper Markdown format."),
            HumanMessage(content=final_prompt)
        ])
        final_content = response.content
        
        # Clean up the content
        final_content = re.sub(r'##\s*Estimated Budget Breakdown.*?(?=##|$)', '', final_content, flags=re.DOTALL)
        final_content = re.sub(r'##\s*Budget Breakdown.*?(?=##|$)', '', final_content, flags=re.DOTALL)
        
        # Add the properly formatted budget table
        final_content = final_content.strip() + '\n\n' + budget_table
        
        # Clean up any remaining issues
        final_content = re.sub(r'\n{3,}', '\n\n', final_content)
        
    except Exception as e:
        final_content = f"Error generating plan: {str(e)}"
    
    return {
        "messages": [AIMessage(content=final_content)],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Build Graph
# =========================

graph = StateGraph(TravelState)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    print(f"🔍 Processing with thread_id: {thread_id}")
    
    new_info = extract_trip_info(user_input)
    print(f"📥 New info extracted: {new_info}")
    
    existing_info = {}
    try:
        state_snapshot = travel_graph.get_state(config)
        
        if state_snapshot and state_snapshot.values:
            existing_info = {
                "from_city": state_snapshot.values.get("from_city"),
                "to_city": state_snapshot.values.get("to_city"),
                "budget": state_snapshot.values.get("budget"),
                "duration": state_snapshot.values.get("duration"),
                "start_date": state_snapshot.values.get("start_date"),
                "end_date": state_snapshot.values.get("end_date"),
            }
            print(f"📦 Existing state found: {existing_info}")
        else:
            print("📦 No existing state found, starting fresh")
    except Exception as e:
        print(f"⚠️ Could not retrieve state: {e}")
    
    merged_info = merge_extracted_info(existing_info, new_info)
    print(f"📊 Merged Info: {merged_info}")
    
    missing_info = check_missing_info(merged_info)
    is_complete = len(missing_info) == 0
    
    print(f"📊 Missing: {missing_info}")
    print(f"📊 Complete: {is_complete}")
    
    if not is_complete:
        try:
            state_update = {
                "user_query": user_input,
                "from_city": merged_info.get("from_city"),
                "to_city": merged_info.get("to_city"),
                "budget": merged_info.get("budget"),
                "duration": merged_info.get("duration"),
                "start_date": merged_info.get("start_date"),
                "end_date": merged_info.get("end_date"),
                "missing_info": missing_info,
                "is_complete": False,
                "messages": [HumanMessage(content=user_input)],
                "flight_results": "INCOMPLETE",
                "hotel_results": "INCOMPLETE",
                "itinerary": "INCOMPLETE",
                "llm_calls": 0
            }
            
            travel_graph.update_state(config, state_update)
            print(f"💾 State updated with partial info: {merged_info}")
        except Exception as e:
            print(f"⚠️ Error updating state: {e}")
        
        clarification = generate_clarification(missing_info, merged_info)
        return {
            "thread_id": thread_id,
            "answer": clarification,
            "flight_results": "INCOMPLETE",
            "hotel_results": "INCOMPLETE",
            "itinerary": "INCOMPLETE",
            "llm_calls": 0,
            "is_complete": False,
            "missing_info": missing_info
        }

    try:
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "from_city": merged_info.get("from_city"),
            "to_city": merged_info.get("to_city"),
            "budget": merged_info.get("budget"),
            "duration": merged_info.get("duration"),
            "start_date": merged_info.get("start_date"),
            "end_date": merged_info.get("end_date"),
            "missing_info": [],
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0,
            "is_complete": True
        }
        
        result = travel_graph.invoke(initial_state, config=config)

        final_answer = result["messages"][-1].content

        return {
            "thread_id": thread_id,
            "answer": final_answer,
            "flight_results": result.get("flight_results", ""),
            "hotel_results": result.get("hotel_results", ""),
            "itinerary": result.get("itinerary", ""),
            "llm_calls": result.get("llm_calls", 0),
            "is_complete": True,
            "missing_info": []
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "thread_id": thread_id,
            "answer": f"Error: {str(e)}",
            "flight_results": "ERROR",
            "hotel_results": "ERROR",
            "itinerary": "ERROR",
            "llm_calls": 0,
            "is_complete": False,
            "missing_info": ["information unavailable"]
        }