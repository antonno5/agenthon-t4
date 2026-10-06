# V8 Development submission

Submission **964546** was authorized by the user on 2026-10-06 and sent once through the designated account `imak_ai_lab`. Current saved status: **Submitted**. The final score is pending.

- Competition: https://www.codabench.org/competitions/17768/#participate-submit_results
- Phase: Development, 29649.
- Candidate: portable V8 Huber EPS predictor, with V7 deterministic fallbacks for other targets. This is not the V9 rich-history research pipeline.
- Source commit: `b53a9e66dfe994c21c9acdb611d37f7179016467`.
- Published image: `ghcr.io/antonno5/agenthon-t4@sha256:353d99c41736bf82061396a2b5f954dbdc00e9a780134e938f87f6e52a825ca6`.
- Build: https://github.com/antonno5/agenthon-t4/actions/runs/37456110767
- ZIP: `submission-v8-b53a9e6.zip`, SHA-256 `a299abae65f18efbcffb003314db899dbd8030e67ec7d555cd05655cb1201e8a`.
- Model artifact SHA-256: `efe932096f0c1210057a8823f2f536d123c2c93be10be4640ab1ce817bf9f8b9`.
- Full records on cero: `/home/antonnos/agenthon-t4-lab/test-output/submission-v8/`.

The descriptor declares the actual local Huber model in `models[]`. Fitted coefficients use pre-2015 labels; candidate assessment considered outcomes through 2021. The learned predictor therefore runs only for task cutoffs on or after 2022-01-01. Earlier or invalid cutoffs retain the deterministic fallback. Inference makes zero neural calls and uses only the supplied corpus. [Full provenance](V8_PROVENANCE.md).

Validation before upload: 31 tests, 11/11 public structure checks, 11/11 official smoke checks. The published image was pulled anonymously by digest, checked for linux/amd64 and interface 2.0, and produced byte-identical answers to the local image on all 11 public units. The official toolkit packed exactly `submission.json` and `team-claim.json`; the team secret is absent. A receipt prevents duplicate submission POSTs.

The previous actual submission was V6 **963432**, leaderboard score **0.4394002047**, analysis score **0.5585828383**, with 10/10 units admissible. The new score will be compared with this result after evaluation completes.
