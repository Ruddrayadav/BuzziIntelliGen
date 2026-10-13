"""Temporary file-type detector used only by the upload preview route."""


def detect_file_type(columns: list[str]) -> str:
    """Choose the most likely file type from column names only.

    TODO: Replace this UI-assist rule with a backend-owned classifier in the
    backend phase. The business owner can always override the result.
    """
    names = " ".join(str(column).lower() for column in columns)
    sales_words = ("sale", "revenue", "product", "item", "order", "quantity", "price", "qty")
    expense_words = ("expense", "cost", "vendor", "payment", "paid", "bill", "debit", "rent")
    sales_score = sum(word in names for word in sales_words)
    expense_score = sum(word in names for word in expense_words)
    return "expenses" if expense_score > sales_score else "sales"
