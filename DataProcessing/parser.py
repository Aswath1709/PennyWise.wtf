# DataProcessing/parser.py

"""
Chase Statement Parser

Supports:
- Chase Checking/Debit statements
- Chase Credit Card statements (Sapphire, Freedom, etc.)

Returns: (DataFrame, account_last4)
"""

import re
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime


def parse_single_statement(pdf_path: str | Path, statement_type: str = "credit") -> tuple[pd.DataFrame, str]:
    """
    Parse a Chase statement PDF.

    Args:
        pdf_path: Path to PDF file
        statement_type: "credit" or "debit"

    Returns:
        Tuple of (DataFrame with columns: Date, Description, Amount, account_last4 string)
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if statement_type == "credit":
        return parse_credit(pdf_path)
    else:
        return parse_debit(pdf_path)


def extract_account_last4(text: str) -> str:
    """Extract last 4 digits of account number from statement text."""

    # Common patterns for account numbers
    patterns = [
        # "Account Number: XXXX XXXX XXXX 1234" or "...ending in 1234"
        r'(?:account|acct|card)[\s#:]*(?:number)?[\s:]*[\dxX*\s-]*(\d{4})\b',
        # "XXXXXXXXXXXX1234"
        r'[xX*]{8,}(\d{4})\b',
        # "Account ending in 1234"
        r'ending\s+in\s+(\d{4})',
        # "Last 4: 1234"
        r'last\s*4[\s:]+(\d{4})',
        # Just look for pattern like "...1234" after account-like text
        r'account[^\d]*(\d{4})\s',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def parse_credit(pdf_path: str | Path) -> tuple[pd.DataFrame, str]:
    """Parse Chase credit card statement. Returns (DataFrame, account_last4)."""

    # Extract text from all pages
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # Extract account last 4
    account_last4 = extract_account_last4(full_text)

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
    return df, account_last4


def parse_debit(pdf_path: str | Path) -> tuple[pd.DataFrame, str]:
    """Parse Chase checking/debit statement. Returns (DataFrame, account_last4)."""

    # Extract text from all pages
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # Extract account last 4
    account_last4 = extract_account_last4(full_text)

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
    return df, account_last4


# ========== TEST ==========

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        stmt_type = sys.argv[2] if len(sys.argv) > 2 else "credit"

        print(f"Parsing: {pdf_path} (type: {stmt_type})")
        print("-" * 60)

        df, account_last4 = parse_single_statement(pdf_path, stmt_type)

        print(f"Account ending in: {account_last4 or 'Not found'}")
        print()

        if df.empty:
            print("No transactions found!")
        else:
            print(f"Found {len(df)} transactions:\n")
            print(df.to_string(index=False))
            print(f"\nTotal: ${df['Amount'].sum():,.2f}")
    else:
        print("Usage: python parser.py <pdf_path> [credit|debit]")