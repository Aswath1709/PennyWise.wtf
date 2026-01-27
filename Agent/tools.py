# Agent/tools.py

"""
Finance Agent Tools

Tool definitions (JSON schema for LLM) + implementations (Python functions)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for DataProcessing imports
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import matplotlib

matplotlib.use('Agg')  # Use non-interactive backend for Streamlit
import matplotlib.pyplot as plt

# Try to import plotly for interactive charts
try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# Import database - try both ways for compatibility
try:
    from DataProcessing.database import load_transactions, run_query, get_summary
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from DataProcessing.database import load_transactions, run_query, get_summary

# Chart output directory
CHARTS_DIR = Path(__file__).parent.parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

# ========== TOOL DEFINITIONS (Single Source of Truth) ==========

TOOL_DEFINITIONS = [
    {
        "name": "get_data_summary",
        "description": "Get overview of available data: date range, total transactions, categories, banks, card types (credit/debit), account numbers (last 4 digits), total income/expenses. Call this first to understand what data exists.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "query_transactions",
        "description": "Search and filter transactions. Returns matching transactions (max 50).",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter from date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter until date (YYYY-MM-DD)"},
                "category": {"type": "string", "description": "Filter by category"},
                "description_contains": {"type": "string", "description": "Search merchant name"},
                "min_amount": {"type": "number", "description": "Minimum amount"},
                "max_amount": {"type": "number", "description": "Maximum amount"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name (e.g., 'Chase')"},
                "account_last4": {"type": "string",
                                  "description": "Filter by last 4 digits of account number (e.g., '1234')"}
            }
        }
    },
    {
        "name": "aggregate",
        "description": "Calculate sum, average, count, min, or max of transactions. Can group by category, month, merchant, card_type, bank, or account_last4. Use for 'how much did I spend' questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "description": "Math operation: sum, avg, count, min, max"},
                "group_by": {"type": "string",
                             "description": "Group by: category, month, merchant, card_type, bank, or account_last4"},
                "start_date": {"type": "string", "description": "Filter from date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter until date (YYYY-MM-DD)"},
                "category": {"type": "string", "description": "Filter by category"},
                "description_contains": {"type": "string", "description": "Filter by merchant name"},
                "expenses_only": {"type": "boolean", "description": "Only expenses (negative amounts)"},
                "income_only": {"type": "boolean", "description": "Only income (positive amounts)"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name (e.g., 'Chase')"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"}
            },
            "required": ["operation"]
        }
    },
    {
        "name": "compare_periods",
        "description": "Compare spending between two time periods.",
        "parameters": {
            "type": "object",
            "properties": {
                "period1_start": {"type": "string", "description": "First period start (YYYY-MM-DD)"},
                "period1_end": {"type": "string", "description": "First period end (YYYY-MM-DD)"},
                "period2_start": {"type": "string", "description": "Second period start (YYYY-MM-DD)"},
                "period2_end": {"type": "string", "description": "Second period end (YYYY-MM-DD)"},
                "group_by": {"type": "string", "description": "Compare by: total or category"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"}
            },
            "required": ["period1_start", "period1_end", "period2_start", "period2_end"]
        }
    },
    {
        "name": "find_recurring",
        "description": "Find recurring/subscription charges that appear multiple times.",
        "parameters": {
            "type": "object",
            "properties": {
                "min_occurrences": {"type": "integer", "description": "Minimum occurrences (default: 3)"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"}
            }
        }
    },
    {
        "name": "detect_anomalies",
        "description": "Find unusual transactions significantly higher than average.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Check specific category only"},
                "threshold": {"type": "number", "description": "Standard deviations (default: 2)"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"}
            }
        }
    },
    {
        "name": "run_sql",
        "description": "Run custom SQL query. Table: transactions. Columns: id, date, description, amount, category, card_type, bank, account_last4, source_file.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_chart",
        "description": """Create a visual chart. ALWAYS use this when user asks for visualization, charts, or graphs.

Chart types:
- pie: For showing distribution/breakdown of a single period
- bar: For comparing values side-by-side. Use group_by="month" to show all months as separate bars.
- line: For showing trends over time (use with group_by="month")

Examples:
- "pie chart of November spending" → chart_type="pie", group_by="category", start_date="2024-11-01", end_date="2024-11-30"
- "bar chart comparing each month" → chart_type="bar", group_by="month"
- "monthly spending trend" → chart_type="line", group_by="month"
- "pie chart for account 1234" → chart_type="pie", group_by="category", account_last4="1234"

Can be called multiple times with different account_last4 values to create separate charts for each account.""",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "description": "Type: pie, bar, or line"},
                "group_by": {"type": "string", "description": "Group by: category, month, or merchant"},
                "title": {"type": "string", "description": "Chart title"},
                "start_date": {"type": "string", "description": "Filter from date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter until date (YYYY-MM-DD)"},
                "expenses_only": {"type": "boolean", "description": "Only show expenses (default: true)"},
                "top_n": {"type": "integer", "description": "Show only top N items (default: 10)"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name"}
            },
            "required": ["chart_type", "group_by"]
        }
    },
    {
        "name": "compare_periods_chart",
        "description": """REQUIRED when user asks to COMPARE two periods AND wants a CHART/GRAPH/VISUAL.

Creates a grouped bar chart with categories on X-axis and TWO bars per category (one for each period).

ALWAYS use this when user says:
- "compare October vs November, show me a chart"
- "bar graph comparing spending between two months"
- "visualize the difference between Q1 and Q2" """,
        "parameters": {
            "type": "object",
            "properties": {
                "period1_start": {"type": "string", "description": "First period start (YYYY-MM-DD)"},
                "period1_end": {"type": "string", "description": "First period end (YYYY-MM-DD)"},
                "period2_start": {"type": "string", "description": "Second period start (YYYY-MM-DD)"},
                "period2_end": {"type": "string", "description": "Second period end (YYYY-MM-DD)"},
                "period1_label": {"type": "string", "description": "Label like 'October 2024'"},
                "period2_label": {"type": "string", "description": "Label like 'November 2024'"},
                "group_by": {"type": "string", "description": "Compare by: category or merchant"},
                "title": {"type": "string", "description": "Chart title"}
            },
            "required": ["period1_start", "period1_end", "period2_start", "period2_end"]
        }
    },
    {
        "name": "compare_accounts_chart",
        "description": """REQUIRED when user asks to COMPARE two accounts AND wants a CHART/GRAPH/VISUAL.

Creates a grouped bar chart with categories on X-axis and TWO bars per category (one for each account).

ALWAYS use this when user says:
- "compare spending between account 1234 and 5678"
- "bar graph comparing my two accounts"
- "visualize spending by category for accounts ending in 1122 vs 0594"
- "compare transactions across categories between accounts" """,
        "parameters": {
            "type": "object",
            "properties": {
                "account1_last4": {"type": "string", "description": "First account last 4 digits (e.g., '1234')"},
                "account2_last4": {"type": "string", "description": "Second account last 4 digits (e.g., '5678')"},
                "group_by": {"type": "string", "description": "Compare by: category or merchant (default: category)"},
                "title": {"type": "string", "description": "Chart title"},
                "start_date": {"type": "string", "description": "Filter from date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter until date (YYYY-MM-DD)"},
                "expenses_only": {"type": "boolean", "description": "Only expenses (default: true)"}
            },
            "required": ["account1_last4", "account2_last4"]
        }
    },
    {
        "name": "analyze_and_chart",
        "description": """USE THIS when user wants BOTH a text breakdown AND a visual chart in ONE response.

Returns the data breakdown AND creates a chart - all in one call.

ALWAYS use this when user says:
- "list the months and show a bar graph"
- "show me categories with a pie chart"
- "which merchants cost most? show a chart too"
- Any request asking for BOTH words/list AND a visual""",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "description": "pie, bar, or line"},
                "group_by": {"type": "string", "description": "category, month, or merchant"},
                "start_date": {"type": "string", "description": "Filter from date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter until date (YYYY-MM-DD)"},
                "expenses_only": {"type": "boolean", "description": "Only expenses (default: true)"},
                "top_n": {"type": "integer", "description": "Limit results (default: 10)"},
                "account_last4": {"type": "string", "description": "Filter by last 4 digits of account number"},
                "card_type": {"type": "string", "description": "Filter by card type: 'credit' or 'debit'"},
                "bank": {"type": "string", "description": "Filter by bank name"}
            },
            "required": ["chart_type", "group_by"]
        }
    }
]


def get_gemini_tools():
    """Convert TOOL_DEFINITIONS to Gemini FunctionDeclarations."""
    from google.generativeai.types import FunctionDeclaration, Tool

    declarations = []
    for tool in TOOL_DEFINITIONS:
        declarations.append(FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=tool.get("parameters", {"type": "object", "properties": {}})
        ))

    return Tool(function_declarations=declarations)


# ========== TOOL IMPLEMENTATIONS ==========

class FinanceTools:
    """Implements all finance agent tools."""

    def __init__(self):
        self.df = load_transactions()

    def reload(self):
        """Reload data from database."""
        self.df = load_transactions()

    def execute(self, tool_name: str, params: dict) -> dict:
        """Route tool call to correct method."""
        method = getattr(self, tool_name, None)

        if not method:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return method(**params)
        except Exception as e:
            return {"error": str(e)}

    # ---------- Tool: get_data_summary ----------

    def get_data_summary(self) -> dict:
        """Get overview of available data."""
        if self.df.empty:
            return {"status": "No data available"}

        result = {
            "total_transactions": len(self.df),
            "date_range": {
                "start": self.df['date'].min().strftime('%Y-%m-%d'),
                "end": self.df['date'].max().strftime('%Y-%m-%d')
            },
            "categories": self.df['category'].unique().tolist(),
            "total_income": round(self.df[self.df['amount'] > 0]['amount'].sum(), 2),
            "total_expenses": round(abs(self.df[self.df['amount'] < 0]['amount'].sum()), 2)
        }

        # Add card_type info if column exists
        if 'card_type' in self.df.columns:
            card_types = self.df['card_type'].dropna().unique().tolist()
            result["card_types"] = card_types if card_types else ["unknown"]

        # Add bank info if column exists
        if 'bank' in self.df.columns:
            banks = self.df['bank'].dropna().unique().tolist()
            result["banks"] = banks if banks else ["unknown"]

        # Add account numbers (last 4 digits) if column exists
        if 'account_last4' in self.df.columns:
            accounts = self.df['account_last4'].dropna().unique().tolist()
            result["accounts"] = [f"****{acc}" for acc in accounts] if accounts else ["unknown"]

        return result

    # ---------- Tool: query_transactions ----------

    def query_transactions(
            self,
            start_date: str = None,
            end_date: str = None,
            category: str = None,
            description_contains: str = None,
            min_amount: float = None,
            max_amount: float = None,
            card_type: str = None,
            bank: str = None,
            account_last4: str = None
    ) -> dict:
        """Filter and return transactions."""
        result = self.df.copy()

        # Apply filters
        if start_date:
            result = result[result['date'] >= start_date]
        if end_date:
            result = result[result['date'] <= end_date]
        if category:
            result = result[result['category'].str.lower() == category.lower()]
        if description_contains:
            result = result[result['description'].str.contains(description_contains, case=False, na=False)]
        if min_amount is not None:
            result = result[result['amount'] >= min_amount]
        if max_amount is not None:
            result = result[result['amount'] <= max_amount]
        if card_type and 'card_type' in result.columns:
            result = result[result['card_type'].str.lower() == card_type.lower()]
        if bank and 'bank' in result.columns:
            result = result[result['bank'].str.lower() == bank.lower()]
        if account_last4 and 'account_last4' in result.columns:
            result = result[result['account_last4'] == account_last4]

        # Format output
        result = result.head(50)  # Limit results
        result['date'] = result['date'].dt.strftime('%Y-%m-%d')

        # Include card_type, bank, account_last4 in output if they exist
        output_cols = ['date', 'description', 'amount', 'category']
        if 'card_type' in result.columns:
            output_cols.append('card_type')
        if 'bank' in result.columns:
            output_cols.append('bank')
        if 'account_last4' in result.columns:
            output_cols.append('account_last4')

        return {
            "count": len(result),
            "transactions": result[output_cols].to_dict('records')
        }

    # ---------- Tool: aggregate ----------

    def aggregate(
            self,
            operation: str,
            group_by: str = None,
            start_date: str = None,
            end_date: str = None,
            category: str = None,
            description_contains: str = None,
            expenses_only: bool = False,
            income_only: bool = False,
            card_type: str = None,
            bank: str = None,
            account_last4: str = None
    ) -> dict:
        """Aggregate transactions with optional grouping."""
        data = self.df.copy()

        # Apply filters
        if start_date:
            data = data[data['date'] >= start_date]
        if end_date:
            data = data[data['date'] <= end_date]
        if category:
            data = data[data['category'].str.lower() == category.lower()]
        if description_contains:
            data = data[data['description'].str.contains(description_contains, case=False, na=False)]
        if card_type and 'card_type' in data.columns:
            data = data[data['card_type'].str.lower() == card_type.lower()]
        if bank and 'bank' in data.columns:
            data = data[data['bank'].str.lower() == bank.lower()]
        if account_last4 and 'account_last4' in data.columns:
            data = data[data['account_last4'] == account_last4]

        if data.empty:
            return {"result": 0, "count": 0, "note": "No matching transactions"}

        # When querying a specific merchant, show breakdown before filtering
        if description_contains and operation == "sum" and not expenses_only and not income_only:
            expenses = data[data['amount'] < 0]['amount'].sum()
            refunds = data[data['amount'] > 0]['amount'].sum()
            net = data['amount'].sum()

            return {
                "total_spent": round(abs(expenses), 2),
                "total_refunds": round(refunds, 2),
                "net": round(net, 2),
                "transaction_count": len(data),
                "expense_count": len(data[data['amount'] < 0]),
                "refund_count": len(data[data['amount'] > 0])
            }

        # Apply expense/income filters
        if expenses_only:
            data = data[data['amount'] < 0]
        if income_only:
            data = data[data['amount'] > 0]

        if data.empty:
            return {"result": 0, "count": 0, "note": "No matching transactions"}

        # Prepare grouping
        if group_by == "month":
            data['group'] = data['date'].dt.strftime('%Y-%m')
        elif group_by == "merchant":
            data['group'] = data['description']
        elif group_by == "category":
            data['group'] = data['category']
        elif group_by == "card_type" and 'card_type' in data.columns:
            data['group'] = data['card_type'].fillna('unknown')
        elif group_by == "bank" and 'bank' in data.columns:
            data['group'] = data['bank'].fillna('unknown')
        elif group_by == "account_last4" and 'account_last4' in data.columns:
            data['group'] = data['account_last4'].fillna('unknown')

        # Perform aggregation
        if group_by:
            if operation == "sum":
                result = data.groupby('group')['amount'].sum().round(2).to_dict()
                result = dict(sorted(result.items(), key=lambda x: abs(x[1]), reverse=True))
                return {"grouped_results": result, "count": len(data)}

            elif operation == "avg":
                result = data.groupby('group')['amount'].mean().round(2).to_dict()
                result = dict(sorted(result.items(), key=lambda x: abs(x[1]), reverse=True))
                return {"grouped_results": result, "count": len(data)}

            elif operation == "count":
                result = data.groupby('group').size().to_dict()
                result = dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
                return {"grouped_results": result, "count": len(data)}

            elif operation == "min":
                # Return full transaction details for each group
                idx = data.groupby('group')['amount'].idxmin()
                transactions = []
                for group_name, row_idx in idx.items():
                    row = data.loc[row_idx]
                    transactions.append({
                        "group": group_name,
                        "date": row['date'].strftime('%Y-%m-%d'),
                        "description": row['description'],
                        "amount": round(row['amount'], 2),
                        "category": row['category']
                    })
                transactions = sorted(transactions, key=lambda x: x['amount'])
                return {"transactions": transactions, "count": len(transactions)}

            elif operation == "max":
                # Return full transaction details for each group
                idx = data.groupby('group')['amount'].idxmax()
                transactions = []
                for group_name, row_idx in idx.items():
                    row = data.loc[row_idx]
                    transactions.append({
                        "group": group_name,
                        "date": row['date'].strftime('%Y-%m-%d'),
                        "description": row['description'],
                        "amount": round(row['amount'], 2),
                        "category": row['category']
                    })
                transactions = sorted(transactions, key=lambda x: abs(x['amount']), reverse=True)
                return {"transactions": transactions, "count": len(transactions)}

        else:
            if operation == "sum":
                result = round(data['amount'].sum(), 2)
            elif operation == "avg":
                result = round(data['amount'].mean(), 2)
            elif operation == "count":
                result = len(data)
            elif operation == "min":
                row = data.loc[data['amount'].idxmin()]
                return {
                    "result": round(row['amount'], 2),
                    "transaction": {
                        "date": row['date'].strftime('%Y-%m-%d'),
                        "description": row['description'],
                        "amount": round(row['amount'], 2)
                    }
                }
            elif operation == "max":
                row = data.loc[data['amount'].idxmax()]
                return {
                    "result": round(row['amount'], 2),
                    "transaction": {
                        "date": row['date'].strftime('%Y-%m-%d'),
                        "description": row['description'],
                        "amount": round(row['amount'], 2)
                    }
                }

            return {"result": result, "count": len(data)}

    # ---------- Tool: compare_periods ----------

    def compare_periods(
            self,
            period1_start: str,
            period1_end: str,
            period2_start: str,
            period2_end: str,
            group_by: str = "total"
    ) -> dict:
        """Compare spending between two periods."""
        p1 = self.df[(self.df['date'] >= period1_start) & (self.df['date'] <= period1_end)]
        p2 = self.df[(self.df['date'] >= period2_start) & (self.df['date'] <= period2_end)]

        if group_by == "total":
            p1_total = round(p1['amount'].sum(), 2)
            p2_total = round(p2['amount'].sum(), 2)
            diff = round(p2_total - p1_total, 2)
            pct = round((diff / abs(p1_total) * 100), 1) if p1_total != 0 else 0

            return {
                "period1": {"dates": f"{period1_start} to {period1_end}", "total": p1_total},
                "period2": {"dates": f"{period2_start} to {period2_end}", "total": p2_total},
                "difference": diff,
                "percent_change": pct
            }
        else:
            p1_cat = p1.groupby('category')['amount'].sum().round(2).to_dict()
            p2_cat = p2.groupby('category')['amount'].sum().round(2).to_dict()

            return {
                "period1": {"dates": f"{period1_start} to {period1_end}", "by_category": p1_cat},
                "period2": {"dates": f"{period2_start} to {period2_end}", "by_category": p2_cat}
            }

    # ---------- Tool: find_recurring ----------

    def find_recurring(self, min_occurrences: int = 3) -> dict:
        """Find recurring charges."""
        merchant_stats = self.df.groupby('description').agg(
            count=('amount', 'count'),
            avg_amount=('amount', lambda x: round(x.mean(), 2)),
            total=('amount', lambda x: round(x.sum(), 2))
        ).reset_index()

        recurring = merchant_stats[merchant_stats['count'] >= min_occurrences]
        recurring = recurring.sort_values('count', ascending=False)

        return {
            "recurring_count": len(recurring),
            "recurring_charges": recurring.to_dict('records')
        }

    # ---------- Tool: detect_anomalies ----------

    def detect_anomalies(self, category: str = None, threshold: float = 2) -> dict:
        """Find unusual transactions."""
        data = self.df.copy()

        if category:
            data = data[data['category'].str.lower() == category.lower()]

        if data.empty:
            return {"anomalies": [], "note": "No data to analyze"}

        # Only look at expenses
        expenses = data[data['amount'] < 0].copy()

        if len(expenses) < 3:
            return {"anomalies": [], "note": "Not enough transactions to detect anomalies"}

        mean = expenses['amount'].mean()
        std = expenses['amount'].std()

        # Find anomalies (more negative than usual)
        anomalies = expenses[expenses['amount'] < (mean - threshold * std)]
        anomalies = anomalies.sort_values('amount')
        anomalies['date'] = anomalies['date'].dt.strftime('%Y-%m-%d')

        return {
            "anomaly_count": len(anomalies),
            "threshold_used": f"{threshold} standard deviations",
            "anomalies": anomalies[['date', 'description', 'amount', 'category']].to_dict('records')
        }

    # ---------- Tool: run_sql ----------

    def run_sql(self, query: str) -> dict:
        """Run custom SQL query."""
        try:
            result = run_query(query)

            if 'date' in result.columns:
                result['date'] = pd.to_datetime(result['date']).dt.strftime('%Y-%m-%d')

            return {
                "count": len(result),
                "results": result.to_dict('records')
            }
        except Exception as e:
            return {"error": str(e)}

    # ---------- Tool: create_chart ----------

    def create_chart(
            self,
            chart_type: str,
            group_by: str,
            title: str = None,
            start_date: str = None,
            end_date: str = None,
            expenses_only: bool = True,
            top_n: int = 10,
            account_last4: str = None,
            card_type: str = None,
            bank: str = None
    ) -> dict:
        """Create a visual chart and save to file."""
        data = self.df.copy()

        # Apply filters
        if start_date:
            data = data[data['date'] >= start_date]
        if end_date:
            data = data[data['date'] <= end_date]
        if account_last4 and 'account_last4' in data.columns:
            data = data[data['account_last4'] == account_last4]
        if card_type and 'card_type' in data.columns:
            data = data[data['card_type'].str.lower() == card_type.lower()]
        if bank and 'bank' in data.columns:
            data = data[data['bank'].str.lower() == bank.lower()]
        if expenses_only:
            data = data[data['amount'] < 0]
            data['amount'] = data['amount'].abs()  # Make positive for charting

        if data.empty:
            return {"error": "No data matching filters"}

        # Prepare grouping
        if group_by == "month":
            data['group'] = data['date'].dt.strftime('%Y-%m')
        elif group_by == "merchant":
            data['group'] = data['description']
        elif group_by == "category":
            data['group'] = data['category']

        # Aggregate data
        chart_data = data.groupby('group')['amount'].sum().round(2)
        chart_data = chart_data.sort_values(ascending=False)

        # Limit to top N (except for line charts)
        if chart_type != "line" and len(chart_data) > top_n:
            other = chart_data[top_n:].sum()
            chart_data = chart_data[:top_n]
            if other > 0:
                chart_data['Other'] = other

        # Generate title
        if not title:
            date_range = ""
            if start_date and end_date:
                date_range = f" ({start_date} to {end_date})"
            elif start_date:
                date_range = f" (from {start_date})"
            elif end_date:
                date_range = f" (until {end_date})"

            account_label = f" - Account ****{account_last4}" if account_last4 else ""
            title = f"Spending by {group_by.title()}{date_range}{account_label}"

        # Create chart
        plt.style.use('seaborn-v0_8-darkgrid')

        if chart_type == "pie":
            total = chart_data.sum()

            # Use Plotly for interactive pie chart if available
            if PLOTLY_AVAILABLE:
                colors = ['#8dd3c7', '#bebada', '#fb8072', '#80b1d3', '#fdb462',
                          '#b3de69', '#fccde5', '#d9d9d9', '#bc80bd', '#ccebc5']

                fig = go.Figure(data=[go.Pie(
                    labels=chart_data.index.tolist(),
                    values=chart_data.values.tolist(),
                    hole=0.3,  # Donut style
                    textinfo='none',  # No text on slices
                    hovertemplate='<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>',
                    marker=dict(colors=colors[:len(chart_data)])
                )])

                fig.update_layout(
                    title=dict(text=title, font=dict(size=18, color='#333')),
                    showlegend=True,
                    legend=dict(
                        orientation="v",
                        yanchor="middle",
                        y=0.5,
                        xanchor="left",
                        x=1.02,
                        font=dict(size=12)
                    ),
                    margin=dict(t=60, b=20, l=20, r=150),
                    paper_bgcolor='white',
                    plot_bgcolor='white'
                )

                # Save as HTML for interactive viewing
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{chart_type}_{group_by}_{timestamp}.html"
                filepath = CHARTS_DIR / filename
                fig.write_html(str(filepath), include_plotlyjs='cdn')

                # Also save JSON for Streamlit to render
                json_filename = f"{chart_type}_{group_by}_{timestamp}.json"
                json_filepath = CHARTS_DIR / json_filename
                fig.write_json(str(json_filepath))

                return {
                    "chart_created": True,
                    "chart_path": str(json_filepath),
                    "chart_type": "plotly_pie",
                    "interactive": True,
                    "data_points": len(chart_data),
                    "total": round(total, 2),
                    "_note": "Interactive chart saved. DO NOT include the chart_path in your response."
                }

            # Fallback to matplotlib if plotly not available
            fig, ax = plt.subplots(figsize=(12, 8))
            colors = plt.cm.Set3(range(len(chart_data)))

            wedges, texts = ax.pie(
                chart_data.values,
                colors=colors,
                startangle=90
            )

            legend_labels = [f"{k}: ${v:,.0f} ({v / total * 100:.1f}%)" for k, v in chart_data.items()]
            ax.legend(wedges, legend_labels, title="Categories", loc="center left",
                      bbox_to_anchor=(1, 0, 0.5, 1), fontsize=10)

            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{chart_type}_{group_by}_{timestamp}.png"
            filepath = CHARTS_DIR / filename
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            return {
                "chart_created": True,
                "chart_path": str(filepath),
                "chart_type": chart_type,
                "interactive": False,
                "data_points": len(chart_data),
                "total": round(total, 2),
                "_note": "Chart saved. DO NOT include the chart_path in your response."
            }

        plt.figure(figsize=(10, 6))

        if chart_type == "bar":
            # Sort chronologically if grouped by month
            if group_by == "month":
                chart_data = chart_data.sort_index()

            colors = plt.cm.viridis([i / len(chart_data) for i in range(len(chart_data))])
            bars = plt.bar(range(len(chart_data)), chart_data.values, color=colors)
            plt.xticks(range(len(chart_data)), chart_data.index, rotation=45, ha='right')
            plt.ylabel('Amount ($)')
            plt.title(title, fontsize=14, fontweight='bold')

            # Add value labels on bars
            for bar, val in zip(bars, chart_data.values):
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                         f'${val:,.0f}', ha='center', va='bottom', fontsize=9)

        elif chart_type == "line":
            # Sort by date for line chart
            chart_data = chart_data.sort_index()
            plt.plot(chart_data.index, chart_data.values, marker='o', linewidth=2, markersize=8)
            plt.fill_between(chart_data.index, chart_data.values, alpha=0.3)
            plt.xticks(rotation=45, ha='right')
            plt.ylabel('Amount ($)')
            plt.title(title, fontsize=14, fontweight='bold')

            # Add value labels
            for i, (x, y) in enumerate(zip(chart_data.index, chart_data.values)):
                plt.annotate(f'${y:,.0f}', (x, y), textcoords="offset points",
                             xytext=(0, 10), ha='center', fontsize=9)

        plt.tight_layout()

        # Save chart
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{chart_type}_{group_by}_{timestamp}.png"
        filepath = CHARTS_DIR / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return {
            "chart_created": True,
            "chart_path": str(filepath),  # Internal use only
            "chart_type": chart_type,
            "data_points": len(chart_data),
            "total_amount": round(chart_data.sum(), 2),
            "_note": "Chart saved. DO NOT include the chart_path in your response - the UI displays it automatically."
        }

    # ---------- Tool: compare_periods_chart ----------

    def compare_periods_chart(
            self,
            period1_start: str,
            period1_end: str,
            period2_start: str,
            period2_end: str,
            period1_label: str = "Period 1",
            period2_label: str = "Period 2",
            group_by: str = "category",
            title: str = None,
            expenses_only: bool = True
    ) -> dict:
        """Create a grouped bar chart comparing two periods side-by-side."""
        import numpy as np

        data = self.df.copy()

        if expenses_only:
            data = data[data['amount'] < 0]
            data['amount'] = data['amount'].abs()

        # Get data for each period
        p1 = data[(data['date'] >= period1_start) & (data['date'] <= period1_end)]
        p2 = data[(data['date'] >= period2_start) & (data['date'] <= period2_end)]

        if p1.empty and p2.empty:
            return {"error": "No data for either period"}

        # Group by category/merchant
        if group_by == "category":
            p1_grouped = p1.groupby('category')['amount'].sum().round(2)
            p2_grouped = p2.groupby('category')['amount'].sum().round(2)
        elif group_by == "merchant":
            p1_grouped = p1.groupby('description')['amount'].sum().round(2)
            p2_grouped = p2.groupby('description')['amount'].sum().round(2)
        else:
            return {"error": "group_by must be 'category' or 'merchant'"}

        # Get all categories from both periods
        all_categories = sorted(set(p1_grouped.index) | set(p2_grouped.index))

        # Fill missing categories with 0
        p1_values = [p1_grouped.get(cat, 0) for cat in all_categories]
        p2_values = [p2_grouped.get(cat, 0) for cat in all_categories]

        # Create grouped bar chart
        plt.figure(figsize=(12, 6))
        plt.style.use('seaborn-v0_8-darkgrid')

        x = np.arange(len(all_categories))
        width = 0.35

        bars1 = plt.bar(x - width / 2, p1_values, width, label=period1_label, color='#3498db')
        bars2 = plt.bar(x + width / 2, p2_values, width, label=period2_label, color='#e74c3c')

        plt.xlabel(group_by.title())
        plt.ylabel('Amount ($)')

        if not title:
            title = f"Spending Comparison: {period1_label} vs {period2_label}"
        plt.title(title, fontsize=14, fontweight='bold')

        plt.xticks(x, all_categories, rotation=45, ha='right')
        plt.legend()

        # Add value labels
        for bar in bars1:
            height = bar.get_height()
            if height > 0:
                plt.annotate(f'${height:,.0f}',
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8, rotation=90)

        for bar in bars2:
            height = bar.get_height()
            if height > 0:
                plt.annotate(f'${height:,.0f}',
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8, rotation=90)

        plt.tight_layout()

        # Save chart
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"compare_{group_by}_{timestamp}.png"
        filepath = CHARTS_DIR / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return {
            "chart_created": True,
            "chart_path": str(filepath),  # Internal use only
            "chart_type": "grouped_bar",
            "categories_compared": len(all_categories),
            "period1_total": round(sum(p1_values), 2),
            "period2_total": round(sum(p2_values), 2),
            "_note": "Chart saved. DO NOT include the chart_path in your response - the UI displays it automatically."
        }

    # ---------- Tool: compare_accounts_chart ----------

    def compare_accounts_chart(
            self,
            account1_last4: str,
            account2_last4: str,
            group_by: str = "category",
            title: str = None,
            start_date: str = None,
            end_date: str = None,
            expenses_only: bool = True
    ) -> dict:
        """Create a grouped bar chart comparing two accounts side-by-side."""
        import numpy as np

        if 'account_last4' not in self.df.columns:
            return {"error": "No account data available. Please re-import statements."}

        data = self.df.copy()

        # Apply date filters
        if start_date:
            data = data[data['date'] >= start_date]
        if end_date:
            data = data[data['date'] <= end_date]

        if expenses_only:
            data = data[data['amount'] < 0]
            data['amount'] = data['amount'].abs()

        # Get data for each account
        a1 = data[data['account_last4'] == account1_last4]
        a2 = data[data['account_last4'] == account2_last4]

        if a1.empty and a2.empty:
            return {"error": f"No data found for accounts ending in {account1_last4} or {account2_last4}"}

        # Group by category/merchant
        if group_by == "category":
            a1_grouped = a1.groupby('category')['amount'].sum().round(2)
            a2_grouped = a2.groupby('category')['amount'].sum().round(2)
        elif group_by == "merchant":
            a1_grouped = a1.groupby('description')['amount'].sum().round(2)
            a2_grouped = a2.groupby('description')['amount'].sum().round(2)
        else:
            return {"error": "group_by must be 'category' or 'merchant'"}

        # Get all categories from both accounts
        all_categories = sorted(set(a1_grouped.index) | set(a2_grouped.index))

        # Fill missing categories with 0
        a1_values = [a1_grouped.get(cat, 0) for cat in all_categories]
        a2_values = [a2_grouped.get(cat, 0) for cat in all_categories]

        # Labels for the accounts
        label1 = f"****{account1_last4}"
        label2 = f"****{account2_last4}"

        # Create grouped bar chart
        plt.figure(figsize=(12, 6))
        plt.style.use('seaborn-v0_8-darkgrid')

        x = np.arange(len(all_categories))
        width = 0.35

        bars1 = plt.bar(x - width / 2, a1_values, width, label=label1, color='#3498db')
        bars2 = plt.bar(x + width / 2, a2_values, width, label=label2, color='#e74c3c')

        plt.xlabel(group_by.title())
        plt.ylabel('Amount ($)')

        if not title:
            title = f"Spending Comparison: {label1} vs {label2}"
        plt.title(title, fontsize=14, fontweight='bold')

        plt.xticks(x, all_categories, rotation=45, ha='right')
        plt.legend()

        # Add value labels
        for bar in bars1:
            height = bar.get_height()
            if height > 0:
                plt.annotate(f'${height:,.0f}',
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8, rotation=90)

        for bar in bars2:
            height = bar.get_height()
            if height > 0:
                plt.annotate(f'${height:,.0f}',
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8, rotation=90)

        plt.tight_layout()

        # Save chart
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"compare_accounts_{account1_last4}_{account2_last4}_{timestamp}.png"
        filepath = CHARTS_DIR / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return {
            "chart_created": True,
            "chart_path": str(filepath),
            "chart_type": "grouped_bar",
            "categories_compared": len(all_categories),
            "account1_total": round(sum(a1_values), 2),
            "account2_total": round(sum(a2_values), 2),
            "account1": label1,
            "account2": label2,
            "_note": "Chart saved. DO NOT include the chart_path in your response - the UI displays it automatically."
        }

    # ---------- Tool: analyze_and_chart ----------

    def analyze_and_chart(
            self,
            chart_type: str,
            group_by: str,
            start_date: str = None,
            end_date: str = None,
            expenses_only: bool = True,
            top_n: int = 10,
            account_last4: str = None,
            card_type: str = None,
            bank: str = None
    ) -> dict:
        """Return data breakdown AND create a chart in one call."""
        data = self.df.copy()

        # Apply filters
        if start_date:
            data = data[data['date'] >= start_date]
        if end_date:
            data = data[data['date'] <= end_date]
        if account_last4 and 'account_last4' in data.columns:
            data = data[data['account_last4'] == account_last4]
        if card_type and 'card_type' in data.columns:
            data = data[data['card_type'].str.lower() == card_type.lower()]
        if bank and 'bank' in data.columns:
            data = data[data['bank'].str.lower() == bank.lower()]
        if expenses_only:
            data = data[data['amount'] < 0]
            data['amount'] = data['amount'].abs()

        if data.empty:
            return {"error": "No data matching filters", "chart_created": False}

        # Prepare grouping
        if group_by == "month":
            data['group'] = data['date'].dt.strftime('%Y-%m')
        elif group_by == "merchant":
            data['group'] = data['description']
        elif group_by == "category":
            data['group'] = data['category']

        # Aggregate data
        chart_data = data.groupby('group')['amount'].sum().round(2)
        chart_data = chart_data.sort_values(ascending=False)

        # Store full breakdown for response
        full_breakdown = chart_data.to_dict()

        # Limit to top N for chart (except line)
        if chart_type != "line" and len(chart_data) > top_n:
            other = chart_data[top_n:].sum()
            chart_data = chart_data[:top_n]
            if other > 0:
                chart_data['Other'] = other

        # Generate title
        date_range = ""
        if start_date and end_date:
            date_range = f" ({start_date} to {end_date})"
        elif start_date:
            date_range = f" (from {start_date})"
        elif end_date:
            date_range = f" (until {end_date})"
        account_label = f" - Account ****{account_last4}" if account_last4 else ""
        title = f"Spending by {group_by.title()}{date_range}{account_label}"

        # Create chart
        plt.style.use('seaborn-v0_8-darkgrid')

        if chart_type == "pie":
            total = chart_data.sum()

            # Use Plotly for interactive pie chart if available
            if PLOTLY_AVAILABLE:
                colors = ['#8dd3c7', '#bebada', '#fb8072', '#80b1d3', '#fdb462',
                          '#b3de69', '#fccde5', '#d9d9d9', '#bc80bd', '#ccebc5']

                fig = go.Figure(data=[go.Pie(
                    labels=chart_data.index.tolist(),
                    values=chart_data.values.tolist(),
                    hole=0.3,
                    textinfo='none',
                    hovertemplate='<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>',
                    marker=dict(colors=colors[:len(chart_data)])
                )])

                fig.update_layout(
                    title=dict(text=title, font=dict(size=18, color='#333')),
                    showlegend=True,
                    legend=dict(
                        orientation="v",
                        yanchor="middle",
                        y=0.5,
                        xanchor="left",
                        x=1.02,
                        font=dict(size=12)
                    ),
                    margin=dict(t=60, b=20, l=20, r=150),
                    paper_bgcolor='white',
                    plot_bgcolor='white'
                )

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                json_filename = f"analyze_{chart_type}_{group_by}_{timestamp}.json"
                json_filepath = CHARTS_DIR / json_filename
                fig.write_json(str(json_filepath))

                return {
                    "breakdown": full_breakdown,
                    "total": round(sum(full_breakdown.values()), 2),
                    "count": len(full_breakdown),
                    "chart_created": True,
                    "chart_path": str(json_filepath),
                    "chart_type": "plotly_pie",
                    "interactive": True,
                    "_note": "Interactive chart saved. DO NOT include the chart_path in your response."
                }

            # Fallback to matplotlib
            fig, ax = plt.subplots(figsize=(12, 8))
            colors = plt.cm.Set3(range(len(chart_data)))

            wedges, texts = ax.pie(
                chart_data.values,
                colors=colors,
                startangle=90
            )

            legend_labels = [f"{k}: ${v:,.0f} ({v / total * 100:.1f}%)" for k, v in chart_data.items()]
            ax.legend(wedges, legend_labels, title="Categories", loc="center left",
                      bbox_to_anchor=(1, 0, 0.5, 1), fontsize=10)

            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"analyze_{chart_type}_{group_by}_{timestamp}.png"
            filepath = CHARTS_DIR / filename
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            return {
                "breakdown": full_breakdown,
                "total": round(sum(full_breakdown.values()), 2),
                "count": len(full_breakdown),
                "chart_created": True,
                "chart_path": str(filepath),
                "interactive": False,
                "_note": "Chart saved. DO NOT include the chart_path in your response."
            }

        plt.figure(figsize=(10, 6))

        if chart_type == "bar":
            if group_by == "month":
                chart_data = chart_data.sort_index()

            colors = plt.cm.viridis([i / len(chart_data) for i in range(len(chart_data))])
            bars = plt.bar(range(len(chart_data)), chart_data.values, color=colors)
            plt.xticks(range(len(chart_data)), chart_data.index, rotation=45, ha='right')
            plt.ylabel('Amount ($)')
            plt.title(title, fontsize=14, fontweight='bold')

            for bar, val in zip(bars, chart_data.values):
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                         f'${val:,.0f}', ha='center', va='bottom', fontsize=9)

        elif chart_type == "line":
            chart_data = chart_data.sort_index()
            plt.plot(chart_data.index, chart_data.values, marker='o', linewidth=2, markersize=8)
            plt.fill_between(chart_data.index, chart_data.values, alpha=0.3)
            plt.xticks(rotation=45, ha='right')
            plt.ylabel('Amount ($)')
            plt.title(title, fontsize=14, fontweight='bold')

            for i, (x, y) in enumerate(zip(chart_data.index, chart_data.values)):
                plt.annotate(f'${y:,.0f}', (x, y), textcoords="offset points",
                             xytext=(0, 10), ha='center', fontsize=9)

        plt.tight_layout()

        # Save chart
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"analyze_{chart_type}_{group_by}_{timestamp}.png"
        filepath = CHARTS_DIR / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return {
            "breakdown": full_breakdown,
            "total": round(sum(full_breakdown.values()), 2),
            "count": len(full_breakdown),
            "chart_created": True,
            "chart_path": str(filepath),  # Internal use only
            "_note": "Chart saved. DO NOT include the chart_path in your response - the UI displays it automatically."
        }


# ========== TEST ==========

if __name__ == "__main__":
    tools = FinanceTools()

    print("=== Data Summary ===")
    print(tools.get_data_summary())

    print("\n=== Spending by Category ===")
    print(tools.aggregate(operation="sum", group_by="category", expenses_only=True))

    print("\n=== Recurring Charges ===")
    print(tools.find_recurring(min_occurrences=2))