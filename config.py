from pathlib import Path
from dotenv import load_dotenv
import os
# Load secrets from the .env file
load_dotenv()
# ========== PATHS ==========

# Project root directory
PROJECT_DIR = Path(__file__).parent

# Data directory (in project folder)
DATA_DIR = PROJECT_DIR / "Database"
DATA_DIR.mkdir(exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "finance.db"

# Category cache
CACHE_PATH = DATA_DIR / "category_cache.json"
# Model
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
#jajaja

# Categories
CATEGORIES = [
    "groceries", "dining", "transport", "subscriptions",
    "utilities", "shopping", "entertainment", "health",
    "rent", "income", "fees","transfer", "other"
]

# Prompt for categorization
CATEGORIZATION_PROMPT = """Categorize each merchant into exactly one category.

IMPORTANT RULES:
1. Focus on the CORE BUSINESS NAME - ignore dates, card numbers, transaction IDs, locations
2. Be CONSISTENT - same store must always get the same category
3. "Convenience" stores, gas stations with shops = groceries
4. Look at the business type, not the extra text

Examples:
- "Card Purchase 11/22 College Convenience Boston MA Card 2812" → groceries (it's a convenience store)
- "Card Purchase 11/28 College Convenience Boston MA Card 2812" → groceries (same store, same category)
- "UBER TRIP 12345 HELP.UBER.COM" → transport
- "UBER EATS 98765 HELP.UBER.COM" → dining

Categories: {categories}

Merchants:
{merchants}

Respond with ONLY a JSON array of categories in the same order:
["category1", "category2", ...]"""