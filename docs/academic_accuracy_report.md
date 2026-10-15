# BizIntel Ground-Truth Accuracy Benchmark Report

## 1. Executive Summary & Methodology
This empirical evaluation measures the accuracy of the BizIntel Decision Support System on a standardized suite of 25 ground-truth small business intelligence queries.

- **Evaluation Principle**: Adheres to *Principle 1 & 2* (LLM never performs arithmetic; all calculations originate from deterministic Python/SQL services).
- **Total Questions Evaluated**: 25
- **Deterministic Arithmetic Accuracy**: **100.0%** (25/25 passed)
- **Evaluation Tolerance**: $\pm ₹0.01$ currency precision.

## 2. Experimental Results Table (Copy into Final Year Dissertation)

| ID | Natural Language Query | Routed Intent | Expected Value | Computed Value | Status |
|:---:|---|---|:---:|:---:|:---:|
| 1 | What is my total revenue? | `revenue_summary` | ₹27,530.00 | ₹27,530.00 | **PASS** |
| 2 | How much money did we make in total? | `revenue_summary` | ₹27,530.00 | ₹27,530.00 | **PASS** |
| 3 | What were our total sales in January 2024? | `revenue_summary` | ₹16,360.00 | ₹16,360.00 | **PASS** |
| 4 | What were our total sales in February 2024? | `revenue_summary` | ₹11,170.00 | ₹11,170.00 | **PASS** |
| 5 | What are my total operating expenses? | `expense_summary` | ₹285,199.00 | ₹285,199.00 | **PASS** |
| 6 | How much did we spend in January 2024? | `expense_summary` | ₹144,500.00 | ₹144,500.00 | **PASS** |
| 7 | How much did we spend in February 2024? | `expense_summary` | ₹140,699.00 | ₹140,699.00 | **PASS** |
| 8 | What is my net profit? | `net_profit` | ₹-257,669.00 | ₹-257,669.00 | **PASS** |
| 9 | Are we profitable overall? | `net_profit` | ₹-257,669.00 | ₹-257,669.00 | **PASS** |
| 10 | What is our net profit for January 2024? | `net_profit` | ₹-128,140.00 | ₹-128,140.00 | **PASS** |
| 11 | What are my top products by revenue? | `top_products` | ₹7,680.00 | ₹7,680.00 | **PASS** |
| 12 | Which item generated the highest sales? | `top_products` | ₹7,680.00 | ₹7,680.00 | **PASS** |
| 13 | What are my top selling products by quantity? | `top_products` | ₹36.00 | ₹36.00 | **PASS** |
| 14 | Which item sold the most units? | `top_products` | ₹36.00 | ₹36.00 | **PASS** |
| 15 | Which items sold the lowest volume? | `bottom_products` | ₹4.00 | ₹4.00 | **PASS** |
| 16 | What are my least popular items? | `bottom_products` | ₹4.00 | ₹4.00 | **PASS** |
| 17 | What was my highest revenue month? | `highest_revenue_month` | ₹16,360.00 | ₹16,360.00 | **PASS** |
| 18 | Which month had the best sales? | `highest_revenue_month` | ₹16,360.00 | ₹16,360.00 | **PASS** |
| 19 | What were my biggest expenses? | `biggest_expense` | ₹25,000.00 | ₹25,000.00 | **PASS** |
| 20 | What was our largest expense transaction? | `biggest_expense` | ₹25,000.00 | ₹25,000.00 | **PASS** |
| 21 | How much did we spend on Salaries? | `expense_by_category` | ₹112,000.00 | ₹112,000.00 | **PASS** |
| 22 | How much did we spend on Rent? | `expense_by_category` | ₹100,000.00 | ₹100,000.00 | **PASS** |
| 23 | How much did we spend on Utilities? | `expense_by_category` | ₹7,899.00 | ₹7,899.00 | **PASS** |
| 24 | How is my business performing? | `business_summary` | ₹27,530.00 | ₹27,530.00 | **PASS** |
| 25 | Compare this month with last month | `period_comparison` | ₹-5,190.00 | ₹-5,190.00 | **PASS** |

## 3. Academic Defense Discussion (Viva Voce)
- **Hallucination Prevention**: Traditional LLM-based business intelligence systems suffer from numerical hallucination when performing aggregations over long contexts. BizIntel completely eliminates arithmetic hallucination by employing **Deterministic Intent Routing**: the model acts strictly as a query classifier and language formatter, while all numeric sums, averages, and group-bys are executed natively in Python/SQL.
- **Tenant Isolation**: All queries enforce strict tenant filtering (`Sales.tenant_id == user.tenant_id`), guaranteeing zero cross-business data leakage.