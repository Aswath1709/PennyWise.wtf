# Agent/agent.py

"""
Finance Agent using Gemini (Conversational)

Maintains chat history for context-aware conversations.
"""

import json
import sys
import os
import platform
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
# Add Agent directory to path (for tools import)
sys.path.append(str(Path(__file__).parent))

import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

# Import tools - try both ways for compatibility
try:
    from Agent.tools import FinanceTools, get_gemini_tools
except ImportError:
    from tools import FinanceTools, get_gemini_tools


def open_file(filepath: str):
    """Open a file with the default application."""
    filepath = Path(filepath)
    if not filepath.exists():
        return

    try:
        if platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', filepath])
        elif platform.system() == 'Windows':  # Windows
            os.startfile(filepath)
        else:  # Linux
            subprocess.run(['xdg-open', filepath])
    except Exception as e:
        print(f"Could not open file: {e}")


# ========== SYSTEM PROMPT ==========

SYSTEM_PROMPT = """You are a personal finance advisor with access to the user's transaction data.

RULES:
1. ALWAYS use tools for any calculations - never guess numbers
2. If user doesn't specify a time period, use all available data
3. Call get_data_summary first if you need to understand what data exists
4. Mention the time period or data you analyzed in your response
5. Be concise and actionable
6. Format currency with $ and commas (e.g., $1,234.56)
7. Remember the conversation context

CRITICAL CHART RULES:
8. When user wants BOTH a list/breakdown AND a chart → use analyze_and_chart (ONE tool does both!)
   Examples: "list months and show graph", "show categories with a pie chart"

9. When user wants ONLY a chart (no text data) → use create_chart
   - Can filter by account_last4, card_type, bank
   - For MULTIPLE accounts, call create_chart MULTIPLE TIMES with different account_last4 values
   Examples: "pie chart for each account" → call create_chart twice with different account_last4

10. When comparing TWO specific periods with a chart → use compare_periods_chart

11. When comparing TWO specific accounts with a chart → use compare_accounts_chart
    Examples: "compare spending between account 1234 and 5678", "compare accounts by category"

12. When user wants ONLY text data (no chart) → use aggregate

13. For "pie chart for all accounts" or "separate charts for each account":
    - First call get_data_summary to see which accounts exist
    - Then call create_chart once per account with account_last4 filter

RESPONSE FORMATTING - EXTREMELY IMPORTANT:
- NEVER include file paths, chart paths, or any paths in your response
- NEVER mention "/home/", "/charts/", ".png", or any file locations
- NEVER use <chart path="..."> or similar tags
- The UI automatically displays charts - just say "Here is a pie chart showing..." WITHOUT any path
- If a tool returns a chart_path, DO NOT include it in your response text

GOOD RESPONSE: "Here is a pie chart showing your spending breakdown by category."
BAD RESPONSE: "Here is a pie chart <chart path='/home/user/charts/pie.png'>"

When user asks about spending, use expenses_only=true.
When user asks about income, use income_only=true."""


# ========== FINANCE AGENT CLASS ==========

class FinanceAgent:
    """Conversational finance agent with persistent chat history."""

    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)

        self.finance_tools = FinanceTools()
        self.gemini_tools = get_gemini_tools()

        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            tools=[self.gemini_tools],
            system_instruction=SYSTEM_PROMPT
        )

        # Start chat session - this persists across messages
        self.chat = self.model.start_chat()
        self.verbose = False
        self.last_chart_path = None  # Track last created chart (for single chart)
        self.chart_paths = []  # Track all charts created in a response

    def reset(self):
        """Start a new conversation (clear history)."""
        self.chat = self.model.start_chat()
        self.last_chart_path = None
        self.chart_paths = []
        print("Conversation reset.")

    def ask(self, user_query: str) -> str:
        """
        Send a message and get response.
        Remembers previous conversation context.
        """
        self.last_chart_path = None  # Reset chart path
        self.chart_paths = []  # Reset all chart paths
        response = self.chat.send_message(user_query)

        # Loop until no more function calls
        while True:
            function_calls = []

            try:
                # Collect ALL function calls in this response (parallel function calling)
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call.name:
                        function_calls.append(part.function_call)
            except (AttributeError, IndexError):
                return response.text

            if not function_calls:
                return response.text

            # Execute ALL function calls and collect responses
            function_responses = []

            for function_call in function_calls:
                tool_name = function_call.name
                tool_params = {k: v for k, v in function_call.args.items()}

                if self.verbose:
                    print(f"\n[Agent] Calling tool: {tool_name}")
                    print(f"[Agent] Params: {json.dumps(tool_params, indent=2, default=str)}")

                # Execute tool
                result = self.finance_tools.execute(tool_name, tool_params)

                # Track if chart was created
                if tool_name in ["create_chart", "compare_periods_chart", "compare_accounts_chart",
                                 "analyze_and_chart"] and result.get("chart_created"):
                    chart_path = result.get("chart_path")
                    self.last_chart_path = chart_path
                    self.chart_paths.append(chart_path)

                if self.verbose:
                    result_str = json.dumps(result, indent=2, default=str)
                    print(f"[Agent] Result: {result_str[:500]}...")

                # Add to function responses
                function_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": result}
                        )
                    )
                )

            # Send ALL function responses back at once
            response = self.chat.send_message(
                genai.protos.Content(parts=function_responses)
            )


# ========== CHAT INTERFACE ==========

def chat():
    """Interactive chat with the finance agent."""
    print("=" * 50)
    print("FINANCE AGENT (Gemini)")
    print("=" * 50)
    print("Ask me anything about your transactions!")
    print("Commands:")
    print("  'quit'    - Exit")
    print("  'verbose' - Toggle debug mode")
    print("  'reset'   - Start new conversation")
    print("=" * 50)

    agent = FinanceAgent()

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == 'quit':
            print("Goodbye!")
            break

        if user_input.lower() == 'verbose':
            agent.verbose = not agent.verbose
            print(f"Verbose mode: {'ON' if agent.verbose else 'OFF'}")
            continue

        if user_input.lower() == 'reset':
            agent.reset()
            continue

        print("\nAgent: ", end="", flush=True)
        try:
            response = agent.ask(user_input)
            print(response)

            # Auto-open chart if one was created
            if agent.last_chart_path:
                print(f"\n📊 Opening chart: {agent.last_chart_path}")
                open_file(agent.last_chart_path)
            else:
                # Warn if agent mentioned chart but didn't create one
                chart_words = ['chart', 'graph', 'visual', 'plot', 'here is the']
                if any(word in response.lower() for word in chart_words) and 'pie' not in response.lower()[:50]:
                    if 'no data' not in response.lower() and 'cannot' not in response.lower():
                        print("\n⚠️  Note: No chart was actually generated.")

        except Exception as e:
            import traceback
            print(f"Error: {e}")
            print("\n--- Full Traceback ---")
            traceback.print_exc()
            print("--- End Traceback ---")


# ========== MAIN ==========

if __name__ == "__main__":
    chat()