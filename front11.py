import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import os
import re
import uuid

# --- Configuration ---
# The base URL for your Flask backend.
# BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5000")


BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://15.235.9.166:5010")



QUERY_URL = f"{BACKEND_BASE_URL}/query"
DISCOVER_CONTENT_URL = f"{BACKEND_BASE_URL}/discover-content"
HEALTH_CHECK_URL = f"{BACKEND_BASE_URL}/"

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="Conversational AI Database Agent",
    page_icon="🤖"
)

# --- Helper Functions ---

def make_api_request(url, method="GET", json_data=None, timeout=60):
    """A robust function to handle HTTP requests to the backend API."""
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as http_err:
        try:
            error_details = http_err.response.json()
            details_msg = error_details.get('details', str(http_err))
            error_msg = f"{error_details.get('error', 'An HTTP error occurred')}: {details_msg}"
            return None, error_msg
        except:
            return None, f"An HTTP error occurred: {http_err}"
    except requests.exceptions.ConnectionError:
        return None, f"Connection Error: Could not connect to the backend at {BACKEND_BASE_URL}. Is it running?"
    except Exception as e:
        return None, f"An unexpected error occurred: {e}"

def format_sql(sql_query):
    """Formats SQL for better readability in the UI."""
    if not isinstance(sql_query, str): return ""
    keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'ON', 'GROUP BY', 'ORDER BY', 'LIMIT']
    for keyword in keywords:
        sql_query = re.sub(rf'\b({keyword})\b', f'\n{keyword}', sql_query, flags=re.IGNORECASE)
    return sql_query.strip()

def create_visualization(df):
    """Analyzes a DataFrame and creates a relevant Plotly chart if possible."""
    if df.empty or len(df.columns) < 2: return None
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    if not numeric_cols or not categorical_cols: return None

    try:
        if df[categorical_cols[0]].nunique() > 1 and df[categorical_cols[0]].nunique() < 50:
             return px.bar(df, x=categorical_cols[0], y=numeric_cols[0],
                           title=f"Bar Chart: {numeric_cols[0]} by {categorical_cols[0]}", text_auto=True)
    except Exception:
        return None
    return None

def generate_session_id():
    """Generates a unique session ID for a new conversation."""
    return f"st-session-{uuid.uuid4()}"

# --- Session State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = generate_session_id()

# --- Sidebar UI ---
with st.sidebar:
    st.title("🧰 AI Database Agent")
    st.markdown("This agent can answer questions about your database and remembers the context of your conversation.")
    
    st.header("Session Controls")
    st.info(f"Current Session ID: `{st.session_state.session_id}`")
    
    if st.button("Start New Chat Session"):
        st.session_state.messages = []
        st.session_state.session_id = generate_session_id()
        st.rerun()

    st.header("System")
    if st.button("Check Backend Status"):
        with st.spinner("Pinging backend..."):
            _, error = make_api_request(HEALTH_CHECK_URL)
            if error: st.error(f"Backend Offline: {error}")
            else: st.success("Backend is connected and running.")

    st.header("Database Setup")
    if st.button("Discover/Refresh Schema", help="This scans your database and teaches the AI about its structure. Run this once to get started."):
        with st.spinner("Analyzing and embedding database schema..."):
            data, error = make_api_request(DISCOVER_CONTENT_URL, method="POST")
            if error: st.error(f"Discovery Failed: {error}")
            else: st.success(f"Discovery complete! {data.get('documents_added', 0)} schema documents were indexed.")

# --- Main Chat Interface ---
st.header("💬 Chat with your Database")
st.caption("You can ask follow-up questions to refine your results.")

# Display the chat history from the session state
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # This block is responsible for showing the SQL and results for assistant messages
        if message["role"] == "assistant":
            # Show the SQL query in an expandable section
            if "sql" in message and message["sql"]:
                with st.expander("View Generated SQL"):
                    st.code(format_sql(message["sql"]), language="sql")
            
            # Show the results in a table if they exist
            if "df" in message and not message["df"].empty:
                st.dataframe(message["df"], use_container_width=True)
                fig = create_visualization(message["df"])
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

# The chat input box at the bottom of the page
if prompt := st.chat_input("Ask a question about your data..."):
    # Add user's message to the chat history and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Send the user's query to the backend
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
                
                # Prepare the user-friendly text response
                assistant_response_content = f"I found {len(results_list)} results."
                if not results_list and "SELECT" in (sql_query or "").upper():
                    assistant_response_content = "I ran the query successfully, but it returned no results."
                elif not sql_query:
                     assistant_response_content = "I was unable to generate a SQL query for your request."
                st.markdown(assistant_response_content)

                # Store the complete response (text, SQL, and DataFrame) in the session state
                assistant_message = {
                    "role": "assistant",
                    "content": assistant_response_content,
                    "sql": sql_query,
                    "df": pd.DataFrame(results_list) if results_list else pd.DataFrame()
                }
                st.session_state.messages.append(assistant_message)
                
                # Rerun the script to display the new message with all its elements
                # This happens automatically after the 'with' block finishes
                st.rerun()