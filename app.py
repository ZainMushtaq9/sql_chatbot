import streamlit as st
import requests
import pandas as pd
import os
import re
import uuid

# --- Configuration ---
# BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5000")
BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://15.235.9.166:5002")
QUERY_URL = f"{BACKEND_BASE_URL}/query"
DISCOVER_CONTENT_URL = f"{BACKEND_BASE_URL}/discover-content"
HEALTH_CHECK_URL = f"{BACKEND_BASE_URL}/"

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="AI Database Agent",
    page_icon="🤖"
)

# --- Helper Functions (No changes needed here) ---
def make_api_request(url, method="GET", json_data=None, timeout=60):
    try:
        headers = {'Content-Type': 'application/json'}
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, timeout=timeout, headers=headers)
        else:
            response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as http_err:
        try:
            error_details = http_err.response.json()
            details_msg = error_details.get('details', str(http_err))
            error_msg = f"{error_details.get('error', 'An HTTP error occurred')}: {details_msg}"
            return None, error_msg
        except:
            return None, f"An HTTP error occurred: {http_err.response.text}"
    except requests.exceptions.ConnectionError:
        return None, "Connection Error: Backend is unreachable."
    except Exception as e:
        return None, f"An unexpected error occurred: {e}"

def format_sql(sql_query):
    if not isinstance(sql_query, str): return ""
    keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'ON', 'GROUP BY', 'ORDER BY', 'LIMIT']
    for keyword in keywords:
        sql_query = re.sub(rf'\b({keyword})\b', f'\n{keyword}', sql_query, flags=re.IGNORECASE)
    return sql_query.strip()

def generate_session_id():
    return f"st-session-{uuid.uuid4()}"

# --- Session State Initialization ---
# The session now persists for the lifetime of the browser tab.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = generate_session_id()

# --- Main Page Layout ---

# Title and Admin controls are now at the top of the main page
st.title("💬 AI Database Agent")

with st.expander("Admin & Setup"):
    st.markdown("Use this to teach the AI about your database schema.")
    if st.button("Discover/Refresh Schema"):
        with st.spinner("Analyzing and embedding database schema..."):
            data, error = make_api_request(DISCOVER_CONTENT_URL, method="POST")
            if error:
                st.error(f"Discovery Failed: {error}")
            else:
                st.success(f"Discovery complete! {data.get('documents_added', 0)} documents indexed.")

# --- Main Chat Interface ---

# A container for the chat history
chat_container = st.container()

with chat_container:
    # Display the chat history from the session state
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            # For assistant messages, we might have structured content
            if isinstance(message["content"], dict):
                st.markdown(message["content"]["summary"])
                if message["content"]["sql"]:
                    with st.expander("View Generated SQL"):
                        st.code(format_sql(message["content"]["sql"]), language="sql")
                if not message["content"]["df"].empty:
                    st.dataframe(message["content"]["df"], use_container_width=True)
            else:
                # For user messages or simple text responses
                st.markdown(message["content"])

# The chat input box at the bottom of the page
if prompt := st.chat_input("Ask a question about your data..."):
    # Add user message to history and display it immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Send the query to the backend and handle the response
    with st.chat_message("assistant"):
        with st.spinner("🤖 Thinking..."):
            json_payload = {
                "query": prompt,
                "session_id": st.session_state.session_id
            }
            response, error = make_api_request(QUERY_URL, method="POST", json_data=json_payload)
            
            if error:
                st.error(error)
                st.session_state.messages.append({"role": "assistant", "content": error})
            elif response:
                sql_query = response.get("sql_query")
                results_list = response.get("results", [])
                df = pd.DataFrame(results_list) if results_list else pd.DataFrame()
                
                # Create a user-friendly text summary
                summary_text = f"I found {len(results_list)} results."
                if not results_list and "SELECT" in (sql_query or "").upper():
                    summary_text = "The query ran successfully, but returned no results."
                
                # Store the full response (text, SQL, and DataFrame) in the session state
                assistant_response = {
                    "summary": summary_text,
                    "sql": sql_query,
                    "df": df
                }
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                
                # Rerun the script to display the new message from the session state
                st.rerun()

# --- Connection Status Indicator ---
# This CSS places the status indicator in the bottom-left corner.
st.markdown("""
    <style>
    .status-indicator {
        position: fixed;
        bottom: 10px;
        left: 10px;
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 5px 10px;
        font-size: 14px;
        border: 1px solid #dcdcdc;
    }
    </style>
""", unsafe_allow_html=True)

# Check the backend status once per session and display it.
_, error = make_api_request(HEALTH_CHECK_URL)
status_text = "🟢 Backend Connected" if not error else "🔴 Backend Disconnected"
st.markdown(f'<div class="status-indicator">{status_text}</div>', unsafe_allow_html=True)
