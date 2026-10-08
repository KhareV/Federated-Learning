# Viva question bank

**Q1. Why is the federated result not called better than centralized?**

Only point values exist for the centralized reference (0.999473 / 0.970004); differences of -0.000542 and +0.006600 have opposite signs, no paired interval, different training budgets and exposed datasets.

**Q2. What does 'frozen' mean here?**

Artifacts are hash-verified before display; locks and historical evidence are never edited. New work is additive successor material.

**Q3. Why does the synthetic round-3 model predict everything positive?**

At the fixed 0.5 threshold its recall is 1.0000 and specificity 0.0000. Threshold-free AUPRC/AUROC improved (0.6355→0.6953, 0.7382→0.8135), so ranking improved but the uncalibrated operating point is poor. We did not tune the threshold or retrain, by protocol.

**Q4. Is the synthetic evaluation clinical validation?**

No. It is labelled 'SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION'.

**Q5. How do you know the holdout did not leak?**

Participant, session, seed and window-input disjointness are checked and tested; a changed label, hash or protocol aborts the run.

**Q6. Why was the protocol committed first?**

A two-commit method-freeze/result sequence (method freeze 6d79274c0c) prevents choosing methods after seeing results.

**Q7. Is the live-monitored participant different from the synthetic one?**

The windows come from a genuine monitoring-runtime session; the generator is the same, so the dataset is identical to canonical (observed: True). The candidate digest equality (True) is a measured consequence.

**Q8. Does raw data leave clients?**

No; only updates, digests and example counts reach the coordinator (client-data-locality audit).

**Q9. Why are no p-values reported?**

Patient-cluster counts are small (6 and 32 for the scientific sets, 8 for synthetic); only nominal percentile intervals are reported.

**Q10. What would strengthen the comparison?**

A designed paired experiment with matched budgets and held-out clusters; independent hardware data is out of scope and not authorised.
