<<<<<<< HEAD
# ✈️ TripMate AI — A Multi-Agent Travel Planner with LangGraph

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.0.20-purple.svg)](https://langchain-ai.github.io/langgraph/)
[![Groq](https://img.shields.io/badge/Groq-LLM-orange.svg)](https://groq.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An open-source AI travel planner that turns a natural-language trip request into a practical travel plan with flight suggestions, hotel ideas, and a day-by-day itinerary. The project uses a multi-agent workflow built with LangGraph, LangChain, and FastAPI.

## 🌟 Why This Project?

Planning a trip usually means jumping between multiple websites, tools, and spreadsheets. This project brings that flow into one experience by combining:

- ✈️ A flight-search agent
- 🏨 A hotel-research agent
- 🗺️ An itinerary-planning agent
- 📝 A final response agent

All coordinated through a LangGraph workflow with **human-in-the-loop** capabilities for collecting missing information.

## ✨ Features

### Core Features
- ✈️ **Flight Research** — Real-time flight search using AviationStack API
- 🏨 **Hotel Suggestions** — Accommodation recommendations via Tavily search
- 🧠 **Multi-Agent Orchestration** — Coordinated workflow with LangGraph
- 📝 **Structured Itinerary** — Day-by-day travel plans with budget breakdowns
- 💾 **State Persistence** — Conversation memory using PostgreSQL checkpointer
- ⚡ **LLM-Powered** — Intelligent responses with Groq's Llama 3.3 70B

### User Experience
- 💬 **Chat Interface** — Natural conversation-style interaction
- 🔄 **Multi-Turn Conversations** — Maintains context across messages
- 📅 **Date Extraction** — Smart parsing of travel dates
- 🧠 **Human-in-the-Loop** — Asks for missing information (cities, budget, dates)
- 📊 **Budget Tables** — Clean, formatted budget breakdowns
- 📱 **Responsive Design** — Works on desktop and mobile
- 🌙 **Dark Theme** — Modern, eye-friendly UI

### Advanced Features
- 🔍 **Spell Checking** — Auto-corrects city name typos (e.g., "banglore" → "Bangalore")
- 📅 **Date Parsing** — Supports multiple date formats (DD Month YYYY, MM/DD/YYYY, etc.)
- 💰 **Budget Calculation** — Automatic budget allocation across categories
- 🗂️ **State Management** — PostgreSQL persistent conversation state
- 🔄 **Thread Management** — Maintains separate conversation threads

## 🛠️ Tech Stack

### Backend
- **Python 3.10+** — Core language
- **FastAPI** — Web framework with automatic OpenAPI docs
- **LangGraph** — Multi-agent workflow orchestration
- **LangChain** — LLM integration and tooling
- **Groq** — LLM provider (Llama 3.3 70B)
- **PostgreSQL** — Persistent state storage with `psycopg2`

### Frontend
- **HTML5 + CSS3** — Modern, responsive UI
- **JavaScript (ES6+)** — Interactive chat interface
- **Marked.js** — Markdown rendering
- **html2pdf.js** — PDF export functionality
- **Font Awesome** — Icon library

### APIs & Integrations
- **AviationStack API** — Real-time flight data
- **Tavily API** — Web search for hotels and information

## 📁 Project Structure

```text
tripmate-ai/
├── app.py                      # FastAPI application entry point
├── backend.py                  # LangGraph travel workflow
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables template
├── static/
│   ├── style.css              # Professional UI styling
│   ├── script.js              # Frontend chat logic
├── templates/
│   └── index.html             # Main chat interface
└── README.md                  
=======
# TripMate
>>>>>>> c097a787071ce1ba73227f23e65ebee6f009b336
