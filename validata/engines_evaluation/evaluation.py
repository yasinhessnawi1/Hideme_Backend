"""
compare_results.py

Compares all engines’ flat JSON outputs against the manual labels using
partial‐substring matching across all entities. Generates:
  1) A single detailed report (all_engines_report.txt) including:
       - Explanation of evaluation method and comparison base
       - Legend for table symbols
       - Full tables of stats per entity (only entities detected) for each engine
         * includes a Totals row per engine with aggregate P, P%, FP_OR_NI, FP_OR_NI%
       - Top 5 entities by positive match rate per engine
       - Summary across engines: ranking by overall P% detection
  2) Individual diagrams for each engine, named <engine>_diagram.png,
     showing stacked P% vs FP_OR_NI% per detected entity.

Requirements:
    - python-dotenv
    - matplotlib
"""
import os
import json
from dotenv import load_dotenv
import matplotlib.pyplot as plt

# Load environment and file paths
load_dotenv()
ENGINES = {
    "gemini": os.getenv("PATH_FILE_GEMINI"),
    "gliner": os.getenv("PATH_FILE_GLINER"),
    "hideme": os.getenv("PATH_FILE_HIDEME"),
    "presidio": os.getenv("PATH_FILE_PRESIDIO"),
    "private": os.getenv("PATH_FILE_PRIVATE"),
}
MANUAL_PATH = os.getenv("PATH_FILE_MANUAL")

if not MANUAL_PATH or any(p is None for p in ENGINES.values()):
    raise RuntimeError("Please set PATH_FILE_<engine> and PATH_FILE_MANUAL in your .env file.")

# Load manual labels for comparison (lowercased)

with open(MANUAL_PATH, "r", encoding="utf-8") as manual_file:
    manual_records = json.load(manual_file)

# Build a list of all manually labeled strings (lowercased) for substring matching
manual_texts = [rec.get("sensitive", "").lower() for rec in manual_records]


def analyze_engine(file_labeling_path):
    """
    Load one engine's JSON output and compare each 'sensitive' text
    to manual_texts via partial-substring matching.

    Returns:
        dict mapping entity -> {
            total:       int, number of hits
            positive:    int, matches to manual
            negative:    int, misses (FP or not included)
            p_pct:       float, positive / total * 100
            fp_pct:      float, negative / total * 100
        }
    """
    # Read engine output
    with open(file_labeling_path, "r", encoding="utf-8") as input_file:
        records = json.load(input_file)

    entity_stats = {}
    # Count totals/positives/negatives per entity
    for record in records:
        entity = record.get("entity")
        text = record.get("sensitive", "").lower()
        entity_stats.setdefault(entity, {"total": 0, "positive": 0, "negative": 0})
        entity_stats[entity]["total"] += 1

        # If any manual text contains or is contained by this hit → positive
        if any(m in text or text in m for m in manual_texts):
            entity_stats[entity]["positive"] += 1
        else:
            entity_stats[entity]["negative"] += 1

    # Compute percentages
    for stats in entity_stats.values():
        total = stats["total"] or 1
        stats["p_pct"] = stats["positive"] / total * 100
        stats["fp_pct"] = stats["negative"] / total * 100

    return entity_stats


def write_report_and_collect(engine_stats_map):
    """
    Writes a unified text report, and at the same time
    collects the plotting data per engine.

    Returns:
        dict: {
            engine_name: (
                [list of detected entities],
                [list of corresponding P%],
                [list of FP_OR_NI%]
            )
        }
    """
    report_path = "all_engines_report.txt"
    plotting_data = {}
    summary_totals = {}

    with open(report_path, 'w', encoding='utf-8') as rpt:
        # Write evaluation overview
        rpt.write("Evaluation method:\n")
        rpt.write("  Partial-substring matching: count positive if any substring match.\n\n")
        rpt.write("Comparison base:\n")
        rpt.write("  Manual labels (lowercased) loaded from JSON, compared to engine outputs.\n\n")
        rpt.write("Legend:\n")
        rpt.write("  Total     - total hits by engine.\n")
        rpt.write("  P         - positives (matched manual).\n")
        rpt.write("  P%        - % positives.\n")
        rpt.write("  FP_OR_NI  - false positives or not manually included.\n")
        rpt.write("  FP_OR_NI% - % false positives.\n\n")

        # Per-engine section
        for engine_name, entity_stats in engine_stats_map.items():
            rpt.write(f"==== {engine_name.upper()} ====\n")
            rpt.write(f"{'Entity':30} {'Total':>8} {'P':>8} {'P%':>8} {'FP_OR_NI':>16} {'FP_OR_NI%':>10}\n")
            rpt.write("-" * 80 + "\n")

            # Filter to only entities with at least one hit
            detected = [(e, s) for e, s in entity_stats.items() if s["total"] > 0]

            # Compute engine-wide sums
            total_hits = sum(s["total"] for _, s in detected)
            total_positive = sum(s["positive"] for _, s in detected)
            total_negative = sum(s["negative"] for _, s in detected)
            overall_p_pct = (total_positive / total_hits * 100) if total_hits else 0.0
            overall_fp_pct = (total_negative / total_hits * 100) if total_hits else 0.0

            # Write each entity row
            for entity, stats in sorted(detected):
                rpt.write(
                    f"{entity:30} "
                    f"{stats['total']:8d} "
                    f"{stats['positive']:8d} "
                    f"{stats['p_pct']:8.2f}% "
                    f"{stats['negative']:12d} "
                    f"{stats['fp_pct']:10.2f}%\n"
                )

            # Totals row
            rpt.write("-" * 80 + "\n")
            rpt.write(
                f"{'Totals':30} "
                f"{total_hits:8d} "
                f"{total_positive:8d} "
                f"{overall_p_pct:8.2f}% "
                f"{total_negative:12d} "
                f"{overall_fp_pct:10.2f}%\n"
            )
            rpt.write("\n")

            # Top 5 entities by P%
            rpt.write("Top 5 entities by positive rate:\n")
            top5 = sorted(detected, key=lambda item: item[1]["p_pct"], reverse=True)[:5]
            for entity, stats in top5:
                rpt.write(f"  - {entity}: {stats['p_pct']:.2f}%\n")
            rpt.write("\n")

            # Save per-engine plotting data
            entities = [e for e, _ in sorted(detected)]
            p_percents = [s["p_pct"] for _, s in sorted(detected)]
            fp_percents = [s["fp_pct"] for _, s in sorted(detected)]
            plotting_data[engine_name] = (entities, p_percents, fp_percents)

            # Track for overall ranking
            summary_totals[engine_name] = (total_positive, total_hits)

        # Overall summary: rank engines by their aggregate positive %
        rpt.write("==== OVERALL SUMMARY ====\n")
        engine_rates = [
            (eng, pos / tot * 100 if tot else 0.0)
            for eng, (pos, tot) in summary_totals.items()
        ]
        # Sort descending
        for rank, (eng, rate) in enumerate(sorted(engine_rates, key=lambda x: x[1], reverse=True), 1):
            rpt.write(f"  {rank}. {eng}: {rate:.2f}% overall positive\n")

    return plotting_data


def generate_individual_diagrams(plotting_data):
    """
    For each engine, generate a standalone bar chart
    of P% vs FP_OR_NI% across its detected entities.
    """
    for engine_name, (entities, positives, negatives) in plotting_data.items():
        x_positions = range(len(entities))
        plt.figure(figsize=(max(8, len(entities) * 0.5), 6))

        # Draw P% bars
        plt.bar(x_positions, positives, label="P%", alpha=0.8)
        # Stack FP_OR_NI% on top
        plt.bar(x_positions, negatives, bottom=positives, label="FP_OR_NI%", alpha=0.5)

        # Labeling
        plt.xticks(x_positions, entities, rotation=60, ha="right")
        plt.ylabel("Percentage")
        plt.title(f"{engine_name.capitalize()} — Entity P% vs FP_OR_NI%")
        plt.legend()
        plt.tight_layout()

        # Save per-engine image
        plt.savefig(f"{engine_name}_diagram.png")
        plt.close()


if __name__ == "__main__":
    # Analyze each engine
    engine_stats = {}
    for eng_name, file_path in ENGINES.items():
        if not os.path.exists(file_path):
            print(f" {eng_name}: file not found at {file_path!r}")
            continue
        engine_stats[eng_name] = analyze_engine(file_path)

    # Write the unified report & collect plotting data
    plot_data = write_report_and_collect(engine_stats)

    # Generate one PNG per engine
    generate_individual_diagrams(plot_data)

    print("Unified report and individual diagrams generated.")
