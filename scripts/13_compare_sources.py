"""Which data combination best predicts the measured neighbourhood heat pattern?

    python scripts/13_compare_sources.py

Truth is the MODIS land-surface-temperature anomaly on the zones the satellite
actually observed. Each candidate predicts zones it has not seen:

    0  every zone = the city average           (the do-nothing baseline)
    A  the OpenStreetMap formula               (the method satellite replaced)
    B  OpenStreetMap features, fitted to satellite
    C  mean of measured satellite neighbours   (the gap fill script 12 uses)
    D  C + OpenStreetMap features, fused

Cross-validation holds out whole H3 res-6 districts at a time (DECISIONS D13),
so a zone's neighbours cannot leak its answer into training. A second pass
leaves one zone out at a time, which is the real gap-filling job: a handful of
scattered zones with measured neighbours all round.

This is the evidence behind using OpenStreetMap to DESCRIBE zones but not to
LOCATE heat. It measures the pattern only -- the surface-to-air coefficient
alpha is untouched by it and still assumed. numpy + scipy only.
"""
import json
import sys
from pathlib import Path

import h3
import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("roads", "green", "water", "built")
N_FOLDS = 5
TOP_N = 40


def ridge(Xtr, ytr, Xte, lam=1.0):
    """Closed-form ridge on standardised features; intercept unpenalised."""
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A = np.column_stack([np.ones(len(Xtr)), (Xtr - mu) / sd])
    penalty = lam * np.diag([0.0] + [1.0] * (A.shape[1] - 1))
    w = np.linalg.solve(A.T @ A + penalty, A.T @ ytr)
    return np.column_stack([np.ones(len(Xte)), (Xte - mu) / sd]) @ w


def grouped_folds(groups, k=N_FOLDS):
    """Assign whole districts to folds, largest first, to balance fold sizes."""
    sizes = {}
    for g in groups:
        sizes[g] = sizes.get(g, 0) + 1
    fold_of, load = {}, [0] * k
    for g in sorted(sizes, key=sizes.get, reverse=True):
        j = int(np.argmin(load))
        fold_of[g] = j
        load[j] += sizes[g]
    return np.array([fold_of[g] for g in groups]), len(sizes)


def main(slug: str = "ahmedabad") -> None:
    processed = ROOT / "data" / "processed"
    osm = json.loads((processed / f"urban_form_{slug}.json").read_text("utf-8"))["cells"]
    lst = json.loads((processed / f"urban_form_lst_{slug}.json").read_text("utf-8"))["cells"]

    cells = [c for c in lst if lst[c]["provenance"] != "filled_neighbour" and c in osm]
    n = len(cells)
    idx = {c: i for i, c in enumerate(cells)}
    y = np.array([lst[c]["lst_anomaly_c"] for c in cells])
    F = np.array([[osm[c][k] for k in FEATURES] for c in cells])
    osm_formula = np.array([osm[c]["d_ta_c"] for c in cells])
    folds, n_districts = grouped_folds([h3.cell_to_parent(c, 6) for c in cells])

    def neighbour_mean(i, known):
        for ring in (1, 2, 3):
            nb = [idx[c] for c in h3.grid_disk(cells[i], ring)
                  if c in idx and known[idx[c]] and idx[c] != i]
            if nb:
                return y[nb].mean()
        return np.nan

    def fused(tr, te):
        nb_tr = np.array([neighbour_mean(i, tr) for i in np.where(tr)[0]])
        nb_te = np.array([neighbour_mean(i, tr) for i in np.where(te)[0]])
        fill = np.nanmean(nb_tr)
        Xtr = np.column_stack([F[tr], np.where(np.isfinite(nb_tr), nb_tr, fill)])
        Xte = np.column_stack([F[te], np.where(np.isfinite(nb_te), nb_te, fill)])
        return ridge(Xtr, y[tr], Xte)

    candidates = [
        ("0  city average everywhere", lambda tr, te: np.zeros(te.sum())),
        ("A  OpenStreetMap formula",
         lambda tr, te: ridge(osm_formula[tr, None], y[tr], osm_formula[te, None], lam=0.0)),
        ("B  OSM features, fitted", lambda tr, te: ridge(F[tr], y[tr], F[te])),
        ("C  satellite neighbours",
         lambda tr, te: np.array([neighbour_mean(i, tr) for i in np.where(te)[0]])),
        ("D  neighbours + OSM (fused)", fused),
    ]

    print(f"{n} observed zones, {n_districts} districts, {N_FOLDS} grouped folds\n")
    print(f"{'candidate':32s} {'error':>8s} {'rank':>7s} {'hottest-' + str(TOP_N):>11s} {'coverage':>9s}")
    top_true = set(np.argsort(-y)[:TOP_N])
    for name, predict in candidates:
        pred = np.full(n, np.nan)
        for k in range(N_FOLDS):
            te = folds == k
            pred[te] = predict(~te, te)
        ok = np.isfinite(pred)
        mae = np.abs(pred[ok] - y[ok]).mean()
        # A constant prediction has no rank; report it as such, not as NaN noise.
        rho = spearmanr(pred[ok], y[ok])[0] if np.ptp(pred[ok]) > 0 else float("nan")
        found = len(top_true & set(np.argsort(-np.where(ok, pred, -1e9))[:TOP_N]))
        rank = "   n/a" if np.isnan(rho) else f"{rho:+.2f}"
        hits = "  n/a" if np.isnan(rho) else f"{found:2d}/{TOP_N}"
        print(f"{name:32s} {mae:6.2f} C {rank:>7s} {hits:>11s} {ok.mean():8.0%}")

    print("\nLeave one zone out (the real gap-filling job):")
    everyone = np.ones(n, bool)
    nb_all = np.array([neighbour_mean(i, everyone) for i in range(n)])
    X = np.column_stack([F, nb_all])
    for name, pred in (
        ("C  satellite neighbours", nb_all),
        ("D  neighbours + OSM (fused)",
         np.array([ridge(np.delete(X, i, 0), np.delete(y, i), X[i:i + 1])[0] for i in range(n)])),
    ):
        ok = np.isfinite(pred)
        print(f"{name:32s} {np.abs(pred[ok] - y[ok]).mean():6.2f} C "
              f"{spearmanr(pred[ok], y[ok])[0]:+7.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ahmedabad")
