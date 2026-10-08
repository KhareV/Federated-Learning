**Metric definitions and undefined-value policy**

| metric | definition | undefined_when | implementation |
|---|---|---|---|
| AUPRC | average precision = sum_n (R_n - R_{n-1}) P_n (sklearn average_precision_score, non-interpolated) | needs both classes | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| AUROC | area under the ROC curve (sklearn roc_auc_score) | needs both classes | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| F1 | 2TP / (2TP + FP + FN), positive class | 2TP+FP+FN = 0 | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| accuracy | (TP+TN) / N | never undefined for N > 0 | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| precision | TP / (TP+FP) = PPV | no predicted positives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| recall | TP / (TP+FN) = sensitivity = TPR | no actual positives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| specificity | TN / (TN+FP) = TNR | no actual negatives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| balanced_accuracy | (recall + specificity) / 2 | recall or specificity undefined | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| negative_predictive_value | TN / (TN+FN) | no predicted negatives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| false_positive_rate | FP / (FP+TN) | no actual negatives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| false_negative_rate | FN / (FN+TP) | no actual positives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| false_discovery_rate | FP / (FP+TP) = 1 - precision | no predicted positives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| false_omission_rate | FN / (FN+TN) = 1 - NPV | no predicted negatives | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| MCC | (TP*TN - FP*FN) / sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN)) | any marginal total is zero | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| BCE | mean unweighted binary cross-entropy from raw logits | never undefined | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| Brier | mean (sigmoid(logit) - label)^2 | never undefined | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |
| participant_macro_F1 | mean of per-participant F1 over participants where F1 is defined; the contributing count is reported | no participant has defined F1 | final_showcase.metrics + fl10.metrics (scikit-learn average_precision_score / roc_auc_score where applicable) |

*Metric equations and undefined-value policy (fixed in the protocol).*
