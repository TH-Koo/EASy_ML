"""Run with `python -m fides_ml --help` from the EASy repository root."""
from __future__ import annotations

import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Fides stage 1: learn contextual weights; AnalysisEngine owns ACCS/verdict")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Rescore existing evidence caches and attach reference ordinal labels")
    p.add_argument("--labels", required=True)
    p.add_argument("--output", required=True)
    sources = p.add_mutually_exclusive_group(required=True)
    sources.add_argument("--cache-dir")
    sources.add_argument("--results", help="JSON/JSONL AnalysisResult snapshots with URL")
    sources.add_argument("--seller-only", action="store_true", help="Explicitly incomplete offline input for execution checks")
    p.add_argument("--ontology-dir", default="ontology")
    p.add_argument("--groups", help="Reviewed CSV with url and base_model_id/split_group")
    p.add_argument("--group-column", help="Explicit grouping column; product_type gives a stricter category holdout")
    p = sub.add_parser("train", help="Train on Washing/Suspicious/Genuine intervals, validate, then evaluate test once")
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode", choices=["fixed", "global", "cen", "cen_senn"], default="cen_senn")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--patience", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--learning-rate", type=float, default=.001)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cpu", help="cpu | cuda | auto")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--hidden-dim", type=int, default=32)
    p.add_argument("--prototypes", type=int, default=4)
    p.add_argument("--ecs-alpha", type=float, default=.15)
    p.add_argument("--washing-cutoff", type=float, default=21.8)
    p.add_argument("--genuine-cutoff", type=float, default=35.0)
    p.add_argument("--credible-cutoff", type=float, default=67.5)
    p.add_argument("--temperature", type=float, default=5.0)
    p.add_argument("--lambda-senn", type=float, default=.1)
    p.add_argument("--lambda-prior", type=float, default=.005)
    p.add_argument("--lambda-weight-stability", type=float, default=.01)
    p.add_argument("--no-balanced", action="store_true")
    p = sub.add_parser("predict-weights", help="Write weights and model metadata only; no ACCS or verdict")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--device", default="cpu")
    p = sub.add_parser("demo-data", help="Generate clearly labeled synthetic execution-check data")
    p.add_argument("--output", required=True)
    p.add_argument("--groups", type=int, default=180)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            from .prepare import prepare_dataset
            result = prepare_dataset(args.labels, args.output, cache_dir=args.cache_dir, results_path=args.results,
                                     seller_only=args.seller_only, ontology_dir=args.ontology_dir,
                                     groups_path=args.groups, group_column=args.group_column)
        elif args.command == "train":
            from .train import TrainConfig, train_model
            config = TrainConfig(epochs=args.epochs, batch_size=args.batch_size, learning_rate=args.learning_rate,
                                 patience=args.patience, seed=args.seed, device=args.device, threads=args.threads,
                                 lambda_senn=args.lambda_senn, lambda_prior=args.lambda_prior,
                                 lambda_weight_stability=args.lambda_weight_stability, balanced=not args.no_balanced)
            options = {k: getattr(args, k) for k in ("mode", "hidden_dim", "prototypes", "ecs_alpha", "washing_cutoff",
                        "genuine_cutoff", "credible_cutoff", "temperature")}
            full = train_model(args.data, args.output, options, config)
            result = {"output": args.output, "best_epoch": full["best_epoch"], "test": full["splits"]["test"]}
        elif args.command == "predict-weights":
            from .predict import WeightPredictor
            result_frame = WeightPredictor(args.checkpoint, args.device).predict_csv(args.data, args.output)
            result = {"output": args.output, "rows": len(result_frame)}
        else:
            from .demo import make_demo
            result = make_demo(args.output, args.groups)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
