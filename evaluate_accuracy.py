"""
evaluate_accuracy.py

Independent accuracy scoring for the reconciliation engine.

This script compares what reconcile.py DECIDED (in reconciliation_report.csv)
against ground_truth.csv -- the true, known-correct answer key that was
generated alongside the synthetic data but NEVER shown to reconcile.py.

This turns "the engine reports 100% match rate" (a self-reported claim)
into an independently verified accuracy score (precision/recall), which
is a much stronger and more credible claim.

Categories scored:
- CORRECT MATCH: engine matched order to the actual correct settlement
- WRONG MATCH:    engine matched order to an INCORRECT settlement (worst
                   kind of error -- silently wrong, not just missed)
- CORRECT EXCEPTION: engine correctly refused to match (order truly
                   had no correct settlement, e.g. refunded/orphan)
- MISSED MATCH:   engine reported "exception" but a true match existed
                   (overly cautious -- safe but incomplete)
"""

import csv


def load_ground_truth():
    with open("ground_truth.csv", newline="") as f:
        return {row["order_id"]: row["true_settlement_id"] for row in csv.DictReader(f)}


def load_engine_results():
    """Returns order_id -> settlement_id the engine matched it to (or None)."""
    engine_matches = {}
    with open("reconciliation_report.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["order_id"]:  # skip settlement-only exception rows
                engine_matches[row["order_id"]] = row["settlement_id"] or None
    return engine_matches


def evaluate():
    truth = load_ground_truth()
    engine = load_engine_results()

    correct_match = []
    wrong_match = []
    correct_exception = []
    missed_match = []
    not_evaluated = []  # orders in ground truth but not in engine output (shouldn't happen)

    for order_id, true_settlement in truth.items():
        if order_id not in engine:
            not_evaluated.append(order_id)
            continue

        engine_settlement = engine[order_id]
        true_is_none = true_settlement in ("NONE",)

        if true_is_none:
            if engine_settlement is None:
                correct_exception.append(order_id)
            else:
                wrong_match.append((order_id, "expected NO match", engine_settlement))
        else:
            if engine_settlement == true_settlement:
                correct_match.append(order_id)
            elif engine_settlement is None:
                missed_match.append((order_id, true_settlement))
            else:
                wrong_match.append((order_id, true_settlement, engine_settlement))

    total = len(truth)
    print("=" * 70)
    print("INDEPENDENT ACCURACY SCORE (engine output vs. hidden ground truth)")
    print("=" * 70)
    print(f"Total orders evaluated:        {total}")
    print(f"Correct matches:               {len(correct_match)}")
    print(f"Correct exceptions (no match needed, none given): {len(correct_exception)}")
    print(f"Missed matches (too cautious):  {len(missed_match)}")
    print(f"WRONG matches (silently incorrect): {len(wrong_match)}")
    if not_evaluated:
        print(f"WARNING - not found in engine output: {len(not_evaluated)} {not_evaluated}")
    print()

    accuracy = (len(correct_match) + len(correct_exception)) / total * 100
    print(f"Overall accuracy: {accuracy:.1f}%  "
          f"(({len(correct_match)} correct matches + {len(correct_exception)} correct "
          f"exceptions) / {total} total)")
    print()

    if wrong_match:
        print("--- WRONG MATCHES (most important to review) ---")
        for order_id, expected, got in wrong_match:
            print(f"  {order_id}: expected '{expected}', engine said '{got}'")
    else:
        print("No wrong matches -- zero cases where the engine confidently matched "
              "an order to the WRONG settlement.")

    if missed_match:
        print("\n--- MISSED MATCHES (engine was too cautious, safe but incomplete) ---")
        for order_id, expected in missed_match:
            print(f"  {order_id}: true match was '{expected}', engine reported exception")

    return {
        "total": total,
        "correct_match": len(correct_match),
        "correct_exception": len(correct_exception),
        "missed_match": len(missed_match),
        "wrong_match": len(wrong_match),
        "accuracy_pct": accuracy,
    }


if __name__ == "__main__":
    evaluate()
