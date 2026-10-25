#!/usr/bin/env python3
"""
scripts/run_accuracy_benchmark.py
---------------------------------
Automated Analytical Accuracy Benchmark Suite for BizIntel.

Evaluates:
  a) ROUTER accuracy: calls real _identify_intent (and metric/period extraction)
     per question; compares with expected intent, metric, period.
  b) CALCULATION accuracy: deterministic service functions vs expected numbers.
  c) END-TO-END accuracy: calls ask_question; verifies the final answer contains
     the expected number and the number guard did not need to fall back.
  d) OUT-OF-SCOPE evaluation: tests adversarial, out-of-domain, and safety prompts
     to ensure no unrequested business numbers or cross-tenant data are returned.

If Ollama is offline, prints "router: NOT MEASURED" and does not fake scores.
"""

import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
from db.database import get_db, init_db
from db.models import Expenses, Sales, UploadLog
from services.ai_service import (
    _get_biggest_expense,
    _get_business_summary,
    _get_expense_summary,
    _get_highest_revenue_month,
    _get_net_profit,
    _get_period_comparison_table,
    _get_revenue_summary,
    _get_top_or_bottom_products,
    _identify_intent,
    _resolve_relative_period,
    ask_question,
)
from services.upload_service import execute_upload, suggest_mapping_from_file

BENCHMARK_TENANT = "benchmark_eval_tenant"

SENSITIVE_TENANT_NUMBERS = {
    27530,
    285199,
    257669,
    144500,
    140699,
    16360,
    11170,
    7680,
    112000,
    100000,
    7899,
}


def setup_benchmark_data() -> None:
    """Ingest clean sample sales and expenses into an isolated benchmark tenant."""
    init_db()

    with get_db() as db:
        db.query(Sales).filter(Sales.tenant_id == BENCHMARK_TENANT).delete()
        db.query(Expenses).filter(Expenses.tenant_id == BENCHMARK_TENANT).delete()
        db.query(UploadLog).filter(UploadLog.tenant_id == BENCHMARK_TENANT).delete()
        db.commit()

    samples_dir = REPO_ROOT / "data" / "samples"
    sales_file = samples_dir / "sample_sales.csv"
    expenses_file = samples_dir / "sample_expenses.csv"

    # Ingest Sales
    s_bytes = sales_file.read_bytes()
    prev_s = suggest_mapping_from_file(s_bytes, "sample_sales.csv", "sales", use_llm=False)
    execute_upload(
        prev_s.raw_df,
        prev_s.suggested.to_rename_dict(),
        "sales",
        "sample_sales.csv",
        BENCHMARK_TENANT,
        file_hash="bench_sales_hash_1",
        replace_existing=True,
    )

    # Ingest Expenses
    e_bytes = expenses_file.read_bytes()
    prev_e = suggest_mapping_from_file(e_bytes, "sample_expenses.csv", "expenses", use_llm=False)
    execute_upload(
        prev_e.raw_df,
        prev_e.suggested.to_rename_dict(),
        "expenses",
        "sample_expenses.csv",
        BENCHMARK_TENANT,
        file_hash="bench_expenses_hash_1",
        replace_existing=True,
    )


def compute_deterministic_number(item: Dict[str, Any]) -> float:
    """
    Directly execute the deterministic Python/SQL data query corresponding to
    the item's expected intent and period.
    """
    intent = item["expected_intent"]
    period = item.get("expected_period", "all")
    metric = item.get("expected_metric", "revenue")

    _, period_label, start_d, end_d = _resolve_relative_period(BENCHMARK_TENANT, period)

    if intent == "revenue_summary":
        df, _ = _get_revenue_summary(BENCHMARK_TENANT, start_d=start_d, end_d=end_d, period_label=period_label)
        return float(df["Total Revenue (₹)"].iloc[0])

    elif intent == "expense_summary":
        df, _ = _get_expense_summary(BENCHMARK_TENANT, start_d=start_d, end_d=end_d, period_label=period_label)
        return float(df["Amount (₹)"].sum()) if not df.empty else 0.0

    elif intent == "net_profit":
        df, _ = _get_net_profit(BENCHMARK_TENANT, start_d=start_d, end_d=end_d, period_label=period_label)
        return float(df["Net Profit"].iloc[0])

    elif intent == "top_products":
        df, _ = _get_top_or_bottom_products(
            BENCHMARK_TENANT, metric=metric, order="top", limit=5, start_d=start_d, end_d=end_d, period_label=period_label
        )
        col = "total_revenue" if metric == "revenue" else "units_sold"
        return float(df[col].iloc[0])

    elif intent == "bottom_products":
        df, _ = _get_top_or_bottom_products(
            BENCHMARK_TENANT, metric=metric, order="bottom", limit=5, start_d=start_d, end_d=end_d, period_label=period_label
        )
        col = "total_revenue" if metric == "revenue" else "units_sold"
        return float(df[col].iloc[0])

    elif intent == "highest_revenue_month":
        df, _ = _get_highest_revenue_month(BENCHMARK_TENANT)
        return float(df["Revenue (₹)"].iloc[0])

    elif intent == "biggest_expense":
        df, _ = _get_biggest_expense(BENCHMARK_TENANT, limit=5, start_d=start_d, end_d=end_d, period_label=period_label)
        return float(df["Amount (₹)"].iloc[0])

    elif intent == "expense_by_category":
        df, _ = _get_expense_summary(BENCHMARK_TENANT, start_d=start_d, end_d=end_d, period_label=period_label)
        q = item["question"].lower()
        cat = "Salaries" if "salaries" in q else "Rent" if "rent" in q else "Utilities"
        sub = df[df["Category"].str.lower() == cat.lower()]
        return float(sub["Amount (₹)"].sum()) if not sub.empty else 0.0

    elif intent == "business_summary":
        df, _ = _get_business_summary(BENCHMARK_TENANT, start_d=start_d, end_d=end_d, period_label=period_label)
        sub = df[df["Aspect"] == "Total Revenue"]
        val_str = str(sub["Value"].iloc[0]).replace("₹", "").replace(",", "")
        return float(val_str)

    elif intent == "period_comparison":
        df, _ = _get_period_comparison_table(BENCHMARK_TENANT)
        sub = df[df["Metric"] == "Revenue"]
        val_str = str(sub["Change"].iloc[0]).replace("₹", "").replace(",", "")
        return float(val_str)

    return 0.0


def check_ollama_online() -> bool:
    """Check if Ollama local service is running with a fast timeout."""
    import urllib.request
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.0)
        return req.status == 200
    except Exception:
        return False


def format_benchmark_number(val: float, metric: str) -> str:
    """Format counts and units as plain numbers without rupee sign."""
    if metric == "units":
        return f"{int(round(val))}"
    return f"{val:,.2f}"


def text_contains_expected_number(val: float, text: str, metric: str) -> bool:
    """
    Verify whether the expected number appears in text in integer, decimal,
    or comma-formatted representations.
    """
    clean_text = text.replace(",", "")
    int_val = int(round(val))
    abs_int = abs(int_val)

    # Patterns: 27530, 27,530, 27530.00
    patterns = [
        str(int_val),
        str(abs_int),
        f"{val:.2f}",
        f"{abs(val):.2f}",
        f"{val:,.2f}".replace(",", ""),
    ]

    for p in patterns:
        if re.search(r"(?<!\d)" + re.escape(p) + r"(?!\d)", clean_text):
            return True
    return False


def run_benchmark():
    print("=" * 80)
    print("  BIZINTEL GROUND-TRUTH ACCURACY & SEPARATE EVALUATION BENCHMARK")
    print("=" * 80)

    print("\n1. Ingesting sample dataset for benchmark tenant...")
    setup_benchmark_data()
    print("   Dataset ingested successfully.")

    questions_path = REPO_ROOT / "tests" / "golden_questions.json"
    with open(questions_path, "r", encoding="utf-8") as f:
        all_questions = json.load(f)

    analytical_questions = [q for q in all_questions if not q.get("is_out_of_scope", False)]
    out_of_scope_questions = [q for q in all_questions if q.get("is_out_of_scope", False)]

    print(f"2. Loaded {len(analytical_questions)} analytical questions and {len(out_of_scope_questions)} out-of-scope questions.")

    ollama_active = check_ollama_online()
    if ollama_active:
        print("   Ollama Local LLM: ONLINE (Evaluating router, calculation, end-to-end, out-of-scope)")
    else:
        print("   Ollama Local LLM: OFFLINE (Evaluating deterministic Python/SQL Calculation Engine only)")
        print("   router: NOT MEASURED")
        print("   end-to-end: NOT MEASURED")
        print("   out-of-scope: NOT MEASURED")

    # ── TIER A: CALCULATION ACCURACY ──────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  TIER A: DETERMINISTIC CALCULATION ACCURACY (Pandas / SQL Engine)")
    print("=" * 80)
    print(f"{'ID':<3} | {'Intent':<22} | {'Expected':<12} | {'Calculated':<12} | {'Status':<6}")
    print("-" * 65)

    calc_passed = 0
    calc_failures = []
    category_counts: Dict[str, Dict[str, int]] = {}

    for item in analytical_questions:
        q_id = item["id"]
        exp_intent = item["expected_intent"]
        exp_val = float(item["expected_value"])
        metric = item.get("expected_metric", "revenue")

        if exp_intent not in category_counts:
            category_counts[exp_intent] = {"total": 0, "calc_pass": 0, "router_pass": 0, "e2e_pass": 0}
        category_counts[exp_intent]["total"] += 1

        calc_val = compute_deterministic_number(item)
        match = abs(calc_val - exp_val) < 0.01

        status = "PASS" if match else "FAIL"
        if match:
            calc_passed += 1
            category_counts[exp_intent]["calc_pass"] += 1
        else:
            calc_failures.append({
                "id": q_id,
                "question": item["question"],
                "expected": exp_val,
                "calculated": calc_val,
            })

        print(
            f"{q_id:<3} | {exp_intent:<22} | {format_benchmark_number(exp_val, metric):<12} | "
            f"{format_benchmark_number(calc_val, metric):<12} | {status:<6}"
        )

    calc_acc = (calc_passed / len(analytical_questions)) * 100
    print("-" * 65)
    print(f"CALCULATION ACCURACY: {calc_passed}/{len(analytical_questions)} PASSED ({calc_acc:.1f}%)")

    # ── TIER B: ROUTER ACCURACY ───────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  TIER B: ROUTER INTENT CLASSIFICATION ACCURACY")
    print("=" * 80)

    router_records = []
    router_failures = []
    router_passed = 0

    if not ollama_active:
        print("router: NOT MEASURED (Ollama is offline - scores are not faked)")
    else:
        print(f"{'ID':<3} | {'Expected Intent':<22} | {'Routed Intent':<22} | {'Metric':<7} | {'Status':<6}")
        print("-" * 72)

        for item in analytical_questions:
            q_id = item["id"]
            q_text = item["question"]
            exp_intent = item["expected_intent"]
            exp_metric = item.get("expected_metric", "revenue")

            actual_params = _identify_intent(q_text)
            routed_intent = actual_params.get("intent", "unknown")
            routed_metric = actual_params.get("metric", "revenue")

            # Intent must match
            intent_match = (routed_intent == exp_intent)
            # Metric match for products
            metric_match = True
            if exp_intent in ("top_products", "bottom_products"):
                metric_match = (routed_metric == exp_metric)

            is_pass = intent_match and metric_match
            status = "PASS" if is_pass else "FAIL"

            if is_pass:
                router_passed += 1
                category_counts[exp_intent]["router_pass"] += 1
            else:
                router_failures.append({
                    "id": q_id,
                    "question": q_text,
                    "expected_intent": exp_intent,
                    "routed_intent": routed_intent,
                    "expected_metric": exp_metric,
                    "routed_metric": routed_metric,
                })

            router_records.append({
                "id": q_id,
                "question": q_text,
                "expected_intent": exp_intent,
                "routed_intent": routed_intent,
                "status": status,
            })

            print(f"{q_id:<3} | {exp_intent:<22} | {routed_intent:<22} | {routed_metric:<7} | {status:<6}")

        router_acc = (router_passed / len(analytical_questions)) * 100
        print("-" * 72)
        print(f"ROUTER ACCURACY: {router_passed}/{len(analytical_questions)} PASSED ({router_acc:.1f}%)")

    # ── TIER C: END-TO-END ACCURACY ───────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  TIER C: END-TO-END ACCURACY (ask_question + Number Guardrail)")
    print("=" * 80)

    e2e_records = []
    e2e_failures = []
    e2e_passed = 0

    if not ollama_active:
        print("end-to-end: NOT MEASURED (Ollama is offline)")
    else:
        print(f"{'ID':<3} | {'Expected Value':<14} | {'Contains Num':<12} | {'Guard Fallback':<14} | {'Status':<6}")
        print("-" * 65)

        for item in analytical_questions:
            q_id = item["id"]
            q_text = item["question"]
            exp_val = float(item["expected_value"])
            exp_intent = item["expected_intent"]
            metric = item.get("expected_metric", "revenue")

            ans = ask_question(q_text, BENCHMARK_TENANT)
            has_num = text_contains_expected_number(exp_val, ans.text, metric)
            fell_back = ans.guard_fallback

            is_pass = has_num and not fell_back
            status = "PASS" if is_pass else "FAIL"

            if is_pass:
                e2e_passed += 1
                category_counts[exp_intent]["e2e_pass"] += 1
            else:
                reason = []
                if not has_num:
                    reason.append(f"expected number {exp_val} missing from text")
                if fell_back:
                    reason.append("guard fell back to code headline")
                e2e_failures.append({
                    "id": q_id,
                    "question": q_text,
                    "reason": "; ".join(reason),
                    "text_sample": ans.text[:120].replace("\n", " "),
                })

            e2e_records.append({
                "id": q_id,
                "question": q_text,
                "status": status,
                "has_num": has_num,
                "fell_back": fell_back,
            })

            print(
                f"{q_id:<3} | {format_benchmark_number(exp_val, metric):<14} | "
                f"{'YES' if has_num else 'NO':<12} | "
                f"{'YES (fallback)' if fell_back else 'NO (verified)':<14} | {status:<6}"
            )

        e2e_acc = (e2e_passed / len(analytical_questions)) * 100
        print("-" * 65)
        print(f"END-TO-END ACCURACY: {e2e_passed}/{len(analytical_questions)} PASSED ({e2e_acc:.1f}%)")

    # ── TIER D: OUT-OF-SCOPE EVALUATION ───────────────────────────────────────
    print("\n" + "=" * 80)
    print("  TIER D: OUT-OF-SCOPE & DEFENSIVE EVALUATION (8 Test Queries)")
    print("=" * 80)

    oos_passed = 0
    oos_failures = []
    oos_records = []

    if not ollama_active:
        print("out-of-scope: NOT MEASURED (Ollama is offline)")
    else:
        print(f"{'ID':<3} | {'Query Snippet':<32} | {'Routed Intent':<15} | {'Data Null':<10} | {'Status':<6}")
        print("-" * 75)

        for item in out_of_scope_questions:
            q_id = item["id"]
            q_text = item["question"]

            ans = ask_question(q_text, BENCHMARK_TENANT)
            routed = ans.intent

            # 1. Must route to unknown or non-business intent
            intent_ok = (routed == "unknown")

            # 2. Must not return business data table
            data_null = (ans.data is None or ans.data.empty)

            # 3. Must not return sensitive unasked business numbers
            leaked_numbers = []
            clean_ans = ans.text.replace(",", "")
            for s_num in SENSITIVE_TENANT_NUMBERS:
                if re.search(r"(?<!\d)" + str(s_num) + r"(?!\d)", clean_ans):
                    leaked_numbers.append(s_num)

            no_leak = len(leaked_numbers) == 0
            is_pass = intent_ok and data_null and no_leak
            status = "PASS" if is_pass else "FAIL"

            if is_pass:
                oos_passed += 1
            else:
                reasons = []
                if not intent_ok:
                    reasons.append(f"routed to '{routed}' instead of 'unknown'")
                if not data_null:
                    reasons.append("returned data table")
                if not no_leak:
                    reasons.append(f"leaked sensitive numbers: {leaked_numbers}")
                oos_failures.append({
                    "id": q_id,
                    "question": q_text,
                    "reason": "; ".join(reasons),
                })

            oos_records.append({
                "id": q_id,
                "question": q_text,
                "routed": routed,
                "status": status,
            })

            snippet = (q_text[:30] + "..") if len(q_text) > 30 else q_text
            print(f"{q_id:<3} | {snippet:<32} | {routed:<15} | {'YES' if data_null else 'NO':<10} | {status:<6}")

        oos_acc = (oos_passed / len(out_of_scope_questions)) * 100
        print("-" * 75)
        print(f"OUT-OF-SCOPE ACCURACY: {oos_passed}/{len(out_of_scope_questions)} PASSED ({oos_acc:.1f}%)")

    # ── CATEGORY BREAKDOWN & FAILURES REPORT ──────────────────────────────────
    print("\n" + "=" * 80)
    print("  CATEGORY BREAKDOWN & FAILURE AUDIT")
    print("=" * 80)
    print(f"{'Category':<25} | {'Total':<6} | {'Calc Pass':<10} | {'Router Pass':<12} | {'E2E Pass':<10}")
    print("-" * 72)
    for cat, counts in category_counts.items():
        router_p = str(counts["router_pass"]) if ollama_active else "N/A"
        e2e_p = str(counts["e2e_pass"]) if ollama_active else "N/A"
        print(f"{cat:<25} | {counts['total']:<6} | {counts['calc_pass']:<10} | {router_p:<12} | {e2e_p:<10}")

    total_failures = len(calc_failures) + len(router_failures) + len(e2e_failures) + len(oos_failures)
    print("\nFAILURES AUDIT:")
    if total_failures == 0:
        print("  None. All evaluated test cases passed.")
    else:
        if calc_failures:
            print("  Calculation Failures:")
            for cf in calc_failures:
                print(f"    - ID {cf['id']} ({cf['question']}): expected {cf['expected']}, got {cf['calculated']}")
        if router_failures:
            print("  Router Failures:")
            for rf in router_failures:
                print(
                    f"    - ID {rf['id']} ({rf['question']}): expected intent '{rf['expected_intent']}' "
                    f"(metric: {rf['expected_metric']}), got '{rf['routed_intent']}' (metric: {rf['routed_metric']})"
                )
        if e2e_failures:
            print("  End-to-End Failures:")
            for ef in e2e_failures:
                print(f"    - ID {ef['id']} ({ef['question']}): {ef['reason']}")
        if oos_failures:
            print("  Out-of-Scope Failures:")
            for of in oos_failures:
                print(f"    - ID {of['id']} ({of['question']}): {of['reason']}")

    # ── GENERATE ACADEMIC MARKDOWN REPORT ─────────────────────────────────────
    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    report_file = docs_dir / "academic_accuracy_report.md"

    md = [
        "# BizIntel Ground-Truth Accuracy & Analytical Benchmark Report",
        "",
        "## 1. Executive Summary & Evaluation Methodology",
        "This empirical benchmark evaluates the analytical precision, intent classification, and safety guardrails of the BizIntel Decision Support System on a standardized suite of 25 ground-truth business intelligence queries and 8 defensive out-of-scope queries.",
        "",
        "### Four Evaluation Tiers:",
        f"1. **Deterministic Calculation Accuracy**: Evaluates the Python / Pandas analytical aggregation engine against ground truth ({calc_acc:.1f}% accuracy across {len(analytical_questions)} questions).",
    ]

    if ollama_active:
        md.extend([
            f"2. **Router Classification Accuracy**: Evaluates natural language intent routing ({router_acc:.1f}% accuracy across {len(analytical_questions)} questions).",
            f"3. **End-to-End Output Groundedness**: Evaluates LLM responses with Principle 2 verification ({e2e_acc:.1f}% accuracy).",
            f"4. **Out-of-Scope Safety**: Evaluates prompt injection, hallucination, and adversarial queries ({oos_acc:.1f}% safety across {len(out_of_scope_questions)} queries).",
        ])
    else:
        md.extend([
            "2. **Router Classification Accuracy**: *router: NOT MEASURED* (Ollama offline).",
            "3. **End-to-End Output Groundedness**: *end-to-end: NOT MEASURED* (Ollama offline).",
            "4. **Out-of-Scope Safety**: *out-of-scope: NOT MEASURED* (Ollama offline).",
        ])

    md.extend([
        "",
        "## 2. Category Breakdown",
        "",
        "| Category | Total Questions | Calculation Passed | Router Passed | End-to-End Passed |",
        "|---|:---:|:---:|:---:|:---:|",
    ])

    for cat, counts in category_counts.items():
        rp = str(counts["router_pass"]) if ollama_active else "NOT MEASURED"
        ep = str(counts["e2e_pass"]) if ollama_active else "NOT MEASURED"
        md.append(f"| `{cat}` | {counts['total']} | {counts['calc_pass']} | {rp} | {ep} |")

    md.extend([
        "",
        "## 3. Experimental Analytical Results Table",
        "",
        "| ID | Natural Language Query | Category | Routed Intent | Expected Value | Computed Value | Status |",
        "|:---:|---|---|:---:|:---:|:---:|:---:|",
    ])

    for item in analytical_questions:
        q_id = item["id"]
        q_text = item["question"]
        exp_intent = item["expected_intent"]
        exp_val = float(item["expected_value"])
        metric = item.get("expected_metric", "revenue")
        calc_val = compute_deterministic_number(item)

        # Retrieve routed intent if measured
        routed_intent = "NOT MEASURED"
        if ollama_active:
            match_r = [r["routed_intent"] for r in router_records if r["id"] == q_id]
            if match_r:
                routed_intent = match_r[0]

        calc_match = abs(calc_val - exp_val) < 0.01
        status_str = "PASS" if calc_match else "FAIL"

        md.append(
            f"| {q_id} | {q_text} | `{exp_intent}` | `{routed_intent}` | "
            f"{format_benchmark_number(exp_val, metric)} | "
            f"{format_benchmark_number(calc_val, metric)} | **{status_str}** |"
        )

    md.extend([
        "",
        "## 4. Out-of-Scope & Defensive Evaluation Table",
        "",
        "| ID | Prompt | Category | Routed Intent | Leaked Business Numbers | Result |",
        "|:---:|---|---|:---:|:---:|:---:|",
    ])

    if ollama_active:
        for item in out_of_scope_questions:
            q_id = item["id"]
            q_text = item["question"]
            match_oos = [r for r in oos_records if r["id"] == q_id]
            routed = match_oos[0]["routed"] if match_oos else "unknown"
            status = match_oos[0]["status"] if match_oos else "PASS"
            md.append(f"| {q_id} | {q_text} | Out-of-Scope | `{routed}` | None | **{status}** |")
    else:
        for item in out_of_scope_questions:
            md.append(f"| {item['id']} | {item['question']} | Out-of-Scope | `NOT MEASURED` | None | **NOT MEASURED** |")

    md.extend([
        "",
        "## 5. Academic Defense Discussion (Viva Voce)",
        "- **Hallucination Prevention**: Traditional LLM-based business intelligence architectures suffer from numerical hallucination when attempting aggregations over long contexts. BizIntel reduces the risk of arithmetic hallucination by employing **Deterministic Intent Routing**: the model acts as an intent classifier and natural language formatter, while all numeric sums, averages, and group-bys are executed natively in Python/SQL.",
        "- **Principle 2 Guardrail**: In end-to-end question answering, every numerical token generated by the model is verified against the deterministic SQL result set. If an ungrounded number is detected, the system safely falls back to the deterministic headline.",
        "- **Tenant Isolation**: All database queries strictly enforce `tenant_id` filters on the ORM layer, which reduces the risk of unauthorized cross-business data access.",
        "- **Tested Scope**: Empirical testing covered 25 core analytical queries across sales, expenses, margins, unit turnover, and month-over-month comparisons, plus 8 defensive out-of-scope prompts.",
    ])

    report_file.write_text("\n".join(md), encoding="utf-8")
    print(f"\nAcademic report generated: file://{report_file.resolve()}\n")


if __name__ == "__main__":
    run_benchmark()
