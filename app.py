import os
import json
import sqlite3
from datetime import datetime, timedelta
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="BizAdvisor AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "openai/gpt-oss-120b"
CHAT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")

# =========================================================
# SESSION STATE
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None

if "selected_page" not in st.session_state:
    st.session_state.selected_page = "🏠 Dashboard"

if "business_profile" not in st.session_state:
    st.session_state.business_profile = {
        "name": "",
        "industry": "",
        "location": "",
        "budget": "",
        "stage": ""
    }

if "tool_business_description" not in st.session_state:
    st.session_state.tool_business_description = ""

if "tool_target_customers" not in st.session_state:
    st.session_state.tool_target_customers = ""

if "tool_business_goal" not in st.session_state:
    st.session_state.tool_business_goal = ""

if "tool_business_challenge" not in st.session_state:
    st.session_state.tool_business_challenge = ""

if "active_analysis_id" not in st.session_state:
    st.session_state.active_analysis_id = None

if "selected_tool" not in st.session_state:
    st.session_state.selected_tool = "📊 SWOT Analysis"

# Dashboard feature-card navigation
dashboard_action = st.query_params.get("dashboard_action")
dashboard_actions = {
    "ai_advisor": ("🤖 AI Advisor", None),
    "business_analysis": ("📊 Business Tools", "📊 SWOT Analysis"),
    "growth_strategy": ("📊 Business Tools", "🎯 Strategy Planner"),
    "business_ideas": ("📊 Business Tools", "💡 Business Idea Generator"),
    "marketing": ("📊 Business Tools", "📣 Marketing Advisor"),
    "risk_analysis": ("📊 Business Tools", "⚠️ Risk Analyzer")
}
if dashboard_action in dashboard_actions:
    selected_page, selected_tool = dashboard_actions[dashboard_action]
    st.session_state.selected_page = selected_page
    if selected_tool:
        st.session_state.selected_tool = selected_tool
    del st.query_params["dashboard_action"]


# =========================================================
# PERSISTENT CHAT HISTORY
# =========================================================

def get_db_connection():
    connection = sqlite3.connect(CHAT_DB)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_chat_database():
    connection = get_db_connection()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            messages TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0
        )
    """)
    conversation_columns = [row[1] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()]
    if "pinned" not in conversation_columns:
        connection.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS business_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            business_name TEXT,
            business_context TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0
        )
    """)
    analysis_columns = [row[1] for row in connection.execute("PRAGMA table_info(business_analyses)").fetchall()]
    if "pinned" not in analysis_columns:
        connection.execute("ALTER TABLE business_analyses ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    connection.commit()
    connection.close()

def create_conversation(title, messages):
    now = datetime.now().isoformat(timespec="seconds")
    connection = get_db_connection()
    cursor = connection.execute(
        "INSERT INTO conversations (title, messages, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, json.dumps(messages, ensure_ascii=False), now, now)
    )
    conversation_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return conversation_id

def update_conversation(conversation_id, messages, title=None):
    now = datetime.now().isoformat(timespec="seconds")
    connection = get_db_connection()
    if title is None:
        connection.execute(
            "UPDATE conversations SET messages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(messages, ensure_ascii=False), now, conversation_id)
        )
    else:
        connection.execute(
            "UPDATE conversations SET title = ?, messages = ?, updated_at = ? WHERE id = ?",
            (title, json.dumps(messages, ensure_ascii=False), now, conversation_id)
        )
    connection.commit()
    connection.close()

def load_conversation(conversation_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT id, title, messages FROM conversations WHERE id = ?",
        (conversation_id,)
    ).fetchone()
    connection.close()
    if row is None:
        return None
    try:
        messages = json.loads(row["messages"])
    except (json.JSONDecodeError, TypeError):
        messages = []
    return {"id": row["id"], "title": row["title"], "messages": messages}

def get_conversations():
    connection = get_db_connection()
    rows = connection.execute(
        "SELECT id, title, created_at, updated_at, pinned FROM conversations ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]

def rename_conversation(conversation_id, title):
    title = " ".join(title.strip().split())
    if not title:
        return
    connection = get_db_connection()
    connection.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title[:80], datetime.now().isoformat(timespec="seconds"), conversation_id)
    )
    connection.commit()
    connection.close()

def toggle_pin_conversation(conversation_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT pinned FROM conversations WHERE id = ?",
        (conversation_id,)
    ).fetchone()
    if row is not None:
        new_value = 0 if row["pinned"] else 1
        connection.execute(
            "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
            (new_value, datetime.now().isoformat(timespec="seconds"), conversation_id)
        )
    connection.commit()
    connection.close()

def delete_conversation(conversation_id):
    connection = get_db_connection()
    connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    connection.commit()
    connection.close()

def create_business_analysis(title, tool_type, business_name, business_context, result):
    now = datetime.now().isoformat(timespec="seconds")
    connection = get_db_connection()
    cursor = connection.execute(
        "INSERT INTO business_analyses (title, tool_type, business_name, business_context, result, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, tool_type, business_name, business_context, result, now, now)
    )
    analysis_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return analysis_id

def get_business_analyses():
    connection = get_db_connection()
    rows = connection.execute(
        "SELECT id, title, tool_type, business_name, created_at, updated_at, pinned FROM business_analyses ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]

def rename_business_analysis(analysis_id, title):
    title = " ".join(title.strip().split())
    if not title:
        return
    connection = get_db_connection()
    connection.execute(
        "UPDATE business_analyses SET title = ?, updated_at = ? WHERE id = ?",
        (title[:100], datetime.now().isoformat(timespec="seconds"), analysis_id)
    )
    connection.commit()
    connection.close()

def toggle_pin_business_analysis(analysis_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT pinned FROM business_analyses WHERE id = ?",
        (analysis_id,)
    ).fetchone()
    if row is not None:
        new_value = 0 if row["pinned"] else 1
        connection.execute(
            "UPDATE business_analyses SET pinned = ?, updated_at = ? WHERE id = ?",
            (new_value, datetime.now().isoformat(timespec="seconds"), analysis_id)
        )
    connection.commit()
    connection.close()

def load_business_analysis(analysis_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT id, title, tool_type, business_name, business_context, result, created_at, updated_at FROM business_analyses WHERE id = ?",
        (analysis_id,)
    ).fetchone()
    connection.close()
    if row is None:
        return None
    return dict(row)

def delete_business_analysis(analysis_id):
    connection = get_db_connection()
    connection.execute("DELETE FROM business_analyses WHERE id = ?", (analysis_id,))
    connection.commit()
    connection.close()

def save_business_analysis(tool_type, result):
    if not result or not result.strip():
        return
    if result.lstrip().startswith("### ⚠️"):
        return
    profile = st.session_state.business_profile
    business_name = profile.get("name") or "My Business"
    business_context = get_business_context()
    title = make_analysis_title(tool_type, business_name)
    analysis_id = create_business_analysis(
        title,
        tool_type,
        business_name,
        business_context,
        result
    )
    st.session_state.active_analysis_id = analysis_id

def make_analysis_title(tool_type, business_name):
    name = (business_name or "My Business").strip()
    clean_tool = tool_type.replace("📊 ", "").replace("📣 ", "").replace("🎯 ", "").replace("⚠️ ", "").replace("💡 ", "")
    return f"{clean_tool} — {name}"[:80]

def save_business_analysis(tool_type, result):
    business_name = st.session_state.business_profile.get("name", "").strip() or "My Business"
    title = make_analysis_title(tool_type, business_name)
    analysis_id = create_business_analysis(
        title,
        tool_type,
        business_name,
        get_business_context(),
        result
    )
    st.session_state.active_analysis_id = analysis_id
    return analysis_id

def make_chat_title(question):
    cleaned = " ".join(question.strip().split())
    if not cleaned:
        return "New conversation"
    words = cleaned.split()
    title = " ".join(words[:8])
    if len(words) > 8:
        title += "..."
    return title[:60]

def save_current_chat():
    messages = st.session_state.messages
    if not messages:
        return
    first_user_message = next(
        (message["content"] for message in messages if message.get("role") == "user"),
        "New conversation"
    )
    title = make_chat_title(first_user_message)
    if st.session_state.active_chat_id is None:
        st.session_state.active_chat_id = create_conversation(title, messages)
    else:
        update_conversation(st.session_state.active_chat_id, messages, title)

def start_new_chat():
    st.session_state.messages = []
    st.session_state.active_chat_id = None
    st.session_state.selected_page = "🤖 AI Advisor"

def open_chat(conversation_id):
    conversation = load_conversation(conversation_id)
    if conversation is not None:
        st.session_state.active_chat_id = conversation["id"]
        st.session_state.messages = conversation["messages"]
        st.session_state.selected_page = "🤖 AI Advisor"

initialize_chat_database()

# =========================================================
# PROFESSIONAL LIGHT UI
# =========================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html,
body,
[class*="css"] {
    font-family: "Inter", sans-serif !important;
}

.stApp {
    background: #f5f7fb !important;
    color: #172033 !important;
}

.main {
    background: #f5f7fb !important;
}

.block-container {
    max-width: 1250px !important;
    padding-top: 3.2rem !important;
    padding-bottom: 4rem !important;
}

/* GLOBAL TEXT */

p,
span,
label,
li,
td,
th {
    color: #172033;
}

/* STREAMLIT HEADER */

[data-testid="stHeader"] {
    background: #ffffff !important;
    border-bottom: 1px solid #e5e7eb !important;
}

[data-testid="stHeader"] * {
    color: #172033 !important;
}

[data-testid="stToolbar"] {
    background: transparent !important;
}

[data-testid="stToolbar"] * {
    color: #172033 !important;
}

/* TEXT AREA */

[data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    color: #172033 !important;
    -webkit-text-fill-color: #172033 !important;
    border: 1px solid #d9dee8 !important;
    border-radius: 12px !important;
    font-size: 15px !important;
    line-height: 1.65 !important;
    padding: 14px !important;
    opacity: 1 !important;
}

[data-testid="stTextArea"] textarea::placeholder {
    color: #98a2b3 !important;
    -webkit-text-fill-color: #98a2b3 !important;
    opacity: 1 !important;
}

[data-testid="stTextArea"] textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.12) !important;
}

[data-testid="stTextArea"] label {
    color: #344054 !important;
    font-weight: 600 !important;
}

/* SIDEBAR */

[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e4e7ec !important;
}

[data-testid="stSidebar"] > div {
    background: #ffffff !important;
}

[data-testid="stSidebar"] * {
    color: #172033 !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #111827 !important;
    font-weight: 800 !important;
}

[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 6px !important;
}

[data-testid="stSidebar"] [role="radio"] {
    background: transparent !important;
    border-radius: 12px !important;
    padding: 10px 12px !important;
}

[data-testid="stSidebar"] [role="radio"]:hover {
    background: #f0f3ff !important;
}

[data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
    background: #eef2ff !important;
}

[data-testid="stSidebar"] [role="radio"][aria-checked="true"] p,
[data-testid="stSidebar"] [role="radio"][aria-checked="true"] span {
    color: #4f46e5 !important;
    font-weight: 700 !important;
}

/* TITLES */

.main-title {
    font-size: 42px !important;
    font-weight: 800 !important;
    color: #111827 !important;
    line-height: 1.15 !important;
    margin-bottom: 6px !important;
}

.subtitle {
    font-size: 17px !important;
    color: #667085 !important;
    line-height: 1.6 !important;
    margin-bottom: 28px !important;
}

.section-title {
    font-size: 24px !important;
    font-weight: 800 !important;
    color: #111827 !important;
    margin-top: 25px !important;
    margin-bottom: 16px !important;
}

/* HERO */

.hero-card {
    background: linear-gradient(
        135deg,
        #eef2ff 0%,
        #f8faff 55%,
        #ffffff 100%
    ) !important;
    border: 1px solid #dce3ff !important;
    border-radius: 24px !important;
    padding: 32px !important;
    margin-bottom: 28px !important;
    box-shadow: 0 10px 30px rgba(79, 70, 229, 0.07) !important;
}

.hero-title {
    font-size: 28px !important;
    font-weight: 800 !important;
    color: #111827 !important;
    margin-bottom: 8px !important;
}

.hero-text {
    font-size: 16px !important;
    color: #4b5563 !important;
    line-height: 1.75 !important;
}

/* FEATURE CARDS */

.feature-card {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 18px !important;
    padding: 24px !important;
    min-height: 155px !important;
    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.04) !important;
    transition: all 0.2s ease !important;
}

.feature-card:hover {
    transform: translateY(-3px) !important;
    border-color: #c7d2fe !important;
    box-shadow: 0 12px 28px rgba(79, 70, 229, 0.09) !important;
}

.dashboard-feature-link {
    display: block !important;
    color: inherit !important;
    text-decoration: none !important;
}

.dashboard-feature-link:hover {
    color: inherit !important;
    text-decoration: none !important;
}

.dashboard-feature-link .feature-card {
    cursor: pointer !important;
}

.feature-icon {
    font-size: 30px !important;
    line-height: 1 !important;
}

.feature-title {
    font-size: 18px !important;
    font-weight: 700 !important;
    color: #111827 !important;
    margin-top: 12px !important;
    margin-bottom: 6px !important;
}

.feature-text {
    font-size: 14px !important;
    color: #667085 !important;
    line-height: 1.6 !important;
}

/* STATUS */

.status-card {
    background: #ecfdf3 !important;
    border: 1px solid #bbf7d0 !important;
    border-radius: 12px !important;
    padding: 11px 14px !important;
    color: #166534 !important;
    font-size: 14px !important;
    font-weight: 600 !important;
}

.status-card * {
    color: #166534 !important;
}

/* CHAT WELCOME */

.chat-welcome {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 22px !important;
    padding: 30px !important;
    margin-bottom: 22px !important;
    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.04) !important;
}

.chat-welcome-title {
    font-size: 25px !important;
    font-weight: 800 !important;
    color: #111827 !important;
    margin-bottom: 8px !important;
}

.chat-welcome-text {
    font-size: 15px !important;
    color: #667085 !important;
    line-height: 1.7 !important;
}

/* CHAT */

[data-testid="stChatMessage"] {
    border-radius: 18px !important;
    padding: 12px 16px !important;
    margin-bottom: 10px !important;
}

[data-testid="stChatMessageContent"] {
    color: #172033 !important;
    line-height: 1.75 !important;
}

[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] span,
[data-testid="stChatMessageContent"] li,
[data-testid="stChatMessageContent"] div {
    color: #172033 !important;
}

[data-testid="stChatMessageContent"] h1,
[data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3,
[data-testid="stChatMessageContent"] h4 {
    color: #111827 !important;
    font-weight: 750 !important;
}

[data-testid="stChatMessageContent"] strong {
    color: #111827 !important;
    font-weight: 700 !important;
}

[data-testid="stChatMessageContent"] a {
    color: #4f46e5 !important;
}

/* MARKDOWN */

.stMarkdown {
    color: #172033 !important;
}

.stMarkdown p {
    color: #172033 !important;
    line-height: 1.7 !important;
}

.stMarkdown h1,
.stMarkdown h2,
.stMarkdown h3,
.stMarkdown h4 {
    color: #111827 !important;
}

.stMarkdown strong {
    color: #111827 !important;
}

/* TABLE */

[data-testid="stMarkdownContainer"] table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 15px 0 !important;
    background: #ffffff !important;
}

[data-testid="stMarkdownContainer"] th {
    background: #eef2ff !important;
    color: #111827 !important;
    font-weight: 700 !important;
    padding: 12px !important;
    border: 1px solid #dfe3eb !important;
}

[data-testid="stMarkdownContainer"] td {
    color: #172033 !important;
    padding: 12px !important;
    border: 1px solid #e5e7eb !important;
    background: #ffffff !important;
}

/* CODE */

[data-testid="stMarkdownContainer"] code {
    background: #f1f3f7 !important;
    color: #b42318 !important;
    border-radius: 5px !important;
    padding: 2px 5px !important;
}

[data-testid="stMarkdownContainer"] pre {
    background: #111827 !important;
    border-radius: 12px !important;
    padding: 16px !important;
}

[data-testid="stMarkdownContainer"] pre code {
    background: transparent !important;
    color: #f9fafb !important;
}

/* BUTTONS */

.stButton > button {
    width: 100% !important;
    min-height: 44px !important;
    border-radius: 12px !important;
    border: 1px solid #d9dee8 !important;
    background: #ffffff !important;
    color: #172033 !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

.stButton > button p,
.stButton > button span {
    color: #172033 !important;
}

.stButton > button:hover {
    border-color: #818cf8 !important;
    background: #f8f9ff !important;
}

.stButton > button:hover p,
.stButton > button:hover span {
    color: #4f46e5 !important;
}

/* FORM BUTTON */

.stFormSubmitButton > button {
    background: #4f46e5 !important;
    color: #ffffff !important;
    border: none !important;
}

.stFormSubmitButton > button p,
.stFormSubmitButton > button span {
    color: #ffffff !important;
}

.stFormSubmitButton > button:hover {
    background: #4338ca !important;
}

/* CHAT INPUT AREA - LIGHT BLUE */

[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div {
    background: #eef6ff !important;
    background-color: #eef6ff !important;
    border-top-color: #dbeafe !important;
}

[data-testid="stBottom"] {
    box-shadow: none !important;
}

[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] form > div,
[data-testid="stChatInput"] form > div > div,
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="input"],
[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: #eef6ff !important;
    background-color: #eef6ff !important;
    border-radius: 18px !important;
}

[data-testid="stChatInput"] textarea {
    background: #ffffff !important;
    color: #172033 !important;
    border: 1px solid #d9dee8 !important;
    border-radius: 16px !important;
    font-size: 15px !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: #98a2b3 !important;
    opacity: 1 !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.12) !important;
}

/* REMOVE DARK BACKGROUND AROUND THE CHAT TYPING BAR */
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] form > div,
[data-testid="stChatInput"] form > div > div,
[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: #eef6ff !important;
    background-color: #eef6ff !important;
}

[data-testid="stChatInput"] textarea {
    background: #ffffff !important;
}

/* TEXT INPUT */

[data-testid="stTextInput"] input {
    background: #ffffff !important;
    color: #172033 !important;
    border: 1px solid #d9dee8 !important;
    border-radius: 11px !important;
}

[data-testid="stTextInput"] input::placeholder {
    color: #98a2b3 !important;
    opacity: 1 !important;
}

[data-testid="stTextInput"] label {
    color: #344054 !important;
    font-weight: 600 !important;
}

/* SELECTBOX */

[data-testid="stSelectbox"] label {
    color: #344054 !important;
    font-weight: 600 !important;
}

[data-testid="stSelectbox"] > div > div {
    background: #ffffff !important;
    color: #172033 !important;
    border-radius: 11px !important;
    border-color: #d9dee8 !important;
}

[data-testid="stSelectbox"] * {
    color: #172033 !important;
}

/* FORM */

[data-testid="stForm"] {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 20px !important;
    padding: 25px !important;
}

/* ALERTS */

[data-testid="stAlert"] {
    border-radius: 12px !important;
}

[data-testid="stAlert"] {
    background: #fff7ed !important;
    border: 1px solid #fed7aa !important;
    color: #7c2d12 !important;
    border-radius: 12px !important;
}

[data-testid="stAlert"] p,
[data-testid="stAlert"] span,
[data-testid="stAlert"] div,
[data-testid="stAlert"] label {
    color: #7c2d12 !important;
    -webkit-text-fill-color: #7c2d12 !important;
    opacity: 1 !important;
}

[data-testid="stAlert"] svg {
    color: #ea580c !important;
    fill: #ea580c !important;
}

/* VISIBLE BUSINESS TOOL WARNINGS */

.visible-warning {
    background: #fff7ed !important;
    color: #9a3412 !important;
    border: 1px solid #fdba74 !important;
    border-radius: 12px !important;
    padding: 12px 15px !important;
    margin: 10px 0 16px 0 !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    line-height: 1.5 !important;
}

.visible-warning * {
    color: #9a3412 !important;
    -webkit-text-fill-color: #9a3412 !important;
}

/* SPINNER */

[data-testid="stSpinner"] p {
    color: #4f46e5 !important;
}

/* DIVIDER */

hr {
    border-color: #e5e7eb !important;
}

/* CAPTION */

.stCaption,
[data-testid="stCaptionContainer"] {
    color: #667085 !important;
}

/* EXPANDERS */

[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 14px !important;
}

[data-testid="stExpander"] summary {
    color: #172033 !important;
}

[data-testid="stExpander"] summary p {
    color: #172033 !important;
    font-weight: 600 !important;
}

/* CHAT HISTORY */

.chat-history-heading {
    font-size: 12px !important;
    font-weight: 800 !important;
    color: #667085 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin: 8px 0 6px 2px !important;
}

.chat-history-empty {
    color: #98a2b3 !important;
    font-size: 13px !important;
    padding: 4px 2px 8px 2px !important;
}

[data-testid="stSidebar"] .history-button button {
    text-align: left !important;
    justify-content: flex-start !important;
    min-height: 38px !important;
    height: 38px !important;
    padding: 7px 10px !important;
    margin: 0 !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    box-shadow: none !important;
    overflow: hidden !important;
}

[data-testid="stSidebar"] .history-button button p,
[data-testid="stSidebar"] .history-button button span {
    text-align: left !important;
    color: #344054 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}

[data-testid="stSidebar"] .history-button button:hover {
    background: #f3f4ff !important;
    border-color: #e0e4ff !important;
}

[data-testid="stSidebar"] .history-button button:hover p,
[data-testid="stSidebar"] .history-button button:hover span {
    color: #4f46e5 !important;
}

/* BUSINESS ANALYSIS HISTORY */

.analysis-history-heading {
    font-size: 12px !important;
    font-weight: 800 !important;
    color: #667085 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin: 10px 0 6px 2px !important;
}

[data-testid="stSidebar"] .history-row {
    margin-bottom: 2px !important;
}

[data-testid="stSidebar"] .history-row button {
    min-height: 36px !important;
    height: 36px !important;
    padding: 5px 8px !important;
}

[data-testid="stSidebar"] [class*="st-key-delete_chat_"] button,
[data-testid="stSidebar"] [class*="st-key-delete_analysis_"] button {
    min-height: 36px !important;
    height: 36px !important;
    width: 36px !important;
    padding: 0 !important;
    margin: 0 !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    color: #dc2626 !important;
    -webkit-text-fill-color: #dc2626 !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] [class*="st-key-delete_chat_"] button p,
[data-testid="stSidebar"] [class*="st-key-delete_chat_"] button span,
[data-testid="stSidebar"] [class*="st-key-delete_analysis_"] button p,
[data-testid="stSidebar"] [class*="st-key-delete_analysis_"] button span {
    color: #dc2626 !important;
    -webkit-text-fill-color: #dc2626 !important;
    font-size: 16px !important;
    line-height: 1 !important;
}

[data-testid="stSidebar"] [class*="st-key-delete_chat_"] button:hover,
[data-testid="stSidebar"] [class*="st-key-delete_analysis_"] button:hover {
    background: #fff1f2 !important;
    border-color: #fecdd3 !important;
}

[data-testid="stSidebar"] [class*="st-key-delete_chat_"] button:focus,
[data-testid="stSidebar"] [class*="st-key-delete_analysis_"] button:focus {
    color: #dc2626 !important;
    -webkit-text-fill-color: #dc2626 !important;
    background: #fff1f2 !important;
    border-color: #fecdd3 !important;
    box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.12) !important;
}

/* MOBILE */

@media (max-width: 768px) {

    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 2rem !important;
    }

    .main-title {
        font-size: 32px !important;
    }

    .subtitle {
        font-size: 15px !important;
    }

    .hero-card {
        padding: 22px !important;
    }

    .hero-title {
        font-size: 23px !important;
    }

    .feature-card {
        margin-bottom: 12px !important;
    }

}


/* =========================================================
   PREMIUM SIDEBAR THREE-DOT MENU - LIGHT BLUE STYLE
   ========================================================= */

/* The Streamlit popover trigger is sometimes wrapped in an extra div.
   Target the actual trigger button at every level so it never falls back
   to the app's dark/default button styling. */
[data-testid="stSidebar"] [data-testid="stPopover"] button {
    appearance: none !important;
    -webkit-appearance: none !important;
    background: #ffffff !important;
    background-color: #ffffff !important;
    background-image: none !important;
    border: 1px solid #bfdbfe !important;
    border-radius: 10px !important;
    color: #2563eb !important;
    -webkit-text-fill-color: #2563eb !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.08) !important;
    opacity: 1 !important;
    filter: none !important;
}

/* Exact trigger sizing */
[data-testid="stSidebar"] [data-testid="stPopover"] > button,
[data-testid="stSidebar"] [data-testid="stPopover"] > div > button,
[data-testid="stSidebar"] [data-testid="stPopover"] button[aria-expanded] {
    width: 38px !important;
    min-width: 38px !important;
    max-width: 38px !important;
    height: 38px !important;
    min-height: 38px !important;
    max-height: 38px !important;
    padding: 0 !important;
    margin: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: 1 !important;
}

/* Remove dark styling from every inner wrapper */
[data-testid="stSidebar"] [data-testid="stPopover"] button > div,
[data-testid="stSidebar"] [data-testid="stPopover"] button > div > div,
[data-testid="stSidebar"] [data-testid="stPopover"] button > span,
[data-testid="stSidebar"] [data-testid="stPopover"] button > p {
    background: transparent !important;
    background-color: transparent !important;
    color: #2563eb !important;
    -webkit-text-fill-color: #2563eb !important;
    opacity: 1 !important;
}

/* KEEP ONLY THE ORIGINAL THREE-DOT LABEL */
[data-testid="stSidebar"] [data-testid="stPopover"] button svg,
[data-testid="stSidebar"] [data-testid="stPopover"] button svg * {
    display: none !important;
    visibility: hidden !important;
}

/* Hide Streamlit's built-in popover chevron/icon.
   The button label already contains "⋯", so no extra icon is needed. */
[data-testid="stSidebar"] [data-testid="stPopover"] button [data-testid="stIconMaterial"],
[data-testid="stSidebar"] [data-testid="stPopover"] button [data-testid="stIcon"],
[data-testid="stSidebar"] [data-testid="stPopover"] button .material-symbols-rounded,
[data-testid="stSidebar"] [data-testid="stPopover"] button .material-symbols-outlined {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* Do not add another ⋯ with a pseudo-element. */
[data-testid="stSidebar"] [data-testid="stPopover"] button::before,
[data-testid="stSidebar"] [data-testid="stPopover"] button::after {
    content: none !important;
    display: none !important;
}

/* Normal state */
[data-testid="stSidebar"] [data-testid="stPopover"] button:not(:hover):not([aria-expanded="true"]) {
    background: #ffffff !important;
    background-color: #ffffff !important;
    border-color: #bfdbfe !important;
    color: #2563eb !important;
    -webkit-text-fill-color: #2563eb !important;
}

/* Hover and open state */
[data-testid="stSidebar"] [data-testid="stPopover"] button:hover,
[data-testid="stSidebar"] [data-testid="stPopover"] button[aria-expanded="true"] {
    background: #eff6ff !important;
    background-color: #eff6ff !important;
    border-color: #93c5fd !important;
    color: #1d4ed8 !important;
    -webkit-text-fill-color: #1d4ed8 !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.12) !important;
}

[data-testid="stSidebar"] [data-testid="stPopover"] button:hover svg,
[data-testid="stSidebar"] [data-testid="stPopover"] button:hover svg *,
[data-testid="stSidebar"] [data-testid="stPopover"] button[aria-expanded="true"] svg,
[data-testid="stSidebar"] [data-testid="stPopover"] button[aria-expanded="true"] svg * {
    color: #1d4ed8 !important;
    stroke: #1d4ed8 !important;
    fill: none !important;
}

/* Keyboard focus */
[data-testid="stSidebar"] [data-testid="stPopover"] button:focus,
[data-testid="stSidebar"] [data-testid="stPopover"] button:focus-visible {
    outline: none !important;
    background: #eff6ff !important;
    background-color: #eff6ff !important;
    border-color: #60a5fa !important;
    color: #1d4ed8 !important;
    -webkit-text-fill-color: #1d4ed8 !important;
    box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.18) !important;
}

/* WHITE DROPDOWN PANEL WITH LIGHT BLUE BORDER */
[data-testid="stPopoverBody"],
[data-baseweb="popover"],
[data-baseweb="popover"] > div {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #172033 !important;
}

[data-testid="stPopoverBody"] {
    min-width: 190px !important;
    padding: 8px !important;
    border: 1px solid #bfdbfe !important;
    border-radius: 14px !important;
    box-shadow: 0 12px 30px rgba(37, 99, 235, 0.12) !important;
}

[data-testid="stPopoverBody"] * {
    color: #344054 !important;
    -webkit-text-fill-color: #344054 !important;
}

/* ONLY THE THREE MENU OPTIONS */
[data-testid="stPopoverBody"] .stButton > button {
    width: 100% !important;
    min-height: 40px !important;
    height: 40px !important;
    padding: 8px 12px !important;
    margin: 3px 0 !important;
    border: 1px solid transparent !important;
    border-radius: 9px !important;
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #344054 !important;
    -webkit-text-fill-color: #344054 !important;
    box-shadow: none !important;
    text-align: left !important;
    justify-content: flex-start !important;
}

[data-testid="stPopoverBody"] .stButton > button:hover {
    background: #eff6ff !important;
    background-color: #eff6ff !important;
    border-color: #dbeafe !important;
    color: #2563eb !important;
    -webkit-text-fill-color: #2563eb !important;
}

[data-testid="stPopoverBody"] .stButton > button p,
[data-testid="stPopoverBody"] .stButton > button span {
    color: #344054 !important;
    -webkit-text-fill-color: #344054 !important;
}

[data-testid="stPopoverBody"] .stButton > button:hover p,
[data-testid="stPopoverBody"] .stButton > button:hover span {
    color: #2563eb !important;
    -webkit-text-fill-color: #2563eb !important;
}

/* DELETE OPTION */
[data-testid="stPopoverBody"] .stButton:last-child > button:hover {
    background: #fff1f2 !important;
    border-color: #fecdd3 !important;
    color: #dc2626 !important;
    -webkit-text-fill-color: #dc2626 !important;
}

[data-testid="stPopoverBody"] .stButton:last-child > button:hover p,
[data-testid="stPopoverBody"] .stButton:last-child > button:hover span {
    color: #dc2626 !important;
    -webkit-text-fill-color: #dc2626 !important;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# GROQ CLIENT
# =========================================================

def get_client():
    if not GROQ_API_KEY:
        return None

    return Groq(api_key=GROQ_API_KEY)

# =========================================================
# BUSINESS CONTEXT
# =========================================================

def get_business_context():
    profile = st.session_state.business_profile

    description = st.session_state.get(
        "tool_business_description",
        ""
    )

    target_customers = st.session_state.get(
        "tool_target_customers",
        ""
    )

    business_goal = st.session_state.get(
        "tool_business_goal",
        ""
    )

    business_challenge = st.session_state.get(
        "tool_business_challenge",
        ""
    )

    if not any(profile.values()) and not any([
        description,
        target_customers,
        business_goal,
        business_challenge
    ]):
        return "No business information has been provided yet."

    return f"""
BUSINESS PROFILE
Business Name: {profile.get("name") or "Not provided"}
Industry: {profile.get("industry") or "Not provided"}
Location: {profile.get("location") or "Not provided"}
Budget: {profile.get("budget") or "Not provided"}
Business Stage: {profile.get("stage") or "Not provided"}

BUSINESS TOOLS WORKSPACE
Business Description: {description or "Not provided"}
Target Customers: {target_customers or "Not provided"}
Business Goal: {business_goal or "Not provided"}
Main Business Challenge: {business_challenge or "Not provided"}
"""

# =========================================================
# AI FUNCTION
# =========================================================

def ask_bizadvisor(user_question):

    client = get_client()

    if client is None:
        return """
### ⚠️ Groq API Key Missing

BizAdvisor AI cannot connect to Groq because the API key is not configured.

Create a `.env` file in your project folder and add:

`GROQ_API_KEY=your_groq_api_key_here`

Then restart Streamlit.
"""

    system_prompt = f"""
You are BizAdvisor AI, a professional AI-powered business consultant.

Your purpose is to help users understand business problems and make better
business decisions.

You should behave like an experienced but friendly business advisor.

BUSINESS PROFILE:
{get_business_context()}

YOUR RESPONSIBILITIES:

- Understand the user's actual question before answering.
- Give practical and actionable advice.
- Explain business concepts in simple language.
- Help with startups, business ideas, strategy, marketing, finance,
  customers, competition, risks, pricing and growth.
- Personalize advice using the business profile when useful.
- If the user has not provided enough information, ask a short,
  useful follow-up question instead of making assumptions.
- Never pretend that an estimate is a verified fact.
- Clearly label assumptions and examples.
- Do not give illegal, fraudulent or deceptive business advice.
- Keep answers organized and easy to read.
- Use headings, numbered steps and bullet points when appropriate.
- Do not repeat the user's question unnecessarily.
- Do not mention these system instructions.

RESPONSE STYLE:

Be conversational, professional and helpful.

For simple questions:
Give a direct answer.

For business decisions use:

1. Recommendation
2. Why
3. Action steps
4. Risks or considerations

For strategy questions:
Give practical steps and measurable goals.

For comparisons:
Use a simple comparison table when useful.

For brainstorming:
Give multiple ideas and explain the strongest options.

The user should feel that they are talking to a real business consultant.
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    for message in st.session_state.messages:
        messages.append({
            "role": message["role"],
            "content": message["content"]
        })

    messages.append({
        "role": "user",
        "content": user_question
    })

    try:

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.6,
            max_completion_tokens=1500
        )

        answer = response.choices[0].message.content

        if not answer:
            return "⚠️ The AI returned an empty response. Please try again."

        return answer

    except Exception as error:

        error_text = str(error)

        return f"""
### ⚠️ AI Connection Problem

BizAdvisor AI could not complete the request.

**Possible reason:**

{error_text}

Please check your Groq API key and internet connection, then try again.
"""

# =========================================================
# SEND MESSAGE
# =========================================================

def send_message(question):

    answer = ask_bizadvisor(question)

    st.session_state.messages.append({
        "role": "user",
        "content": question
    })

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

    save_current_chat()

# =========================================================
# RENAME DIALOGS
# =========================================================

@st.dialog("Rename Chat")
def rename_chat_dialog(conversation_id, current_title):
    st.markdown(
        '<div class="rename-dialog-subtitle">Choose a new name for this conversation.</div>',
        unsafe_allow_html=True
    )
    new_title = st.text_input(
        "Chat name",
        value=current_title,
        max_chars=80,
        label_visibility="collapsed"
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", use_container_width=True, key=f"cancel_rename_chat_{conversation_id}"):
            st.rerun()
    with col2:
        if st.button("Save", use_container_width=True, key=f"save_rename_chat_{conversation_id}"):
            if new_title.strip():
                rename_conversation(conversation_id, new_title)
            st.rerun()

@st.dialog("Rename Analysis")
def rename_analysis_dialog(analysis_id, current_title):
    st.markdown(
        '<div class="rename-dialog-subtitle">Choose a new name for this analysis.</div>',
        unsafe_allow_html=True
    )
    new_title = st.text_input(
        "Analysis name",
        value=current_title,
        max_chars=100,
        label_visibility="collapsed"
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", use_container_width=True, key=f"cancel_rename_analysis_{analysis_id}"):
            st.rerun()
    with col2:
        if st.button("Save", use_container_width=True, key=f"save_rename_analysis_{analysis_id}"):
            if new_title.strip():
                rename_business_analysis(analysis_id, new_title)
            st.rerun()

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown("## 🤖 BizAdvisor AI")

    st.caption("AI-Powered Business Decision Assistant")

    st.divider()

    menu_items = [
        "🏠 Dashboard",
        "🤖 AI Advisor",
        "📊 Business Tools"
    ]

    if st.session_state.selected_page not in menu_items:
        st.session_state.selected_page = menu_items[0]

    page = st.radio(
        "MAIN MENU",
        menu_items,
        index=menu_items.index(st.session_state.selected_page),
        label_visibility="visible"
    )
    st.session_state.selected_page = page

    st.divider()

    if GROQ_API_KEY:

        st.markdown(
            '<div class="status-card">🟢 AI System Connected</div>',
            unsafe_allow_html=True
        )

    else:

        st.error("🔴 Groq API key not configured")

    st.divider()

    # =========================================================
    # CHAT HISTORY
    # =========================================================

    st.markdown('<div class="chat-history-heading">💬 Chat History</div>', unsafe_allow_html=True)

    if st.button("➕ New Chat", use_container_width=True, key="sidebar_new_chat"):
        start_new_chat()
        st.rerun()

    conversations = get_conversations()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    grouped = {"Today": [], "Yesterday": [], "Older": []}

    for conversation in conversations:
        try:
            conversation_date = datetime.fromisoformat(conversation["updated_at"]).date()
        except (ValueError, TypeError):
            conversation_date = today
        if conversation_date == today:
            grouped["Today"].append(conversation)
        elif conversation_date == yesterday:
            grouped["Yesterday"].append(conversation)
        else:
            grouped["Older"].append(conversation)

    for group_name in ["Today", "Yesterday", "Older"]:
        if grouped[group_name]:
            st.markdown(
                f'<div class="chat-history-heading">{group_name}</div>',
                unsafe_allow_html=True
            )
        for conversation in grouped[group_name]:
            row_col, menu_col = st.columns([5, 1], gap="small")
            with row_col:
                if st.button(
                    f"📌 {conversation['title']}" if conversation.get("pinned") else f"💬 {conversation['title']}",
                    key=f"open_chat_{conversation['id']}",
                    use_container_width=True
                ):
                    open_chat(conversation["id"])
                    st.rerun()
            with menu_col:
                with st.popover("⋯", use_container_width=True):
                    if st.button("✏️ Rename Chat", key=f"rename_chat_{conversation['id']}", use_container_width=True):
                        rename_chat_dialog(conversation["id"], conversation["title"])
                    pin_text = "📌 Unpin Chat" if conversation.get("pinned") else "📌 Pin Chat"
                    if st.button(pin_text, key=f"pin_chat_{conversation['id']}", use_container_width=True):
                        toggle_pin_conversation(conversation["id"])
                        st.rerun()
                    if st.button("🗑️ Delete Chat", key=f"delete_chat_{conversation['id']}", use_container_width=True):
                        delete_conversation(conversation["id"])
                        if st.session_state.active_chat_id == conversation["id"]:
                            start_new_chat()
                        st.rerun()

    if not conversations:
        st.markdown(
            '<div class="chat-history-empty">No conversations yet</div>',
            unsafe_allow_html=True
        )

    # =========================================================
    # BUSINESS ANALYSIS HISTORY
    # =========================================================

    st.markdown('<div class="analysis-history-heading">📊 Analysis History</div>', unsafe_allow_html=True)

    analyses = get_business_analyses()
    analysis_grouped = {"Today": [], "Yesterday": [], "Older": []}

    for analysis in analyses:
        try:
            analysis_date = datetime.fromisoformat(analysis["updated_at"]).date()
        except (ValueError, TypeError):
            analysis_date = today
        if analysis_date == today:
            analysis_grouped["Today"].append(analysis)
        elif analysis_date == yesterday:
            analysis_grouped["Yesterday"].append(analysis)
        else:
            analysis_grouped["Older"].append(analysis)

    for group_name in ["Today", "Yesterday", "Older"]:
        if analysis_grouped[group_name]:
            st.markdown(
                f'<div class="chat-history-heading">{group_name}</div>',
                unsafe_allow_html=True
            )
        for analysis in analysis_grouped[group_name]:
            row_col, menu_col = st.columns([5, 1], gap="small")
            with row_col:
                if st.button(
                    f"📌 {analysis['title']}" if analysis.get("pinned") else f"📊 {analysis['title']}",
                    key=f"open_analysis_{analysis['id']}",
                    use_container_width=True
                ):
                    st.session_state.active_analysis_id = analysis["id"]
                    st.session_state.selected_page = "📊 Business Tools"
                    st.rerun()
            with menu_col:
                with st.popover("⋯", use_container_width=True):
                    if st.button("✏️ Rename Analysis", key=f"rename_analysis_{analysis['id']}", use_container_width=True):
                        rename_analysis_dialog(analysis["id"], analysis["title"])
                    pin_text = "📌 Unpin Analysis" if analysis.get("pinned") else "📌 Pin Analysis"
                    if st.button(pin_text, key=f"pin_analysis_{analysis['id']}", use_container_width=True):
                        toggle_pin_business_analysis(analysis["id"])
                        st.rerun()
                    if st.button("🗑️ Delete Analysis", key=f"delete_analysis_{analysis['id']}", use_container_width=True):
                        delete_business_analysis(analysis["id"])
                        if st.session_state.active_analysis_id == analysis["id"]:
                            st.session_state.active_analysis_id = None
                        st.rerun()

    if not analyses:
        st.markdown(
            '<div class="chat-history-empty">No analyses yet</div>',
            unsafe_allow_html=True
        )

    st.divider()

    if st.session_state.business_profile["name"]:

        st.markdown("### 🏢 Active Business")

        st.write(
            st.session_state.business_profile["name"]
        )

        if st.session_state.business_profile["industry"]:

            st.caption(
                st.session_state.business_profile["industry"]
            )

        st.caption("Business details are managed in Business Tools.")

# =========================================================
# DASHBOARD
# =========================================================

if st.session_state.get("start_chat"):
    st.session_state.start_chat = False
    page = "🤖 AI Advisor"

if page == "🏠 Dashboard":

    st.markdown(
        '<div class="main-title">BizAdvisor AI</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">Your intelligent partner for smarter business decisions.</div>',
        unsafe_allow_html=True
    )

    st.markdown("""
    <div class="hero-card">
        <div class="hero-title">👋 Welcome to BizAdvisor AI</div>
        <div class="hero-text">
            Ask questions, explore business ideas, build strategies,
            analyze risks and get practical recommendations from your
            AI business advisor.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="section-title">What can you do?</div>',
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=ai_advisor">
            <div class="feature-card">
                <div class="feature-icon">🤖</div>
                <div class="feature-title">AI Advisor</div>
                <div class="feature-text">
                    Have a natural conversation with your AI business consultant.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    with col2:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=business_analysis">
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <div class="feature-title">Business Analysis</div>
                <div class="feature-text">
                    Understand strengths, weaknesses, opportunities and risks.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    with col3:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=growth_strategy">
            <div class="feature-card">
                <div class="feature-icon">📈</div>
                <div class="feature-title">Growth Strategy</div>
                <div class="feature-text">
                    Build practical strategies to improve and grow your business.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)

    with col4:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=business_ideas">
            <div class="feature-card">
                <div class="feature-icon">💡</div>
                <div class="feature-title">Business Ideas</div>
                <div class="feature-text">
                    Discover business opportunities based on your goals.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    with col5:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=marketing">
            <div class="feature-card">
                <div class="feature-icon">📣</div>
                <div class="feature-title">Marketing</div>
                <div class="feature-text">
                    Create customer-focused marketing and promotion strategies.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    with col6:

        st.markdown("""
        <a class="dashboard-feature-link" href="?dashboard_action=risk_analysis">
            <div class="feature-card">
                <div class="feature-icon">⚠️</div>
                <div class="feature-title">Risk Analysis</div>
                <div class="feature-text">
                    Identify possible business risks and ways to reduce them.
                </div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button(
        "🤖 Start Chatting with BizAdvisor AI",
        use_container_width=True
    ):

        st.session_state.selected_page = "🤖 AI Advisor"
        st.session_state.start_chat = True
        st.rerun()

# =========================================================
# AI ADVISOR
# =========================================================

elif page == "🤖 AI Advisor":

    st.markdown(
        '<div class="main-title">🤖 AI Business Advisor</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">Ask anything about your business and get practical AI-powered guidance.</div>',
        unsafe_allow_html=True
    )

    if not st.session_state.messages:

        st.markdown("""
        <div class="chat-welcome">
            <div class="chat-welcome-title">
                👋 How can I help you today?
            </div>
            <div class="chat-welcome-text">
                I can help you with business ideas, strategy, marketing,
                pricing, customers, competition, financial planning,
                risk analysis and growth.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 💡 Start with a question")

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "💡 Give me a profitable business idea",
                use_container_width=True
            ):

                send_message(
                    "Suggest 5 practical business ideas that can be started with a small budget. For each idea, explain the target customers, problem solved, revenue model and why it could work."
                )

                st.rerun()

            if st.button(
                "📊 Analyze my business",
                use_container_width=True
            ):

                send_message(
                    "Analyze my business using the business profile information available. Give me the most important strengths, weaknesses, opportunities and threats."
                )

                st.rerun()

        with col2:

            if st.button(
                "📣 Create a marketing strategy",
                use_container_width=True
            ):

                send_message(
                    "Create a practical marketing strategy for my business. Include target customers, marketing channels, content ideas, customer acquisition and retention strategies."
                )

                st.rerun()

            if st.button(
                "🚀 How can I grow my business?",
                use_container_width=True
            ):

                send_message(
                    "Give me a practical business growth strategy. Focus on customer acquisition, retention, revenue growth and improving my competitive advantage."
                )

                st.rerun()

    else:

        col1, col2 = st.columns([5, 1])

        with col1:

            st.markdown("### 💬 Your Conversation")

        with col2:

            if st.button("➕ New Chat"):
                start_new_chat()
                st.rerun()

    for message in st.session_state.messages:

        if message["role"] == "user":
            avatar = "👤"
        else:
            avatar = "🤖"

        with st.chat_message(
            message["role"],
            avatar=avatar
        ):

            st.markdown(message["content"])

    user_question = st.chat_input(
        "Ask BizAdvisor AI anything..."
    )

    if user_question and user_question.strip():

        with st.chat_message(
            "user",
            avatar="👤"
        ):

            st.markdown(user_question)

        with st.chat_message(
            "assistant",
            avatar="🤖"
        ):

            with st.spinner(
                "🤖 BizAdvisor AI is thinking..."
            ):

                answer = ask_bizadvisor(user_question)

            st.markdown(answer)

        st.session_state.messages.append({
            "role": "user",
            "content": user_question
        })

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })

        save_current_chat()
        st.rerun()

# =========================================================
# BUSINESS TOOLS

elif page == "📊 Business Tools":

    st.markdown(
        '<div class="main-title">📊 Business Tools</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">Describe your business once, then use AI-powered tools to analyze and improve it.</div>',
        unsafe_allow_html=True
    )

    # =========================================================
    # BUSINESS ANALYSIS WORKSPACE
    # =========================================================

    st.markdown("""
    <div class="hero-card">
        <div class="hero-title">🧠 Business Analysis Workspace</div>
        <div class="hero-text">
            Tell BizAdvisor AI about your business here. The information
            you provide will be used across SWOT, Marketing, Strategy,
            Risk and other business analysis tools.
        </div>
    </div>
    """, unsafe_allow_html=True)

    profile = st.session_state.business_profile

    st.markdown(
        '<div class="section-title">📝 Tell us about your business</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="hero-card" style="padding:22px 26px !important; margin-bottom:18px !important;">
            <div class="hero-text">
                Fill in the details below once. BizAdvisor AI will use this information
                across every analysis tool, so you do not need to enter the same details again.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):

        col1, col2 = st.columns(2)

        with col1:

            workspace_name = st.text_input(
                "Business Name",
                value=profile.get("name", ""),
                placeholder="Example: GreenBite Foods"
            )

            workspace_industry = st.text_input(
                "Industry",
                value=profile.get("industry", ""),
                placeholder="Example: Food & Beverage"
            )

            workspace_location = st.text_input(
                "Business Location",
                value=profile.get("location", ""),
                placeholder="Example: Hyderabad, Telangana"
            )

            workspace_customers = st.text_input(
                "Target Customers",
                value=st.session_state.tool_target_customers,
                placeholder="Example: College students and young professionals"
            )

        with col2:

            workspace_goal = st.text_input(
                "Business Goal",
                value=st.session_state.tool_business_goal,
                placeholder="Example: Get 500 customers in the first 3 months"
            )

            workspace_challenge = st.text_input(
                "Main Business Challenge",
                value=st.session_state.tool_business_challenge,
                placeholder="Example: High competition and limited marketing budget"
            )

            workspace_budget = st.text_input(
                "Estimated Budget",
                value=profile.get("budget", ""),
                placeholder="Example: ₹2,50,000"
            )

            stages = [
                "Idea Stage",
                "Planning",
                "Startup",
                "Growing Business",
                "Established Business"
            ]

            current_stage = (
                profile.get("stage", "")
                if profile.get("stage", "") in stages
                else "Idea Stage"
            )

            workspace_stage = st.selectbox(
                "Business Stage",
                stages,
                index=stages.index(current_stage)
            )

        workspace_description = st.text_area(
            "Business Description",
            value=st.session_state.tool_business_description,
            placeholder=(
                "Example: I want to start a healthy food delivery business in Hyderabad "
                "targeting college students. I will provide affordable high-protein meals "
                "and monthly subscription plans. My initial budget is ₹2 lakh. "
                "My main challenge is competing with Swiggy and Zomato."
            ),
            height=180,
            help="Describe what you sell, who you serve, the problem you solve, how you make money, what makes you different, and any important challenge."
        )

        st.caption(
            "💡 The more specific your description is, the more personalized and useful your AI analysis will be."
        )

        save_col1, save_col2 = st.columns([3, 1])

        with save_col1:

            save_information = st.button(
                "💾 Save Business Information",
                use_container_width=True
            )

        with save_col2:

            reset_information = st.button(
                "↺ Reset",
                use_container_width=True
            )

        if save_information:

            st.session_state.business_profile = {
                "name": workspace_name,
                "industry": workspace_industry,
                "location": workspace_location,
                "budget": workspace_budget,
                "stage": workspace_stage
            }

            st.session_state.tool_business_description = workspace_description
            st.session_state.tool_target_customers = workspace_customers
            st.session_state.tool_business_goal = workspace_goal
            st.session_state.tool_business_challenge = workspace_challenge

            st.success(
                "✅ Business information saved. You can now use any AI analysis tool below."
            )

        if reset_information:

            st.session_state.business_profile = {
                "name": "",
                "industry": "",
                "location": "",
                "budget": "",
                "stage": ""
            }

            st.session_state.tool_business_description = ""
            st.session_state.tool_target_customers = ""
            st.session_state.tool_business_goal = ""
            st.session_state.tool_business_challenge = ""

            st.rerun()

    if st.session_state.business_profile["name"] and st.session_state.tool_business_description:

        st.markdown(
            """
            <div class="status-card">
                🟢 Business information is ready for AI analysis
            </div>
            """,
            unsafe_allow_html=True
        )

    if st.session_state.active_analysis_id is not None:

        saved_analysis = load_business_analysis(st.session_state.active_analysis_id)

        if saved_analysis is not None:
            st.markdown("### 📚 Saved Analysis")
            st.caption(
                f"{saved_analysis['tool_type']} • {saved_analysis['business_name']} • {saved_analysis['updated_at'].replace('T', ' ')}"
            )
            st.markdown(saved_analysis["result"])
            if st.button("🗑️ Delete This Analysis", key="delete_open_analysis", use_container_width=True):
                delete_business_analysis(saved_analysis["id"])
                st.session_state.active_analysis_id = None
                st.rerun()
            st.divider()
        else:
            st.session_state.active_analysis_id = None

    st.markdown(
        '<div class="section-title">🔎 Choose an AI analysis</div>',
        unsafe_allow_html=True
    )

    available_tools = [
        "📊 SWOT Analysis",
        "📣 Marketing Advisor",
        "🎯 Strategy Planner",
        "⚠️ Risk Analyzer",
        "💡 Business Idea Generator"
    ]

    if st.session_state.selected_tool not in available_tools:
        st.session_state.selected_tool = available_tools[0]

    tool = st.selectbox(
        "Choose a tool",
        available_tools,
        index=available_tools.index(st.session_state.selected_tool)
    )
    st.session_state.selected_tool = tool

    st.divider()

    # =====================================================
    # SWOT
    # =====================================================

    if tool == "📊 SWOT Analysis":

        st.markdown("### 📊 SWOT Analysis")

        st.write(
            "Analyze your business strengths, weaknesses, opportunities and threats using the information you entered above."
        )

        if st.button(
            "🚀 Generate SWOT Analysis",
            use_container_width=True
        ):

            if not st.session_state.tool_business_description.strip():
                st.markdown(
                    '<div class="visible-warning">⚠️ Please enter your Business Description above before generating the SWOT analysis.</div>',
                    unsafe_allow_html=True
                )
            else:

                question = """
Create a detailed SWOT analysis for the business information provided.

Give:

1. Strengths
2. Weaknesses
3. Opportunities
4. Threats
5. Three priority actions based on the SWOT analysis

For every point, explain why it matters to this specific business.
Do not give generic advice when the business information supports a more specific answer.
Clearly separate facts from assumptions.
Make the recommendations practical and actionable.
"""

                with st.spinner(
                    "🤖 Analyzing your business..."
                ):

                    result = ask_bizadvisor(question)

                st.markdown("### 📋 SWOT Analysis Result")
                st.markdown(result)
                save_business_analysis("📊 SWOT Analysis", result)
                save_business_analysis("📊 SWOT Analysis", result)

    # =====================================================
    # MARKETING
    # =====================================================

    elif tool == "📣 Marketing Advisor":

        st.markdown("### 📣 Marketing Advisor")

        st.write(
            "Create a practical marketing plan based on your business description, customers, goals and challenges."
        )

        if st.button(
            "🚀 Create Marketing Strategy",
            use_container_width=True
        ):

            if not st.session_state.tool_business_description.strip():
                st.markdown(
                    '<div class="visible-warning">⚠️ Please enter your Business Description above before creating a marketing strategy.</div>',
                    unsafe_allow_html=True
                )
            else:

                question = """
Create a practical marketing strategy specifically for the business information provided.

Include:

- Target audience
- Customer needs
- Positioning
- Unique value proposition
- Marketing channels
- Social media strategy
- Content ideas
- Customer acquisition
- Customer retention
- Suggested offers
- Important metrics

Prioritize the most realistic actions for the business's budget, stage and goals.
"""

                with st.spinner(
                    "🤖 Building your marketing strategy..."
                ):

                    result = ask_bizadvisor(question)

                st.markdown("### 📋 Marketing Strategy Result")
                st.markdown(result)
                save_business_analysis("📣 Marketing Advisor", result)
                save_business_analysis("📣 Marketing Advisor", result)

    # =====================================================
    # STRATEGY PLANNER
    # =====================================================

    elif tool == "🎯 Strategy Planner":

        st.markdown("### 🎯 Strategy Planner")

        st.write(
            "Build a practical 90-day action plan based on your business goals and current challenges."
        )

        if st.button(
            "🚀 Create 90-Day Strategy",
            use_container_width=True
        ):

            if not st.session_state.tool_business_description.strip():
                st.markdown(
                    '<div class="visible-warning">⚠️ Please enter your Business Description above before creating a strategy.</div>',
                    unsafe_allow_html=True
                )
            else:

                question = """
Create a practical 90-day business action plan specifically for the business information provided.

Divide the plan into:

- Days 1–30
- Days 31–60
- Days 61–90

For each period give:

- Main objectives
- Specific actions
- Priority
- Expected outcome
- Metrics to track

End with the top 5 actions the business owner should focus on first.
"""

                with st.spinner(
                    "🤖 Creating your strategy..."
                ):

                    result = ask_bizadvisor(question)

                st.markdown("### 📋 90-Day Strategy Result")
                st.markdown(result)
                save_business_analysis("🎯 Strategy Planner", result)
                save_business_analysis("🎯 Strategy Planner", result)

    # =====================================================
    # RISK ANALYZER
    # =====================================================

    elif tool == "⚠️ Risk Analyzer":

        st.markdown("### ⚠️ Risk Analyzer")

        st.write(
            "Identify major risks for your specific business and learn how to reduce them."
        )

        if st.button(
            "🚀 Analyze Business Risks",
            use_container_width=True
        ):

            if not st.session_state.tool_business_description.strip():
                st.markdown(
                    '<div class="visible-warning">⚠️ Please enter your Business Description above before analyzing risks.</div>',
                    unsafe_allow_html=True
                )
            else:

                question = """
Analyze the major risks for the business information provided.

Cover:

- Financial risks
- Market risks
- Customer risks
- Competition risks
- Operational risks
- Technology risks
- Legal or compliance considerations when relevant

For each important risk provide:

- Risk level
- Why it matters
- Early warning sign
- Prevention strategy
- Backup action

Finish with the three risks that should be addressed first.
"""

                with st.spinner(
                    "🤖 Analyzing business risks..."
                ):

                    result = ask_bizadvisor(question)

                st.markdown("### 📋 Business Risk Analysis Result")
                st.markdown(result)
                save_business_analysis("⚠️ Risk Analyzer", result)
                save_business_analysis("⚠️ Risk Analyzer", result)

    # =====================================================
    # BUSINESS IDEA GENERATOR
    # =====================================================

    elif tool == "💡 Business Idea Generator":

        st.markdown("### 💡 Business Idea Generator")

        st.write(
            "Generate realistic business opportunities based on the information and goals you provide."
        )

        if st.button(
            "🚀 Generate Business Ideas",
            use_container_width=True
        ):

            if not st.session_state.tool_business_description.strip():
                st.markdown(
                    '<div class="visible-warning">⚠️ Please describe your current business, idea or interests above before generating ideas.</div>',
                    unsafe_allow_html=True
                )
            else:

                question = """
Generate 10 realistic business opportunities that match the business information provided.

For every idea include:

- Business concept
- Target customers
- Problem solved
- Revenue model
- Basic startup requirements
- Growth potential
- Main risk

At the end:

1. Recommend the top 3 ideas.
2. Rank them from strongest to weakest.
3. Explain why the #1 idea is the best fit.
"""

                with st.spinner(
                    "🤖 Finding business opportunities..."
                ):

                    result = ask_bizadvisor(question)

                st.markdown("### 📋 Business Ideas Result")
                st.markdown(result)
                save_business_analysis("💡 Business Idea Generator", result)
                save_business_analysis("💡 Business Idea Generator", result)
