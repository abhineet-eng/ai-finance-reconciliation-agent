"""
generate_data.py

Generates two synthetic datasets for the Track 4 (AI Finance Controller)
reconciliation project:

1. orders.csv            -> "our side": what we charged customers
2. bank_settlement.csv    -> "bank side": what actually landed in the account

The datasets are DELIBERATELY messy in realistic ways (fees, delays,
batching, garbled references, refunds, orphans) so the matching engine
has real work to do -- not a trivial 1:1 lookup.
"""

import csv
import random
from datetime import date, timedelta

random.seed(42)  # reproducible output

NUM_ORDERS = 60  # >50 as required by the brief

PAYMENT_METHODS = ["UPI", "Card", "Netbanking"]
# Different gateway fee % depending on payment method (realistic — Razorpay
# charges different rates for UPI vs Card vs Netbanking)
FEE_RATES = {"UPI": 0.005, "Card": 0.02, "Netbanking": 0.015}

FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Ananya", "Karan",
               "Neha", "Arjun", "Divya", "Rohan", "Isha", "Manish", "Pooja"]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Reddy", "Iyer", "Nair", "Singh",
              "Mehta", "Kapoor", "Joshi"]

def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def random_gateway_txn_id(i):
    return f"pay_{random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{random.randint(1000,9999)}x{i}"

START_DATE = date(2026, 8, 1)

orders = []
settlements = []
ground_truth = []  # order_id -> true correct settlement_id (or "NONE"/"EXCEPTION")
# This is the answer key. It is written to its own file and is NEVER read
# by reconcile.py or explain_exceptions.py -- it exists purely so we can
# independently score how accurate the matching engine actually is,
# instead of just trusting the engine's own self-reported numbers.

settlement_counter = 1000
batch_counter = 200

# We'll build orders first, then decide per-order how it shows up (or doesn't)
# in the settlement file, based on a scenario tag.

scenario_pool = (
    ["clean_match"] * 26      # ~43% - straightforward
    + ["fee_variation"] * 6    # relies on correct per-method fee logic
    + ["batched"] * 8          # multiple orders -> one settlement row (handled separately below)
    + ["delayed"] * 6          # settles 4-5 days later than usual
    + ["garbled_ref"] * 6      # reference_note has typo/partial id
    + ["missing_ref"] * 4      # reference_note blank
    + ["refunded"] * 3         # correctly has NO settlement
    + ["duplicate_failed"] * 3 # duplicate attempt, one failed
    + ["orphan_settlement"] * 3# a settlement with no matching order at all
)
random.shuffle(scenario_pool)
# pad/trim to NUM_ORDERS
while len(scenario_pool) < NUM_ORDERS:
    scenario_pool.append("clean_match")
scenario_pool = scenario_pool[:NUM_ORDERS]

batch_groups = {}  # batch_id -> list of order rows, for 'batched' scenario

order_seq = 1
for i, scenario in enumerate(scenario_pool):
    order_id = f"ORD{1000+order_seq}"
    order_seq += 1
    method = random.choice(PAYMENT_METHODS)
    amount = round(random.uniform(300, 5000), 2)
    order_date = START_DATE + timedelta(days=random.randint(0, 20))
    gateway_txn_id = random_gateway_txn_id(i)
    status = "Success"

    if scenario == "refunded":
        status = "Refunded"
    if scenario == "duplicate_failed":
        status = "Success"  # the real one succeeds; we'll add a failed twin below

    orders.append({
        "order_id": order_id,
        "customer_name": random_name(),
        "order_amount": amount,
        "order_date": order_date.isoformat(),
        "payment_method": method,
        "gateway_txn_id": gateway_txn_id,
        "status": status,
    })

    fee_rate = FEE_RATES[method]
    settled_amount = round(amount * (1 - fee_rate), 2)
    settle_date = order_date + timedelta(days=random.choice([1, 2, 2, 3]))

    if scenario == "clean_match":
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": gateway_txn_id,
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})

    elif scenario == "fee_variation":
        # same as clean, but fee already correctly applied per-method above --
        # this scenario exists to test whether the matcher WRONGLY assumes a
        # single flat fee % for everyone. No extra corruption needed here;
        # the "trap" is in the matching logic, not the data.
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": gateway_txn_id,
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})

    elif scenario == "delayed":
        settle_date = order_date + timedelta(days=random.randint(4, 6))
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": gateway_txn_id,
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})

    elif scenario == "garbled_ref":
        # corrupt the reference: drop chars, add noise, or truncate
        corrupt_choice = random.choice(["truncate", "typo", "suffix"])
        if corrupt_choice == "truncate":
            ref = gateway_txn_id[:len(gateway_txn_id)//2]
        elif corrupt_choice == "typo":
            ref = gateway_txn_id.replace("x", "z", 1)
        else:
            ref = gateway_txn_id + "-partial"
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": ref,
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})

    elif scenario == "missing_ref":
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": "",
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})

    elif scenario == "refunded":
        # No settlement row at all -- correctly should stay unmatched.
        ground_truth.append({"order_id": order_id, "true_settlement_id": "NONE", "scenario": scenario})

    elif scenario == "duplicate_failed":
        # Add a second "order" row that's a failed duplicate attempt --
        # it should NOT appear in settlements, and matcher should not
        # treat its absence as an error.
        dup_id = f"ORD{1000+order_seq}"
        order_seq += 1
        orders.append({
            "order_id": dup_id,
            "customer_name": orders[-1]["customer_name"],
            "order_amount": amount,
            "order_date": order_date.isoformat(),
            "payment_method": method,
            "gateway_txn_id": random_gateway_txn_id(i * 100),
            "status": "Failed",
        })
        # the original succeeded order still gets a clean settlement
        settlement_counter += 1
        stl_id = f"STL{settlement_counter}"
        settlements.append({
            "settlement_id": stl_id,
            "settled_amount": settled_amount,
            "settlement_date": settle_date.isoformat(),
            "reference_note": gateway_txn_id,
            "batch_id": "",
        })
        ground_truth.append({"order_id": order_id, "true_settlement_id": stl_id, "scenario": scenario})
        ground_truth.append({"order_id": dup_id, "true_settlement_id": "NONE", "scenario": "duplicate_failed_twin"})

    elif scenario == "batched":
        batch_id = f"BATCH-{batch_counter}"
        batch_groups.setdefault(batch_id, []).append(
            (gateway_txn_id, settled_amount, settle_date, order_id)
        )

    elif scenario == "orphan_settlement":
        # This order intentionally gets NO settlement of its own -- it exists
        # only to keep the scenario pool's proportions meaningful. The actual
        # orphan settlements (bank credits with no matching order) are added
        # unconditionally below, independent of this order.
        ground_truth.append({"order_id": order_id, "true_settlement_id": "NONE", "scenario": scenario})

# Turn batch_groups into combined settlement rows (one settlement = sum of
# several orders' settled amounts, reference_note lists all txn ids)
for batch_id, entries in batch_groups.items():
    total = round(sum(e[1] for e in entries), 2)
    latest_date = max(e[2] for e in entries)
    combined_ref = ";".join(e[0] for e in entries)
    settlement_counter += 1
    stl_id = f"STL{settlement_counter}"
    settlements.append({
        "settlement_id": stl_id,
        "settled_amount": total,
        "settlement_date": latest_date.isoformat(),
        "reference_note": combined_ref,
        "batch_id": batch_id,
    })
    for (_txn_id, _amt, _date, batch_order_id) in entries:
        ground_truth.append({"order_id": batch_order_id, "true_settlement_id": stl_id, "scenario": "batched"})

# Add a couple of truly orphaned settlements (money appears with no matching order)
# These have NO order in ground_truth at all -- they should end up as
# unresolved EXCEPTIONS on the settlement side.
for _ in range(3):
    settlement_counter += 1
    settlements.append({
        "settlement_id": f"STL{settlement_counter}",
        "settled_amount": round(random.uniform(300, 3000), 2),
        "settlement_date": (START_DATE + timedelta(days=random.randint(0, 25))).isoformat(),
        "reference_note": random_gateway_txn_id(9999 + settlement_counter),
        "batch_id": "",
    })

random.shuffle(orders)
random.shuffle(settlements)

with open("orders.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["order_id", "customer_name", "order_amount",
                                            "order_date", "payment_method",
                                            "gateway_txn_id", "status"])
    writer.writeheader()
    writer.writerows(orders)

with open("bank_settlement.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["settlement_id", "settled_amount",
                                            "settlement_date", "reference_note",
                                            "batch_id"])
    writer.writeheader()
    writer.writerows(settlements)

with open("ground_truth.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["order_id", "true_settlement_id", "scenario"])
    writer.writeheader()
    writer.writerows(ground_truth)

print(f"Generated {len(orders)} order rows -> orders.csv")
print(f"Generated {len(settlements)} settlement rows -> bank_settlement.csv")
print(f"Generated {len(ground_truth)} ground-truth answer rows -> ground_truth.csv "
      f"(NOT used by reconcile.py -- kept separate for independent scoring)")
