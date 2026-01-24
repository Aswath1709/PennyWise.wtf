# DataProcessing/parser.py

"""
Chase Statement Parser

Supports:
- Chase Checking/Debit statements
- Chase Credit Card statements (Sapphire, Freedom, etc.)
"""

import re
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime


def parse_single_statement(pdf_path: str | Path, statement_type: str = "credit") -> pd.DataFrame:
    """
    Parse a Chase statement PDF.

    Args:
        pdf_path: Path to PDF file
        statement_type: "credit" or "debit"

    Returns:
        DataFrame with columns: date, description, amount
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if statement_type == "credit":
        return parse_credit(pdf_path)
    else:
        return parse_debit(pdf_path)


def parse_credit(pdf_path: str | Path) -> pd.DataFrame:
    """Parse Chase credit card statement."""

    # Extract text from all pages
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # Get statement year/month from "Statement Date: MM/DD/YY"
    match = re.search(r'Statement\s*Date[:\s]+(\d{1,2})/(\d{1,2})/(\d{2,4})', full_text, re.IGNORECASE)
    if match:
        stmt_month, stmt_year = int(match.group(1)), int(match.group(3))
        if stmt_year < 100:
            stmt_year += 2000
    else:
        stmt_month, stmt_year = datetime.now().month, datetime.now().year

    # Parse transactions: MM/DD DESCRIPTION AMOUNT
    transactions = []
    pattern = r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$'

    skip = ['TOTAL FEES', 'TOTAL INTEREST', 'BALANCE SUBJECT', 'PAGE', 'STATEMENT DATE', 'BILLING PERIOD']
    credits = ['PAYMENT', 'RETURN', 'REFUND', 'CREDIT', 'REVERSAL', 'CASHBACK']

    for line in full_text.split('\n'):
        line = line.strip()
        match = re.match(pattern, line)

        if not match:
            continue

        date_str, desc, amt_str = match.groups()

        if any(kw in desc.upper() for kw in skip):
            continue

        month, day = map(int, date_str.split('/'))
        year = stmt_year - 1 if month > stmt_month else stmt_year

        try:
            date = datetime(year, month, day)
        except ValueError:
            continue

        amount = float(amt_str.replace(',', ''))
        is_credit = any(kw in desc.upper() for kw in credits)
        amount = abs(amount) if is_credit else -abs(amount)

        transactions.append({'Date': date, 'Description': desc, 'Amount': amount})

    df = pd.DataFrame(transactions)
    if not df.empty:
        df = df.sort_values('Date').reset_index(drop=True)
    return df


def parse_debit(pdf_path: str | Path) -> pd.DataFrame:
    """Parse Chase checking/debit statement."""

    # Extract text from all pages
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # Get statement date
    match = re.search(r'through\s+(\d{1,2})/(\d{1,2})/(\d{2,4})', full_text, re.IGNORECASE)
    if not match:
        match = re.search(r'Statement\s*Date[:\s]+(\d{1,2})/(\d{1,2})/(\d{2,4})', full_text, re.IGNORECASE)

    if match:
        stmt_month, stmt_year = int(match.group(1)), int(match.group(3))
        if stmt_year < 100:
            stmt_year += 2000
    else:
        stmt_month, stmt_year = datetime.now().month, datetime.now().year

    transactions = []

    # Patterns for checking statements
    patterns = [
        r'^(\d{2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*$',  # With balance
        r'^(\d{2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s*$',  # Without balance
    ]

    skip = ['BEGINNING BALANCE', 'ENDING BALANCE', 'TOTAL', 'DATE DESCRIPTION']

    for line in full_text.split('\n'):
        line = line.strip()

        if any(kw in line.upper() for kw in skip):
            continue

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                date_str, desc, amt_str = match.groups()

                month, day = map(int, date_str.split('/'))
                year = stmt_year - 1 if month > stmt_month else stmt_year

                try:
                    date = datetime(year, month, day)
                except ValueError:
                    continue

                amount = float(amt_str.replace(',', ''))

                transactions.append({'Date': date, 'Description': desc, 'Amount': amount})
                break

    df = pd.DataFrame(transactions)
    if not df.empty:
        df = df.sort_values('Date').reset_index(drop=True)
    return df


# ========== TEST ==========

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        stmt_type = sys.argv[2] if len(sys.argv) > 2 else "credit"

        print(f"Parsing: {pdf_path} (type: {stmt_type})")
        print("-" * 60)

        df = parse_single_statement(pdf_path, stmt_type)

        if df.empty:
            print("No transactions found!")
        else:
            print(f"Found {len(df)} transactions:\n")
            print(df.to_string(index=False))
            print(f"\nTotal: ${df['Amount'].sum():,.2f}")
    else:
        print("Usage: python parser.py <pdf_path> [credit|debit]")