"""Read-only audit of event pairing in two existing real LTspice RAW runs."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def distribution(values):
    data = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if not len(data):
        return None
    return {
        "count": int(len(data)), "min": float(np.min(data)),
        "p05": float(np.percentile(data, 5)), "median": float(np.median(data)),
        "mean": float(np.mean(data)), "p95": float(np.percentile(data, 95)),
        "max": float(np.max(data)), "std": float(np.std(data)),
    }


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / "sim/tps61088_v1_4/scripts"))
    from ltspice_raw import load_raw
    from analyze_fsw_internal import crossings

    all_records = []
    run_reviews = {}
    metric_fields = (
        "period_ns", "sw_high_ns", "sw_rise_to_cap_cross_ns",
        "comparator_minus_cap_cross_ns", "toff_minus_comparator_ns",
        "toff_minus_cap_cross_ns", "gate_minus_toff_ns",
        "reset_minus_gate_ns", "sw_fall_minus_cap_cross_ns",
        "sw_fall_minus_comparator_ns", "sw_fall_minus_toff_ns",
        "sw_fall_minus_gate_ns", "sw_fall_minus_cap_reset_ns",
        "rc_ode_prediction_residual_ns",
    )

    for step in (50, 25):
        result_dir = root / f"sim/tps61088_v1_4/results/fsw_internal_probe_{step}ns"
        summary_path = result_dir / "fsw_internal_summary.json"
        cycles_path = result_dir / "fsw_internal_cycles.csv"
        original = json.loads(summary_path.read_text(encoding="utf-8"))
        with cycles_path.open(encoding="utf-8", newline="") as f:
            original_rows = list(csv.DictReader(f))
        raw_path = Path(original["raw_path"])
        _, names, raw = load_raw(raw_path)
        idx = {name.lower(): i for i, name in enumerate(names)}
        time_full = raw[:, idx["time"]]
        start, end = original["analysis_window_s"]
        first, last = np.searchsorted(time_full, [start, end])
        first = max(0, first - 1)
        last = min(len(time_full), last + 1)
        t = np.array(time_full[first:last])

        def vector(name):
            return np.array(raw[first:last, idx[name]])

        cap = vector("v(x1:u5_n01584)")
        pvin = vector("v(x1:u5_pvin)")
        comparator = vector("v(x1:u5_n16903113)")
        cap_minus_pvin = cap - pvin
        events = {
            "cap_cross": crossings(t, cap_minus_pvin, 0.0, "rise"),
            "comparator": crossings(t, comparator, 0.5, "rise"),
            "toff": crossings(t, vector("v(x1:u5_toff)"), 0.5, "rise"),
            "gate": crossings(t, vector("v(x1:gate_l)"), 0.5, "rise"),
            "reset": crossings(t, cap, 0.5, "fall"),
            "sw_fall": crossings(t, vector("v(sw)"), 10.0, "fall"),
        }
        records = []
        for original_row in original_rows:
            if not original_row["next_cycle_start_s"]:
                continue
            up = float(original_row["cycle_start_s"])
            next_up = float(original_row["next_cycle_start_s"])
            selected_events = {}
            record = {
                "max_step_ns": step, "cycle_start_s": up,
                "next_cycle_start_s": next_up,
                "original_cycle_status": original_row["cycle_status"],
                "original_invalid_reason": original_row["invalid_reason"],
                "period_ns": (next_up - up) * 1e9,
            }
            for name, times in events.items():
                left = int(np.searchsorted(times, up, side="left"))
                right = int(np.searchsorted(times, next_up, side="left"))
                count = right - left
                record[name + "_count"] = count
                selected_events[name] = float(times[left]) if count == 1 else None
                record[name + "_event_s"] = selected_events[name]

            def delta(later, earlier):
                return (later - earlier) * 1e9 if later is not None and earlier is not None else None

            cross = selected_events["cap_cross"]
            comp = selected_events["comparator"]
            toff = selected_events["toff"]
            gate = selected_events["gate"]
            reset = selected_events["reset"]
            fall = selected_events["sw_fall"]
            record.update({
                "sw_high_ns": delta(fall, up),
                "sw_rise_to_cap_cross_ns": delta(cross, up),
                "comparator_minus_cap_cross_ns": delta(comp, cross),
                "toff_minus_comparator_ns": delta(toff, comp),
                "toff_minus_cap_cross_ns": delta(toff, cross),
                "gate_minus_toff_ns": delta(gate, toff),
                "reset_minus_gate_ns": delta(reset, gate),
                "sw_fall_minus_cap_cross_ns": delta(fall, cross),
                "sw_fall_minus_comparator_ns": delta(fall, comp),
                "sw_fall_minus_toff_ns": delta(fall, toff),
                "sw_fall_minus_gate_ns": delta(fall, gate),
                "sw_fall_minus_cap_reset_ns": delta(fall, reset),
                "rc_ode_prediction_residual_ns": (
                    float(original_row["rc_ode_prediction_residual_s"]) * 1e9
                    if original_row["rc_ode_prediction_residual_s"] else None
                ),
                "cap_cross_matches_original": (
                    cross is not None and abs(cross - float(original_row["pvin_cross_s"])) < 1e-15
                ),
            })
            if cross is not None and comp is not None:
                cap_index = int(np.searchsorted(t, cross))
                comp_index = int(np.searchsorted(t, comp))
                record.update({
                    "comparator_minus_cap_bracket_index": comp_index - cap_index,
                    "same_raw_sample_bracket": comp_index == cap_index,
                    "cap_cross_bracket_start_s": float(t[cap_index - 1]),
                    "cap_cross_bracket_end_s": float(t[cap_index]),
                    "cap_cross_bracket_width_ns": float((t[cap_index] - t[cap_index - 1]) * 1e9),
                    "cap_minus_pvin_bracket_start_V": float(cap_minus_pvin[cap_index - 1]),
                    "cap_minus_pvin_bracket_end_V": float(cap_minus_pvin[cap_index]),
                    "comparator_at_cap_bracket_start_V": float(comparator[cap_index - 1]),
                    "comparator_at_cap_bracket_end_V": float(comparator[cap_index]),
                })
            records.append(record)

        invalid = [record for record in records if record["original_cycle_status"] == "invalid"]
        valid = [record for record in records if record["original_cycle_status"] == "complete"]
        per_event_counts = {
            name: dict(sorted(collections.Counter(record[name + "_count"] for record in records).items()))
            for name in events
        }
        run_reviews[str(step)] = {
            "raw_path": str(raw_path), "raw_size_bytes": raw_path.stat().st_size,
            "original_summary_path": str(summary_path),
            "original_summary_sha256": sha256_file(summary_path),
            "original_cycles_sha256": sha256_file(cycles_path),
            "original_cycle_accounting": original["cycle_accounting"],
            "complete_sw_periods_reviewed": len(records),
            "right_censored_original_rows_excluded": len(original_rows) - len(records),
            "event_count_histograms_per_complete_period": per_event_counts,
            "all_cap_crosses_match_original": all(record["cap_cross_matches_original"] for record in records),
            "negative_comparator_minus_cap_cross_count": sum(
                record["comparator_minus_cap_cross_ns"] < 0 for record in records
                if record["comparator_minus_cap_cross_ns"] is not None
            ),
            "invalid_same_raw_sample_bracket_count": sum(record.get("same_raw_sample_bracket", False) for record in invalid),
            "invalid_bracket_index_delta_histogram": dict(sorted(collections.Counter(
                record.get("comparator_minus_cap_bracket_index") for record in invalid
            ).items())),
            "invalid_cap_cross_bracket_width_ns": distribution([
                record.get("cap_cross_bracket_width_ns") for record in invalid
            ]),
            "original_valid_subset_fraction_of_complete_sw_periods": len(valid) / len(records),
            "all_complete_period_statistics": {field: distribution([record[field] for record in records]) for field in metric_fields},
            "original_valid_subset_statistics": {field: distribution([record[field] for record in valid]) for field in metric_fields},
            "original_invalid_subset_statistics": {field: distribution([record[field] for record in invalid]) for field in metric_fields},
            "invalid_bracket_examples": invalid[:3],
        }
        all_records.extend(records)

    review = {
        "scope": "Read-only independent audit of existing real RAW and original analyzer outputs; no circuit, threshold, edge index, or original result files modified.",
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__)),
        "event_selection": "Count every event independently inside each original complete SW period [rise,next_rise); record signed offsets without imposing a causal order or changing the original valid subset.",
        "runs": run_reviews,
        "interpretation_zh": [
            "每个完整SW周期内独立统计比较器、TOFF、GATE_L、复位及SW下降阈值事件；不修改原始summary/cycles或原valid判定。",
            "原脚本要求比较器0.5V插值交点不早于cap-PVIN插值交点；负的有符号时差导致比较器配对失败，TOFF缺失为下游配对失败。独立周期内事件存在性应以计数为准。",
            "两交点同处一对相邻RAW样本时，分别线性插值不能解析其连续时间因果先后。不能把原invalid数量写成真实漏脉冲、实际内部事件缺失或模型故障。",
            "50ns与25ns的原valid子集纳入比例不同；原comparison的valid-only统计存在选择偏差，不能把全部分布差异直接归因于求解精度。",
            "本复核的完整周期统计仅为独立补充说明，不追认原invalid周期为已验证因果顺序正确，也不修改原始有效子集。",
            "仅两档最大步长不足以证明内部延迟已收敛、采样内物理先后、内部时间链残差已闭合或频偏唯一根因。",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "internal_probe_pairing_review.json"
    csv_path = args.out_dir / "internal_probe_pairing_review.csv"
    json_path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_records[0]))
        writer.writeheader()
        writer.writerows(all_records)
    print(json.dumps({"json": str(json_path.resolve()), "csv": str(csv_path.resolve()), "rows": len(all_records)}, indent=2))


if __name__ == "__main__":
    main()
