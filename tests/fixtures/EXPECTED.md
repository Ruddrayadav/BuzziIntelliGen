# Expected results

**1_messy_sales.csv**
8 good rows, 5 bad (missing date, invalid revenue, negative qty, missing product, bad date). Revenue of good rows = 2210. Nothing may crash; each bad row needs a reason. Undo must remove all 8.

**2_messy_expenses.csv**
5 clear good rows = 51900. Bad: missing date, invalid amount, negative amount. The row with a missing category is a judgement call: it may be saved as 'Uncategorised' (then total adds 900) or rejected. Either is OK if the reason is shown. Never crash.

**3_category_variants.csv**
After the category fix: Raw Material = 3,800 as ONE category; Rent = 20,000 as ONE category. Before the fix you will see 4+ separate rows (that is the bug).

**4_new_category_***
Upload both. Compare Feb vs Jan. Utilities +20%. Marketing must say 'new' (NOT +100%). Total expenses Jan 23,000, Feb 28,600. Revenue Jan 2,500, Feb 2,600.

**5_cashbook.csv**
Should be detected as a cash book. Income 4,100 (3 rows), Expenses 46,200 (3 rows).

**6_shop_sales.csv**
Different column names, dd/mm/yyyy, ₹ and commas. Expect 7 rows, revenue 2715. Top product by revenue: Rice 5kg = 1,650. If bill numbers are used for orders: 6 orders. Dates must read as 5-7 March, not May-July.

**6_shop_expenses.csv**
Expenses 15,450. Net profit with 6_shop_sales = 2,715 - 15,450 = -12,735.

**7_formula_names.csv**
Revenue 400. Export CSV from the app and open in Excel: no cell may run as a formula (should start with an apostrophe or be neutralised).

**8_***
empty / header only / fake pdf / one column: clear plain message, nothing saved, no stack trace. semicolon_latin1: should read 2 rows, revenue 450, name 'Café au lait' not garbled (nice-to-have).

**8_exact_duplicate_rows.csv**
3 identical rows: all 3 must be KEPT (three real Latte sales), revenue 450. This is the data-loss bug you fixed earlier.

**9_sales.xlsx**
Excel file, 3 rows, revenue 650.
