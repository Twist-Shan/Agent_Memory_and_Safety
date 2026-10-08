"""Optional grouped linear-probe baseline. Model selection uses validation only."""

import json
import hashlib
import importlib.metadata
from pathlib import Path


def fit_probe(manifest, output, label="authorized_target"):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    rows = [json.loads(line) for line in Path(manifest).read_text(encoding="utf-8").splitlines() if line]
    seen = {}
    for row in rows:
        if row["base_id"] in seen and seen[row["base_id"]] != row["split"]:
            raise ValueError("Base-instance leakage across splits")
        seen[row["base_id"]] = row["split"]
    x = np.stack([np.load(Path(manifest).parent / r["activation_file"], allow_pickle=False)["activations"] for r in rows])
    y = np.array([r["labels"][label] for r in rows])
    masks = {s: np.array([r["split"] == s for r in rows]) for s in ("train", "validation", "test")}
    if any(len(set(y[m])) != 2 for m in masks.values()):
        raise ValueError("Each split needs both classes; increase independently generated base instances")
    best = None
    for layer in range(x.shape[1]):
        for c in (0.01, 0.1, 1.0, 10.0):
            model = make_pipeline(StandardScaler(), LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=17))
            model.fit(x[masks["train"], layer], y[masks["train"]])
            score = balanced_accuracy_score(y[masks["validation"]], model.predict(x[masks["validation"], layer]))
            if best is None or score > best[0]:
                best = (score, layer, c, model)
    val_score, layer, c, model = best
    mask = masks["test"]
    pred = model.predict(x[mask, layer])
    prob = model.predict_proba(x[mask, layer])[:, 1]
    report = {"label": label, "layer": layer, "C": c, "validation_balanced_accuracy": val_score,
        "test_balanced_accuracy": balanced_accuracy_score(y[mask], pred),
        "test_auroc": roc_auc_score(y[mask], prob),
        "counts": {s: {"checkpoints": int(m.sum()), "bases": len({r["base_id"] for r, keep in zip(rows, m) if keep})} for s, m in masks.items()},
        "test_accuracy_by_condition": {}}
    report["manifest_sha256"] = hashlib.sha256(Path(manifest).read_bytes()).hexdigest()
    report["software"] = {name: importlib.metadata.version(name) for name in ("numpy", "scikit-learn", "scipy")}
    test_rows = [r for r, keep in zip(rows, mask) if keep]
    for condition in sorted({r["condition"] for r in test_rows}):
        selected = np.array([r["condition"] == condition for r in test_rows])
        report["test_accuracy_by_condition"][condition] = {"n": int(selected.sum()),
            "accuracy": accuracy_score(y[mask][selected], pred[selected])}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    scaler, clf = model.steps[0][1], model.steps[1][1]
    direction = clf.coef_[0] / scaler.scale_
    np.save(out / "direction.npy", direction)
    np.savez(out / "probe.npz", direction=direction,
             intercept=clf.intercept_[0] - np.dot(direction, scaler.mean_), layer=layer)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
