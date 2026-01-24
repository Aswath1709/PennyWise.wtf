# app.py

"""
PennyWise.wtf - Personal Finance Dashboard
Streamlit UI
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project to path
sys.path.append(str(Path(__file__).parent))

# Mock imports for the purpose of the script running if you don't have the backend files
try:
    from DataProcessing.database import load_transactions, get_summary, init_db, save_transactions, is_file_imported, \
        get_imported_files
    from DataProcessing.parser import parse_single_statement
    from DataProcessing.preprocess import sanitize, categorize
except ImportError:
    # Fallback for display purposes
    def init_db():
        pass


    def load_transactions():
        return pd.DataFrame()


    def save_transactions(df, source_file):
        return {'saved_count': 0, 'skipped_count': 0}


    def is_file_imported(name):
        return False


    def parse_single_statement(path, statement_type="credit"):
        return pd.DataFrame()


    def sanitize(df):
        return df


    def categorize(df):
        return df

# ========== PAGE CONFIG ==========

st.set_page_config(
    page_title="PennyWise.wtf",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== CUSTOM CSS (Minimal) ==========
# We rely on the standard Light Theme now.
# This CSS just makes the metric cards look like cards (shadow + border).

st.markdown("""
<style>
    /* Style the metric cards to pop out */
    [data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #d0d0d0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.05);
    }

    /* Ensure metric label is distinct */
    [data-testid="stMetricLabel"] {
        color: #555555;
        font-size: 14px;
    }

    /* Make the value pop */
    [data-testid="stMetricValue"] {
        color: #000000;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ========== INITIALIZE ==========

init_db()


# ========== HELPER FUNCTIONS ==========

@st.cache_data(ttl=60)
def get_transactions():
    """Load transactions with caching."""
    df = load_transactions()
    if not df.empty and 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.strftime('%Y-%m')
    return df


def refresh_data():
    """Clear cache and reload data."""
    st.cache_data.clear()


with st.sidebar:
    st.title("PennyWise.wtf")
    st.caption("Where The Funds?")
    st.markdown("---")

    # Navigation
    page = st.radio(
        "Navigate",
        ["📊 Dashboard", "💬 Chat", "📋 Transactions", "📤 Upload"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Quick Stats
    df = get_transactions()

    if not df.empty:
        st.markdown("### Quick Stats")
        st.metric("Total Transactions", len(df))

        expenses = df[df['amount'] < 0]['amount'].sum()
        st.metric("Total Expenses", f"${abs(expenses):,.2f}")

        if st.button("🔄 Refresh Data"):
            refresh_data()
            st.rerun()


def show_empty_state():
    """Show when no data is available."""
    st.markdown("""
    <div style="text-align: center; padding: 50px;">
        <h1>📂 No Data Yet</h1>
        <p style="font-size: 18px; color: #666;">
            Upload your first bank statement to get started
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Bank and Account Type Selection
        subcol1, subcol2 = st.columns(2)
        with subcol1:
            bank = st.selectbox(
                "🏦 Bank",
                ["Chase"],
                key="empty_bank"
            )
        with subcol2:
            account_type = st.selectbox(
                "💳 Type",
                ["Credit Card", "Debit/Checking"],
                key="empty_type"
            )

        statement_type = "credit" if account_type == "Credit Card" else "debit"

        uploaded_files = st.file_uploader(
            "Upload PDF Statements",
            type=['pdf'],
            accept_multiple_files=True,
            help=f"Upload {bank} {account_type} statement PDFs",
            key="empty_state_uploader"
        )

        if uploaded_files:
            if st.button("🚀 Import Statements", type="primary", key="empty_import_btn"):
                progress_bar = st.progress(0)
                status_text = st.empty()

                for index, file in enumerate(uploaded_files):
                    status_text.text(f"Processing {file.name}...")
                    process_upload(file, statement_type, bank)
                    progress_bar.progress((index + 1) / len(uploaded_files))

                status_text.text("✅ All files processed!")
                refresh_data()
                st.rerun()

    st.markdown("""
    <div style="text-align: center; margin-top: 30px;">
        <p style="color: #888;">Supported: Chase (Credit & Debit) • More banks coming soon</p>
    </div>
    """, unsafe_allow_html=True)


def process_upload(uploaded_file, statement_type: str = "credit", bank: str = "Chase"):
    """Process uploaded PDF. Returns True if successful, False otherwise."""

    if is_file_imported(uploaded_file.name):
        st.warning(f"⚠️ '{uploaded_file.name}' has already been imported.")
        return False

    # Save temp file
    temp_path = Path(f"/tmp/{uploaded_file.name}")
    # Create dir if not exists (for local testing)
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    try:
        # We use a status container for this specific file
        with st.status(f"Processing {uploaded_file.name}...", expanded=False) as status:
            # Parse
            st.write("📄 Parsing PDF...")
            df = parse_single_statement(temp_path, statement_type)
            st.write(f"   Found {len(df)} transactions")

            if df.empty:
                status.update(label=f"❌ {uploaded_file.name}: No transactions found", state="error")
                return False

            # Sanitize
            st.write("🔒 Sanitizing sensitive data...")
            df = sanitize(df)

            # Categorize
            st.write("🏷️ Categorizing transactions...")
            df = categorize(df)

            # Save with card_type and bank
            st.write("💾 Saving to database...")
            result = save_transactions(df, source_file=uploaded_file.name, card_type=statement_type, bank=bank)

            status.update(label=f"✅ {uploaded_file.name} Complete!", state="complete")

        st.success(f"Imported {result['saved_count']} transactions from {uploaded_file.name}")

        if result['skipped_count'] > 0:
            st.info(f"Skipped {result['skipped_count']} duplicate transactions")

        return True

    except Exception as e:
        st.error(f"Error processing {uploaded_file.name}: {e}")
        return False

    finally:
        if temp_path.exists():
            temp_path.unlink()


# ========== DASHBOARD PAGE ==========

def show_dashboard():
    """Main dashboard with stats and charts."""
    df = get_transactions()

    if df.empty:
        show_empty_state()
        return

    st.title("📊 Dashboard")

    # Date range filter
    col1, col2 = st.columns([3, 1])
    with col2:
        date_range = st.selectbox(
            "Time Period",
            ["All Time", "Last 30 Days", "Last 90 Days", "Last 6 Months", "This Year"],
            index=0
        )

    # Filter by date
    df_filtered = filter_by_date_range(df, date_range)

    # Metrics Row
    st.markdown("### Overview")
    col1, col2, col3, col4 = st.columns(4)

    income = df_filtered[df_filtered['amount'] > 0]['amount'].sum()
    expenses = abs(df_filtered[df_filtered['amount'] < 0]['amount'].sum())
    net = income - expenses

    with col1:
        st.metric("💵 Income", f"${income:,.2f}")
    with col2:
        st.metric("💸 Expenses", f"${expenses:,.2f}")
    with col3:
        st.metric("📊 Net", f"${net:,.2f}", delta=f"${net:,.2f}")
    with col4:
        st.metric("🧾 Transactions", len(df_filtered))

    st.markdown("---")

    # Charts Row
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Spending by Category")
        show_category_pie(df_filtered)

    with col2:
        st.markdown("### Monthly Spending Trend")
        show_monthly_trend(df_filtered)

    st.markdown("---")

    # Top Merchants
    st.markdown("### Top Merchants")
    show_top_merchants(df_filtered)


def filter_by_date_range(df, date_range):
    """Filter dataframe by date range."""
    if date_range == "All Time":
        return df

    today = datetime.now()

    if date_range == "Last 30 Days":
        start = today - timedelta(days=30)
    elif date_range == "Last 90 Days":
        start = today - timedelta(days=90)
    elif date_range == "Last 6 Months":
        start = today - timedelta(days=180)
    elif date_range == "This Year":
        start = datetime(today.year, 1, 1)
    else:
        return df

    return df[df['date'] >= start]


def show_category_pie(df):
    """Pie chart of spending by category."""
    expenses = df[df['amount'] < 0].copy()

    if expenses.empty:
        st.info("No expense data to display")
        return

    expenses['amount'] = expenses['amount'].abs()
    by_category = expenses.groupby('category')['amount'].sum().reset_index()
    by_category = by_category.sort_values('amount', ascending=False)

    fig = px.pie(
        by_category,
        values='amount',
        names='category',
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    # Use standard light theme colors
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
    )

    st.plotly_chart(fig, use_container_width=True)


def show_monthly_trend(df):
    """Line chart of monthly spending."""
    expenses = df[df['amount'] < 0].copy()

    if expenses.empty:
        st.info("No expense data to display")
        return

    expenses['amount'] = expenses['amount'].abs()
    monthly = expenses.groupby('month')['amount'].sum().reset_index()
    monthly = monthly.sort_values('month')

    fig = px.line(
        monthly,
        x='month',
        y='amount',
        markers=True
    )
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Amount ($)",
        margin=dict(t=0, b=0, l=0, r=0),
        xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
        yaxis=dict(showgrid=True, gridcolor='#f0f0f0')
    )
    fig.update_traces(fill='tozeroy', line_color='#667eea')

    st.plotly_chart(fig, use_container_width=True)


def show_top_merchants(df):
    """Bar chart of top merchants."""
    expenses = df[df['amount'] < 0].copy()

    if expenses.empty:
        st.info("No expense data to display")
        return

    expenses['amount'] = expenses['amount'].abs()
    by_merchant = expenses.groupby('description')['amount'].sum().reset_index()
    by_merchant = by_merchant.sort_values('amount', ascending=True).tail(10)

    fig = px.bar(
        by_merchant,
        x='amount',
        y='description',
        orientation='h',
        color='amount',
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        xaxis_title="Amount ($)",
        yaxis_title="",
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(t=0, b=0, l=0, r=0),
        xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
    )

    st.plotly_chart(fig, use_container_width=True)


# ========== CHAT PAGE ==========

def show_chat():
    """Chat interface with the finance agent."""
    st.title("💬 Chat with Your Data")

    df = get_transactions()

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Initialize agent
    if "agent" not in st.session_state:
        try:
            from Agent.agent import FinanceAgent
            st.session_state.agent = FinanceAgent()
        except Exception as e:
            st.session_state.agent = None

    # Empty state message
    if df.empty:
        st.warning("""
        📂 **No transaction data yet!**
        Upload a bank statement first.
        """)
        return

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_path" in message and message["chart_path"]:
                if Path(message["chart_path"]).exists():
                    st.image(message["chart_path"])

    # Chat input
    if prompt := st.chat_input("Ask about your finances..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            if st.session_state.agent:
                with st.spinner("Analyzing..."):
                    try:
                        response = st.session_state.agent.ask(prompt)
                        st.markdown(response)

                        chart_path = None
                        if st.session_state.agent.last_chart_path:
                            chart_path = st.session_state.agent.last_chart_path
                            if Path(chart_path).exists():
                                st.image(chart_path)

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response,
                            "chart_path": chart_path
                        })
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.error("Agent not initialized. Check your Gemini API key.")

    # Clear chat button
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        if st.session_state.agent:
            st.session_state.agent.reset()
        st.rerun()


# ========== TRANSACTIONS PAGE ==========

def show_transactions():
    """Transactions table with filters."""
    st.title("📋 Transactions")

    df = get_transactions()

    if df.empty:
        show_empty_state()
        return

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        categories = ["All"] + sorted(df['category'].unique().tolist())
        selected_category = st.selectbox("Category", categories)

    with col2:
        search = st.text_input("Search", placeholder="Merchant name...")

    with col3:
        if not df.empty:
            min_date = df['date'].min().date()
            start_date = st.date_input("From", min_date)
        else:
            start_date = datetime.now().date()

    with col4:
        if not df.empty:
            max_date = df['date'].max().date()
            end_date = st.date_input("To", max_date)
        else:
            end_date = datetime.now().date()

    # Apply filters
    filtered = df.copy()

    if selected_category != "All":
        filtered = filtered[filtered['category'] == selected_category]

    if search:
        filtered = filtered[filtered['description'].str.contains(search, case=False, na=False)]

    if not df.empty:
        filtered = filtered[(filtered['date'].dt.date >= start_date) & (filtered['date'].dt.date <= end_date)]

    # Sort
    filtered = filtered.sort_values('date', ascending=False)

    # Summary
    st.markdown(f"**Showing {len(filtered)} transactions**")

    total = filtered['amount'].sum()
    if total < 0:
        st.markdown(f"**Total: <span style='color: #d9534f;'>-${abs(total):,.2f}</span>**", unsafe_allow_html=True)
    else:
        st.markdown(f"**Total: <span style='color: #28a745;'>${total:,.2f}</span>**", unsafe_allow_html=True)

    # Display table
    display_df = filtered[['date', 'description', 'amount', 'category']].copy()
    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['amount'] = display_df['amount'].apply(lambda x: f"${x:,.2f}")
    display_df.columns = ['Date', 'Description', 'Amount', 'Category']

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=500
    )

    # Download button
    csv = filtered.to_csv(index=False)
    st.download_button(
        "📥 Download CSV",
        csv,
        "transactions.csv",
        "text/csv"
    )


# ========== UPLOAD PAGE ==========

def show_upload():
    """Upload page for new statements."""
    st.title("📤 Upload Statement")

    st.markdown("Upload your bank statements to import transactions.")

    st.markdown("---")

    # Bank and Account Type Selection
    col1, col2 = st.columns(2)

    with col1:
        bank = st.selectbox(
            "🏦 Select Bank",
            ["Chase"],
            help="More banks coming soon!"
        )

    with col2:
        account_type = st.selectbox(
            "💳 Account Type",
            ["Credit Card", "Debit/Checking"],
            help="Select the type of statement you're uploading"
        )

    # Map to parser type
    statement_type = "credit" if account_type == "Credit Card" else "debit"

    st.markdown("---")

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=['pdf'],
        accept_multiple_files=True,
        help=f"Upload {bank} {account_type} statement PDFs"
    )

    if uploaded_files:
        st.markdown(f"**Selected {len(uploaded_files)} files**")

        if st.button("🚀 Import Statements", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            success_count = 0

            # Loop through files
            for index, file in enumerate(uploaded_files):
                status_text.text(f"Processing file {index + 1} of {len(uploaded_files)}: {file.name}")

                # Run processing with statement type and bank
                if process_upload(file, statement_type, bank):
                    success_count += 1

                # Update progress
                progress_bar.progress((index + 1) / len(uploaded_files))

            status_text.text("✅ Batch processing complete!")
            st.success(f"Successfully processed {success_count} of {len(uploaded_files)} files.")

            # Refresh data
            refresh_data()

    # Show import history
    st.markdown("---")
    st.markdown("### Import History")

    try:
        history = get_imported_files()
        if history.empty:
            st.info("No files imported yet")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True)
    except:
        st.info("No import history available")


# ========== MAIN ROUTER ==========

def main():
    if "📊 Dashboard" in page:
        show_dashboard()
    elif "💬 Chat" in page:
        show_chat()
    elif "📋 Transactions" in page:
        show_transactions()
    elif "📤 Upload" in page:
        show_upload()


if __name__ == "__main__":
    main()