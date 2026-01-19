# processing/parser.py

"""
Chase PDF Statement Parser

Extracts transactions from Chase bank PDF statements.
"""

import os
import re
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime

# ========== CONSTANTS ==========

MONTH_MAP = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4,
    'May': 5, 'June': 6, 'July': 7, 'August': 8,
    'September': 9, 'October': 10, 'November': 11, 'December': 12
}

# Regex patterns
DATE_RANGE_PATTERN = re.compile(
    r"([A-Za-z]+ \d{1,2}, \d{4}) through ([A-Za-z]+ \d{1,2}, \d{4})"
)
TRANSACTION_SECTION_PATTERN = re.compile(
    r"\*start\*transactiondetail(.*?)\*end\*transactiondetail",
    re.DOTALL
)
TRANSACTION_LINE_PATTERN = re.compile(
    r"^(\d{2}/\d{2})\s+(.*?)\s+(-?\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s+(-?\d{1,3}(?:,\d{3})*(?:\.\d{2}))$"
)
DATE_PARTS_PATTERN = re.compile(r"([A-Za-z]+) \d{1,2}, (\d{4})")


# ========== MAIN FUNCTIONS ==========

def parse_chase_statements(pdf_folder: str | Path) -> pd.DataFrame:
    """
    Parse all Chase PDF statements from a folder.

    Args:
        pdf_folder: Path to folder containing Chase PDF statements.
                    Files should be named like "Apr2024.pdf"

    Returns:
        DataFrame with columns: Date, Description, Amount, Balance

    Raises:
        ValueError: If no PDF files found
        FileNotFoundError: If folder doesn't exist
    """
    pdf_folder = Path(pdf_folder)

    if not pdf_folder.exists():
        raise FileNotFoundError(f"Folder not found: {pdf_folder}")

    # Get and sort PDF files
    pdf_files = _get_sorted_pdfs(pdf_folder)

    if not pdf_files:
        raise ValueError(f"No PDF files found in {pdf_folder}")

    print(f"Found {len(pdf_files)} PDFs: {[f.name for f in pdf_files]}")

    # Extract text from all PDFs
    text = _extract_text_from_pdfs(pdf_files)
    print(f"Extracted {len(text):,} characters")

    # Parse transactions
    transactions = _parse_transactions(text)
    print(f"Parsed {len(transactions)} transactions")

    # Convert to DataFrame
    df = pd.DataFrame(transactions)

    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)

    return df


def parse_single_statement(pdf_path: str | Path) -> pd.DataFrame:
    """
    Parse a single Chase PDF statement.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        DataFrame with columns: Date, Description, Amount, Balance
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    text = _extract_text_from_pdf(pdf_path)
    transactions = _parse_transactions(text)

    df = pd.DataFrame(transactions)

    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)

    return df


# ========== HELPER FUNCTIONS ==========

def _get_sorted_pdfs(folder: Path) -> list[Path]:
    """Get PDF files sorted chronologically by filename."""
    pdf_files = [f for f in folder.iterdir() if f.suffix.lower() == '.pdf']
    pdf_files.sort(key=_parse_date_from_filename)
    return pdf_files


def _parse_date_from_filename(filepath: Path) -> datetime:
    """
    Extract date from filename like 'Apr2024.pdf'.
    Returns datetime.min if parsing fails.
    """
    name = filepath.stem  # filename without extension
    try:
        return datetime.strptime(name, "%b%Y")
    except ValueError:
        return datetime.min


def _extract_text_from_pdfs(pdf_files: list[Path]) -> str:
    """Extract and concatenate text from multiple PDFs."""
    text_parts = []

    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")
        text_parts.append(_extract_text_from_pdf(pdf_path))

    return "\n".join(text_parts)


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a single PDF."""
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n".join(text_parts)


def _parse_transactions(text: str) -> list[dict]:
    """
    Parse transaction data from extracted PDF text.

    Returns list of dicts with Date, Description, Amount, Balance.
    """
    # Find all date ranges and their positions
    date_ranges = [
        (m.start(), m.group(1), m.group(2))
        for m in DATE_RANGE_PATTERN.finditer(text)
    ]

    # Find all transaction sections
    transaction_sections = [
        (m.start(), m.group(1))
        for m in TRANSACTION_SECTION_PATTERN.finditer(text)
    ]

    transactions = []

    for section_pos, section_text in transaction_sections:
        # Find the date range for this section
        start_date_str, end_date_str = _find_date_range_for_position(
            section_pos, date_ranges
        )

        if not start_date_str or not end_date_str:
            continue

        # Parse year info
        year_info = _extract_year_info(start_date_str, end_date_str)
        if not year_info:
            continue

        # Parse each line in section
        section_transactions = _parse_section_lines(section_text, year_info)
        transactions.extend(section_transactions)

    return transactions


def _find_date_range_for_position(
        pos: int,
        date_ranges: list[tuple]
) -> tuple[str | None, str | None]:
    """Find the nearest preceding date range for a position."""
    for i in range(len(date_ranges) - 1, -1, -1):
        if date_ranges[i][0] <= pos:
            return date_ranges[i][1], date_ranges[i][2]
    return None, None


def _extract_year_info(start_date_str: str, end_date_str: str) -> dict | None:
    """Extract year information from date range strings."""
    start_match = DATE_PARTS_PATTERN.match(start_date_str)
    end_match = DATE_PARTS_PATTERN.match(end_date_str)

    if not start_match or not end_match:
        return None

    start_month_name, start_year = start_match.groups()
    _, end_year = end_match.groups()

    return {
        'start_year': int(start_year),
        'end_year': int(end_year),
        'start_month': MONTH_MAP[start_month_name]
    }


def _parse_section_lines(section_text: str, year_info: dict) -> list[dict]:
    """Parse individual transaction lines from a section."""
    transactions = []

    for line in section_text.strip().split("\n"):
        line = line.strip()

        # Skip non-transaction lines
        if not re.match(r"^\d{2}/\d{2}", line):
            continue

        match = TRANSACTION_LINE_PATTERN.match(line)
        if not match:
            continue

        transaction = _parse_transaction_line(match, year_info)
        if transaction:
            transactions.append(transaction)

    return transactions


def _parse_transaction_line(match: re.Match, year_info: dict) -> dict | None:
    """Parse a single transaction line."""
    date_mmdd, description, amount, balance = match.groups()
    month, day = map(int, date_mmdd.split("/"))

    # Determine year (handle year transitions in billing cycles)
    if year_info['start_year'] == year_info['end_year']:
        year = year_info['start_year']
    else:
        year = (
            year_info['start_year']
            if month >= year_info['start_month']
            else year_info['end_year']
        )

    try:
        return {
            "Date": datetime(year, month, day),
            "Description": description.strip(),
            "Amount": float(amount.replace(',', '')),
            "Balance": float(balance.replace(',', ''))
        }
    except ValueError as e:
        print(f"Invalid date {month}/{day}/{year}: {e}")
        return None


# ========== CLI ==========

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <pdf_folder>")
        sys.exit(1)

    folder = sys.argv[1]
    df = parse_chase_statements(folder)
    print(f"\n{df}")
    print(f"\nTotal transactions: {len(df)}")
    print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")