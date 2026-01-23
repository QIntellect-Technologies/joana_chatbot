# Joana Chatbot Project Analysis

## Overview
**Joana Chatbot** is a Flask-based web application designed to serve as an automated customer service agent for a fast food restaurant ("Joana Fastfood"). It integrates with WhatsApp (via Cloud API) to handle customer interactions, including ordering, menu browsing, and answering FAQs.

## Architecture
- **Backend Framework**: Python Flask
- **Data Storage**:
  - **Static Data**: Excel files (`Menu.xlsx`, `Branches.xlsx`) serve as the source of truth, converted to JSON (`menu.json`, `branches.json`) for the app.
  - **Dynamic Data**: `orders.db` (SQLite) is used for tracking orders.
- **AI & NLP**:
  - **OpenAI API**: Used for intelligent parsing of complex natural language food orders (e.g., "I want 2 burgers and a coke").
  - **Rule-Based/Fuzzy Matching**: `nlp_utils.py` uses keyword matching and fuzzy string matching (`difflib`) for high-level intent detection (greeting, menu request, etc.).
- **Integration**: Designed to interface with the WhatsApp Cloud API.

## Directory Structure
- **Root**:
  - `app.py`: The core application handling routes, WhatsApp webhooks, conversation flow, and business logic.
  - `nlp_utils.py`: Helper functions for language detection (Arabic/English) and intent classification.
  - `requirements.txt`: Project dependencies.
- **`data/`**:
  - Stores application data (Excel sources, JSON cache, SQLite database).
- **`templates/`**:
  - Contains `index.html`, likely a simple landing page or test interface.

## Key Functionality
1.  **Multi-Language Support**: Detects and supports both English and Arabic.
2.  **Order Processing**:
    - Supports specific item ordering.
    - Handles generic requests (e.g., "meals", "drinks") by guiding the user through category options.
    - Uses OpenAI to parse complex, multi-item messages with typo tolerance.
3.  **Customer Service**:
    - Provides branch locations and contact info.
    - Answers FAQs using a pre-defined JSON knowledge base.
4.  **Menu Management**:
    - Reads menu structure dynamically from Excel/JSON.

## Tech Stack
- **Languages**: Python, HTML/CSS
- **Libraries**:
  - `flask`, `flask-cors` (Web Server)
  - `openai` (AI Integration)
  - `pandas`, `openpyxl` (Data Processing)
  - `psycopg2-binary` (PostgreSQL driver - suggests potential for production DB upgrade)

## Observations & Recommendations
- **Monolithic `app.py`**: The main file is over 7000 lines long. It would benefit from refactoring into blueprints (e.g., `routes`, `bot_logic`, `services`) for better maintainability.
- **Data Persistence**: Currently uses SQLite (`orders.db`). For high-volume production use, migrating to PostgreSQL (indicated by requirements) is recommended.
- **Secrets Management**: Uses `.env` for API keys, which is good practice.
