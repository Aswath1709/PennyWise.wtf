# DataProcessing/preprocess.py

"""
Transaction Processing: Sanitization and Categorization

Sanitize: Remove sensitive info (card numbers, phone, transaction IDs, etc.)
Categorize: Use Gemini LLM to categorize merchants
"""

import re
import json
import sqlite3
import pandas as pd
import google.generativeai as genai
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import GEMINI_API_KEY, GEMINI_MODEL, CATEGORIES, CATEGORIZATION_PROMPT, DB_PATH, DATA_DIR

# ========== SANITIZATION PATTERNS ==========

SANITIZE_PATTERNS = [
    # Card numbers (full or partial)
    (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD]'),
    (r'\b(?:ending\s*(?:in)?|last\s*4|x{4,})\s*\d{4}\b', '[CARD]'),
    (r'\bCard\s+\d{4}\b', '[CARD]', re.IGNORECASE),

    # Account numbers (6+ digits)
    (r'\b(?:acct?|account)\.?\s*#?\s*\d{6,}\b', '[ACCOUNT]', re.IGNORECASE),

    # Transaction/Reference/Confirmation numbers
    (r'\b(?:trans(?:action)?|ref(?:erence)?|conf(?:irmation)?|trace|auth(?:orization)?)\s*#?\s*:?\s*[A-Z0-9]{6,}\b',
     '[REF]', re.IGNORECASE),

    # Check numbers
    (r'\b(?:check|chk|cheque)\s*#?\s*:?\s*\d{3,}\b', '[CHECK]', re.IGNORECASE),

    # Phone numbers
    (r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),

    # Email addresses
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),

    # SSN
    (r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b', '[SSN]'),

    # Generic long numbers (8+ digits)
    (r'\b\d{8,}\b', '[ID]'),

    # Alphanumeric reference codes
    (r'\b[A-Z]{2,}[0-9]{6,}\b', '[REF]'),
    (r'\b[0-9]{3,}[A-Z]{2,}[0-9]{2,}\b', '[REF]'),
]


# ========== SANITIZATION ==========

def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """Remove sensitive information from transactions."""
    df = df.copy()
    df['Description'] = df['Description'].apply(_sanitize_description)

    if 'Balance' in df.columns:
        df = df.drop(columns=['Balance'])

    return df


def _sanitize_description(text: str) -> str:
    """Apply all sanitization patterns to a description."""
    if not isinstance(text, str):
        return text

    result = text

    for pattern_tuple in SANITIZE_PATTERNS:
        if len(pattern_tuple) == 3:
            pattern, replacement, flags = pattern_tuple
            result = re.sub(pattern, replacement, result, flags=flags)
        else:
            pattern, replacement = pattern_tuple
            result = re.sub(pattern, replacement, result)

    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'(\[\w+\])(?:\s*\1)+', r'\1', result)

    return result


def preview_sanitization(df: pd.DataFrame, n: int = 10) -> None:
    """Preview sanitization changes without modifying data."""
    sample = df.sample(min(n, len(df)))

    print("=" * 60)
    print("SANITIZATION PREVIEW")
    print("=" * 60)

    for _, row in sample.iterrows():
        original = row['Description']
        sanitized = _sanitize_description(original)

        if original != sanitized:
            print(f"\nBEFORE: {original}")
            print(f"AFTER:  {sanitized}")
        else:
            print(f"\nNO CHANGE: {original}")

    print("=" * 60)


# ========== CATEGORIZATION (Gemini) ==========

def categorize(df: pd.DataFrame) -> pd.DataFrame:
    """Categorize transactions using Gemini LLM."""
    df = df.copy()

    unique_merchants = df['Description'].unique().tolist()
    print(f"Found {len(unique_merchants)} unique merchants")

    cache = _load_category_cache()
    cached_count = sum(1 for m in unique_merchants if m in cache)
    print(f"Already categorized: {cached_count}")

    uncategorized = [m for m in unique_merchants if m not in cache]

    if uncategorized:
        print(f"Categorizing {len(uncategorized)} new merchants via Gemini...")
        new_categories = _categorize_with_gemini(uncategorized)

        for merchant, category in zip(uncategorized, new_categories):
            cache[merchant] = category

        _save_category_cache(cache)
        print("Cache updated")

    df['Category'] = df['Description'].map(cache).fillna('other')

    return df


def _categorize_with_gemini(merchants: list[str], batch_size: int = 50) -> list[str]:
    """Categorize merchants using Gemini API."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    all_categories = []

    for i in range(0, len(merchants), batch_size):
        batch = merchants[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(merchants) + batch_size - 1) // batch_size

        print(f"  Processing batch {batch_num}/{total_batches}...")

        merchants_text = "\n".join(f"{j + 1}. {m}" for j, m in enumerate(batch))

        prompt = CATEGORIZATION_PROMPT.format(
            categories=", ".join(CATEGORIES),
            merchants=merchants_text
        )

        response = model.generate_content(prompt)

        categories = _parse_llm_response(response.text, len(batch))
        all_categories.extend(categories)

    return all_categories


def _parse_llm_response(response_text: str, expected_count: int) -> list[str]:
    """Parse JSON array from LLM response."""
    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)

        categories = json.loads(text)

        if len(categories) != expected_count:
            print(f"  Warning: Expected {expected_count} categories, got {len(categories)}")
            if len(categories) < expected_count:
                categories.extend(['other'] * (expected_count - len(categories)))
            else:
                categories = categories[:expected_count]

        categories = [c if c in CATEGORIES else 'other' for c in categories]
        return categories

    except json.JSONDecodeError as e:
        print(f"  Error parsing LLM response: {e}")
        return ['other'] * expected_count


# ========== CATEGORY CACHE ==========

def _load_category_cache() -> dict[str, str]:
    """Load cached merchant → category mappings from database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS merchant_categories
                 (
                     merchant
                     TEXT
                     PRIMARY
                     KEY,
                     category
                     TEXT
                 )
                 """)
    conn.commit()

    cursor = conn.execute("SELECT merchant, category FROM merchant_categories")
    cache = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    return cache


def _save_category_cache(cache: dict[str, str]) -> None:
    conn = sqlite3.connect(DB_PATH)

    conn.executemany(
        "INSERT OR REPLACE INTO merchant_categories (merchant, category) VALUES (?, ?)",
        cache.items()
    )

    conn.commit()
    conn.close()


def clear_category_cache() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM merchant_categories")
    conn.commit()
    conn.close()
    print("Category cache cleared")


def view_category_cache() -> pd.DataFrame:
    cache = _load_category_cache()
    return pd.DataFrame(
        list(cache.items()),
        columns=['Merchant', 'Category']
    ).sort_values('Category')



def process_transactions(df: pd.DataFrame, preview: bool = False) -> pd.DataFrame:
    """Full pipeline: sanitize → categorize."""
    print("=" * 40)
    print("PROCESSING TRANSACTIONS")
    print("=" * 40)

    print("\n[1/2] Sanitizing...")
    if preview:
        preview_sanitization(df)
    df = sanitize(df)
    print(f"  Sanitized {len(df)} transactions")

    print("\n[2/2] Categorizing...")
    df = categorize(df)
    print(f"  Categorized {len(df)} transactions")

    print("\n" + "=" * 40)
    print("CATEGORY SUMMARY")
    print("=" * 40)
    print(df['Category'].value_counts().to_string())

    return df