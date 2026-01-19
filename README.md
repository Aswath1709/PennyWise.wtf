# 💰 PennyWise.wtf

> *"Where The Finances?"* — Your AI-powered personal finance tracker that helps you understand where your money actually goes.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-red.svg)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 🤔 What's with the name?

**PennyWise** = Being smart with every penny 🪙

**.wtf** = *"Watch The Finances"* (or *"Where's The Finance?"* when you're wondering where all your money went 😅)

It's a finance tracker that doesn't take itself too seriously, but takes your money very seriously.

---

## ✨ Features

### 📊 Smart Dashboard
- Real-time overview of income, expenses, and net balance
- Interactive charts (pie, line, bar) powered by Plotly
- Filter by time period (30 days, 90 days, 6 months, year, all time)
- Top merchants and category breakdowns

### 💬 AI Chat Assistant
- Natural language queries: *"How much did I spend on coffee last month?"*
- Automatic chart generation: *"Show me a pie chart of my spending"*
- Anomaly detection: *"Find any unusual transactions"*
- Subscription tracking: *"What are my recurring charges?"*
- Powered by Google Gemini AI

### 📄 PDF Statement Import
- Upload Chase bank statements (PDF)
- Bulk import multiple statements at once
- Automatic duplicate detection
- Smart transaction parsing with regex

### 🏷️ AI-Powered Categorization
- Automatic merchant categorization using Gemini
- 13 categories: groceries, dining, transport, subscriptions, utilities, shopping, entertainment, health, rent, income, transfer, fees, other
- Cached categories for consistency and speed

### 🔒 Privacy First
- All data stored locally in SQLite
- Sensitive data (card numbers, account numbers) automatically sanitized
- No data sent to external servers (except Gemini API for categorization)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         PennyWise.wtf                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────────┐     │
│   │   PDF    │───►│    Parser    │───►│   Preprocessor   │     │
│   │ Uploads  │    │ (pdfplumber) │    │ (Sanitize + AI)  │     │
│   └──────────┘    └──────────────┘    └────────┬─────────┘     │
│                                                 │               │
│                                                 ▼               │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────────┐     │
│   │ Streamlit│◄───│   Finance    │◄───│     SQLite       │     │
│   │    UI    │    │    Agent     │    │    Database      │     │
│   └──────────┘    │  (Gemini)    │    └──────────────────┘     │
│                   └──────────────┘                              │
│                          │                                      │
│                          ▼                                      │
│                   ┌──────────────┐                              │
│                   │  10 Tools    │                              │
│                   │ (Analytics)  │                              │
│                   └──────────────┘                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Streamlit |
| Charts | Plotly (dashboard), Matplotlib (agent) |
| AI/LLM | Google Gemini 1.5 Flash |
| Database | SQLite |
| PDF Parsing | pdfplumber |
| Data Processing | Pandas, NumPy |

---

## 📁 Project Structure

```
PennyWise.wtf/
├── Agent/
│   ├── agent.py          # Conversational AI agent
│   └── tools.py          # 10 finance analysis tools
├── DataProcessing/
│   ├── parser.py         # PDF text extraction
│   ├── preprocess.py     # Sanitization + AI categorization
│   └── database.py       # SQLite operations
├── data/                  # Database & cache (gitignored)
│   ├── finance.db
│   └── category_cache.json
├── charts/                # Generated chart images
├── app.py                 # Streamlit web UI
├── config.py              # Configuration & API keys
├── requirements.txt       # Dependencies
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/PennyWise.wtf.git
cd PennyWise.wtf

# Install dependencies (using uv)
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

### Configuration

1. Set your Gemini API key:

```bash
# Option 1: Environment variable (recommended)
export GEMINI_API_KEY="your-api-key-here"

# Option 2: Edit config.py directly
```

2. Edit `config.py` if needed:

```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your-api-key-here")
GEMINI_MODEL = "gemini-1.5-flash"
```

### Run

```bash
# Web UI (recommended)
streamlit run app.py

# Terminal chat mode
python Agent/agent.py
```

Open `http://localhost:8501` in your browser.

---

## 📖 Usage Guide

### Importing Statements

1. Go to **📤 Upload** page
2. Drag & drop your Chase PDF statement(s)
3. Click **Import All Statements**
4. Wait for processing (parsing → sanitizing → categorizing → saving)

### Chatting with Your Data

Go to **💬 Chat** and ask questions like:

| Query | What it does |
|-------|--------------|
| "How much did I spend last month?" | Total expenses |
| "Show spending by category" | Breakdown with percentages |
| "Draw a pie chart of my expenses" | Visual chart |
| "Compare October vs November" | Period comparison |
| "What are my subscriptions?" | Recurring charges |
| "Find unusual transactions" | Anomaly detection |
| "How much at Starbucks this year?" | Merchant-specific query |

### Dashboard

The **📊 Dashboard** shows:
- Income vs Expenses vs Net
- Spending by category (pie chart)
- Monthly trend (line chart)
- Top 10 merchants (bar chart)

---

## 🔧 Agent Tools

The AI agent has access to 10 specialized tools:

| Tool | Description |
|------|-------------|
| `get_data_summary` | Overview of all available data |
| `query_transactions` | Search and filter transactions |
| `aggregate` | Sum, avg, count, min, max operations |
| `compare_periods` | Compare two time periods |
| `find_recurring` | Detect subscription charges |
| `detect_anomalies` | Find unusual transactions |
| `run_sql` | Custom SQL queries |
| `create_chart` | Generate pie/bar/line charts |
| `compare_periods_chart` | Visual period comparison |
| `analyze_and_chart` | Data breakdown + chart in one |

---

## 🏦 Supported Banks

| Bank | Status |
|------|--------|
| Chase | ✅ Supported |
| Bank of America | 🔜 Coming soon |
| Wells Fargo | 🔜 Coming soon |
| American Express | 🔜 Coming soon |

Want to add support for your bank? PRs welcome!

---

## 🔐 Privacy & Security

- **Local Storage**: All data stored in local SQLite database
- **No Cloud Sync**: Your financial data never leaves your machine
- **Sanitization**: Card numbers, account numbers, and auth codes are automatically removed
- **Gemini API**: Only merchant names are sent for categorization (no amounts, dates, or personal info)

---

## 🤝 Contributing

Contributions are welcome! Here's how:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Ideas for Contribution

- [ ] Add support for more banks (Bank of America, Wells Fargo, etc.)
- [ ] Budget tracking and alerts
- [ ] Export reports to PDF
- [ ] Mobile-responsive UI improvements
- [ ] Multi-currency support
- [ ] CSV import option

---

## 📝 License

MIT License - feel free to use this for personal or commercial projects.

---

## 🙏 Acknowledgments

- [Streamlit](https://streamlit.io/) for the amazing UI framework
- [Google Gemini](https://deepmind.google/technologies/gemini/) for AI capabilities
- [pdfplumber](https://github.com/jsvine/pdfplumber) for PDF parsing

---

<p align="center">
  <b>Made with 💸 by someone who also wonders where all their money goes</b>
</p>

<p align="center">
  <i>Remember: A penny saved is a penny earned. PennyWise helps you find where those pennies went.</i>
</p>
