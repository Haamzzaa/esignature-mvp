"""
Biometric Verification Benchmark Runner
========================================
Runs all genuine and impostor pairs through the pipeline and reports:
  - Genuine Match Rate (True Accept Rate)
  - Impostor Rejection Rate (True Reject Rate)
  - Average Genuine Similarity
  - Average Impostor Similarity
  - False Accepts
  - False Rejects
  - Retry Rate (pairs that failed pre-matching stages)

Usage:
    python tools/benchmark_biometric.py [--threshold 0.60] [--iteration 0]
"""

import os
import sys
import json
import argparse
import datetime

# Django setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from services.enterprise_biometric_service import run_biometric_pipeline

# ── Dataset paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BIOMETRIC_DIR = os.path.join(BASE_DIR, 'tests', 'biometric')

GENUINE_ID   = os.path.join(BIOMETRIC_DIR, 'genuine', 'id.jpeg')
GENUINE_SELFIES = [
    os.path.join(BIOMETRIC_DIR, 'genuine', 'selfie_1.jpg'),
    os.path.join(BIOMETRIC_DIR, 'genuine', 'selfie_2.jpg'),
    os.path.join(BIOMETRIC_DIR, 'genuine', 'selfie_3.jpg'),
    os.path.join(BIOMETRIC_DIR, 'genuine', 'selfie_4.jpg'),
]

IMPOSTOR_SELFIES = [
    os.path.join(BIOMETRIC_DIR, 'impostor', 'friend_1.JPG'),
    os.path.join(BIOMETRIC_DIR, 'impostor', 'friend_2.jpeg'),
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def run_pair(id_path, selfie_path, threshold):
    """Run one pair through the full pipeline and return a result dict."""
    try:
        report = run_biometric_pipeline(id_path, selfie_path, threshold=threshold)
    except Exception as e:
        return {
            "id": os.path.basename(id_path),
            "selfie": os.path.basename(selfie_path),
            "decision": "ERROR",
            "score": None,
            "error": str(e),
            "retry": True,
            "stage_failures": [],
        }

    decision = report.get("decision", "ERROR")
    score = report.get("score", None)

    # A pair is a RETRY if the pipeline bailed before producing a score
    is_retry = (decision == "RETRY" or score is None or score == 0.0)

    return {
        "id": os.path.basename(id_path),
        "selfie": os.path.basename(selfie_path),
        "decision": decision,
        "score": score,
        "reason": report.get("reason", ""),
        "retry": is_retry,
        "stage_failures": _collect_failures(report),
    }


def _collect_failures(report):
    failures = []
    for stage_name, stage_data in report.get("stages", {}).items():
        if not stage_data.get("passed", True):
            detail = stage_data.get("detail", {})
            for img_key in ("id_image", "live_image"):
                msg = detail.get(img_key, {}).get("error_message", "")
                if msg:
                    failures.append(f"{stage_name}[{img_key}]: {msg}")
    return failures


def compute_metrics(genuine_results, impostor_results, threshold):
    """Aggregate results into the full metric suite."""

    # Genuine pair stats
    genuine_scores = [r["score"] for r in genuine_results if r["score"] is not None]
    genuine_retries = sum(1 for r in genuine_results if r["retry"])
    genuine_matchable = [r for r in genuine_results if not r["retry"]]

    true_accepts = sum(1 for r in genuine_matchable if r["decision"] == "MATCH")
    false_rejects = sum(1 for r in genuine_matchable if r["decision"] in ("NO_MATCH", "MANUAL_REVIEW"))

    # Impostor pair stats
    impostor_scores = [r["score"] for r in impostor_results if r["score"] is not None]
    impostor_retries = sum(1 for r in impostor_results if r["retry"])
    impostor_matchable = [r for r in impostor_results if not r["retry"]]

    true_rejects = sum(1 for r in impostor_matchable if r["decision"] == "NO_MATCH")
    false_accepts = sum(1 for r in impostor_matchable if r["decision"] == "MATCH")

    total_pairs = len(genuine_results) + len(impostor_results)
    total_retries = genuine_retries + impostor_retries

    gmr = (true_accepts / len(genuine_matchable) * 100) if genuine_matchable else 0.0
    irr = (true_rejects / len(impostor_matchable) * 100) if impostor_matchable else 0.0
    retry_rate = (total_retries / total_pairs * 100) if total_pairs else 0.0

    return {
        "threshold": threshold,
        "genuine_match_rate_pct": round(gmr, 2),
        "impostor_rejection_rate_pct": round(irr, 2),
        "avg_genuine_similarity": round(sum(genuine_scores) / len(genuine_scores), 4) if genuine_scores else None,
        "avg_impostor_similarity": round(sum(impostor_scores) / len(impostor_scores), 4) if impostor_scores else None,
        "true_accepts": true_accepts,
        "false_rejects": false_rejects,
        "true_rejects": true_rejects,
        "false_accepts": false_accepts,
        "genuine_retries": genuine_retries,
        "impostor_retries": impostor_retries,
        "retry_rate_pct": round(retry_rate, 2),
        "total_genuine_pairs": len(genuine_results),
        "total_impostor_pairs": len(impostor_results),
    }


def print_banner(iteration):
    print()
    print("=" * 60)
    print(f"  BIOMETRIC BENCHMARK  --  Iteration {iteration}")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def print_metrics(metrics):
    print()
    print(f"  Threshold              : {metrics['threshold']:.2f}")
    print(f"  Genuine Match Rate     : {metrics['genuine_match_rate_pct']:.1f}%  (target >= 85%)")
    print(f"  Impostor Rejection Rate: {metrics['impostor_rejection_rate_pct']:.1f}%  (target >= 95%)")
    print(f"  Avg Genuine Similarity : {metrics['avg_genuine_similarity']}")
    print(f"  Avg Impostor Similarity: {metrics['avg_impostor_similarity']}")
    print()
    print(f"  True Accepts  : {metrics['true_accepts']}")
    print(f"  False Rejects : {metrics['false_rejects']}")
    print(f"  True Rejects  : {metrics['true_rejects']}")
    print(f"  False Accepts : {metrics['false_accepts']}")
    print()
    print(f"  Genuine Retries : {metrics['genuine_retries']} / {metrics['total_genuine_pairs']}")
    print(f"  Impostor Retries: {metrics['impostor_retries']} / {metrics['total_impostor_pairs']}")
    print(f"  Retry Rate      : {metrics['retry_rate_pct']:.1f}%")
    print()

    gmr_ok = metrics['genuine_match_rate_pct'] >= 85.0
    irr_ok = metrics['impostor_rejection_rate_pct'] >= 95.0
    if gmr_ok and irr_ok:
        print("  SUCCESS CRITERIA MET -- Optimization complete.")
    else:
        issues = []
        if not gmr_ok:
            issues.append(f"GMR {metrics['genuine_match_rate_pct']:.1f}% < 85%")
        if not irr_ok:
            issues.append(f"IRR {metrics['impostor_rejection_rate_pct']:.1f}% < 95%")
        print(f"  NOT YET: {', '.join(issues)}")
    print()


def print_pair_details(label, results):
    print(f"\n  {label} pair details:")
    for r in results:
        score_str = f"{r['score']:.4f}" if r['score'] is not None else "N/A"
        status = "RETRY" if r["retry"] else r["decision"]
        print(f"    [{status}] {r['selfie']}  score={score_str}")
        for f in r.get("stage_failures", []):
            print(f"             -> {f}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Biometric Benchmark Runner")
    parser.add_argument("--threshold", type=float, default=0.60, help="Similarity threshold")
    parser.add_argument("--iteration", type=int, default=0, help="Iteration label for output file")
    args = parser.parse_args()

    print_banner(args.iteration)

    # Run genuine pairs
    print("  Running GENUINE pairs ...")
    genuine_results = []
    for selfie in GENUINE_SELFIES:
        print(f"    {os.path.basename(GENUINE_ID)} vs {os.path.basename(selfie)} ... ", end="", flush=True)
        r = run_pair(GENUINE_ID, selfie, args.threshold)
        genuine_results.append(r)
        score_str = f"{r['score']:.4f}" if r['score'] is not None else "N/A"
        print(f"{r['decision']}  (score={score_str})")

    # Run impostor pairs
    print("\n  Running IMPOSTOR pairs ...")
    impostor_results = []
    for selfie in IMPOSTOR_SELFIES:
        print(f"    {os.path.basename(GENUINE_ID)} vs {os.path.basename(selfie)} ... ", end="", flush=True)
        r = run_pair(GENUINE_ID, selfie, args.threshold)
        impostor_results.append(r)
        score_str = f"{r['score']:.4f}" if r['score'] is not None else "N/A"
        print(f"{r['decision']}  (score={score_str})")

    # Compute & display metrics
    metrics = compute_metrics(genuine_results, impostor_results, args.threshold)

    print()
    print("-" * 60)
    print("  METRICS")
    print("-" * 60)
    print_metrics(metrics)

    print_pair_details("Genuine", genuine_results)
    print_pair_details("Impostor", impostor_results)

    # Save JSON report
    out_dir = os.path.join(BASE_DIR, 'results', 'benchmark')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"iteration_{args.iteration:02d}.json")
    report = {
        "iteration": args.iteration,
        "timestamp": datetime.datetime.now().isoformat(),
        "metrics": metrics,
        "genuine_pairs": genuine_results,
        "impostor_pairs": impostor_results,
    }
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Saved benchmark report -> {out_path}\n")
    print("=" * 60)


if __name__ == "__main__":
    main()
