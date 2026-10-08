# ruff: noqa: E501
"""Predeclared figure and table inventory (frozen in the protocol before any outcome exists)."""

FIGURES = [
    ("FL10_FIG01", "Ten-round FL architecture", "architecture"), ("FL10_FIG02", "Global training loss versus round", "evolution"),
    ("FL10_FIG03", "Per-client training loss", "evolution"), ("FL10_FIG04", "AUPRC and AUROC evolution (independent holdout)", "evaluation"),
    ("FL10_FIG05", "Threshold-dependent performance R0-R10", "evaluation"), ("FL10_FIG06", "BCE and Brier evolution", "evaluation"),
    ("FL10_FIG07", "ROC curves", "evaluation"), ("FL10_FIG08", "Precision-recall curves", "evaluation"),
    ("FL10_FIG09", "Confusion-matrix comparison", "evaluation"), ("FL10_FIG10", "Predicted-probability distributions", "evaluation"),
    ("FL10_FIG11", "Client-by-round contribution matrix", "federation"), ("FL10_FIG12", "Client-by-round training heatmap", "federation"),
    ("FL10_FIG13", "FedAvg aggregation weights", "federation"), ("FL10_FIG14", "Dataset composition and quality", "data"),
    ("FL10_FIG15", "Participant-level evaluation comparison", "evaluation"), ("FL10_FIG16", "Paired R10 minus R3 effects", "evaluation"),
    ("FL10_FIG17", "Communication and execution evidence", "federation"), ("FL10_FIG18", "Model-state evolution lineage", "federation"),
    ("FL10_FIG19", "Per-batch optimizer diagnostics", "diagnostics"), ("FL10_FIG20", "Final research comparison summary", "evaluation"),
]
TABLES = [
    ("FL10_TAB01", "Full R0-R10 global classification metrics"), ("FL10_TAB02", "R3 versus R10 paired differences"), ("FL10_TAB03", "Full training diagnostics (client x round)"),
    ("FL10_TAB04", "Per-batch diagnostics"), ("FL10_TAB05", "Per-participant independent evaluation (16 participants x 11 states)"), ("FL10_TAB06", "Holdout composition and leakage audit"),
    ("FL10_TAB07", "Federation and aggregation evidence"), ("FL10_TAB08", "Candidate and state lineage"), ("FL10_TAB09", "Metric definitions and undefined-value policy"),
    ("FL10_TAB10", "Synthetic versus scientific evidence boundaries"), ("FL10_TAB11", "Historical exposed-holdout results (continuity only)"), ("FL10_TAB12", "Reproducibility and acceptance matrix"),
]
# metric key -> (definition, undefined condition)
METRIC_DEFINITIONS = {
    "AUPRC": ("average precision = sum_n (R_n - R_{n-1}) P_n (sklearn average_precision_score, non-interpolated)", "needs both classes"),
    "AUROC": ("area under the ROC curve (sklearn roc_auc_score)", "needs both classes"),
    "F1": ("2TP / (2TP + FP + FN), positive class", "2TP+FP+FN = 0"),
    "accuracy": ("(TP+TN) / N", "never undefined for N > 0"),
    "precision": ("TP / (TP+FP) = PPV", "no predicted positives"),
    "recall": ("TP / (TP+FN) = sensitivity = TPR", "no actual positives"),
    "specificity": ("TN / (TN+FP) = TNR", "no actual negatives"),
    "balanced_accuracy": ("(recall + specificity) / 2", "recall or specificity undefined"),
    "negative_predictive_value": ("TN / (TN+FN)", "no predicted negatives"),
    "false_positive_rate": ("FP / (FP+TN)", "no actual negatives"),
    "false_negative_rate": ("FN / (FN+TP)", "no actual positives"),
    "false_discovery_rate": ("FP / (FP+TP) = 1 - precision", "no predicted positives"),
    "false_omission_rate": ("FN / (FN+TN) = 1 - NPV", "no predicted negatives"),
    "MCC": ("(TP*TN - FP*FN) / sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN))", "any marginal total is zero"),
    "BCE": ("mean unweighted binary cross-entropy from raw logits", "never undefined"),
    "Brier": ("mean (sigmoid(logit) - label)^2", "never undefined"),
    "participant_macro_F1": ("mean of per-participant F1 over participants where F1 is defined; the contributing count is reported", "no participant has defined F1"),
}
