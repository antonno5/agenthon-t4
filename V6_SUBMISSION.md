# V6 diagnostic Development submission

Submission: **963432**. Current recorded status: **Submitted**. Score pending; no result is available yet.

- Competition: https://www.codabench.org/competitions/17768/
- Account: imak_ai_lab; phase: Development (29649).
- Source commit: `e9b7ed3bf8f5152c791d11375ff100caa98d4f24`.
- Image: `ghcr.io/antonno5/agenthon-t4@sha256:c8c1070b27830157a5ad00479bfb984943fc6760ada1d732d696ce9f06c023f1`.
- Build: https://github.com/antonno5/agenthon-t4/actions/runs/37396851070
- ZIP SHA-256: `6e94938bb02593f185f2f879b265e47e9eee1918d9c6e560a28c73c99c929ab4`.
- Artifacts on cero: `test-output/submission-v6/`.

The user explicitly authorized this diagnostic upload after the laboratory gate had
remained closed. This upload tests a corpus-only deterministic adaptation. It does
not deploy the laboratory Ridge model: the official rate snapshots do not contain
enough completed windows to fit it, and no external fitted artifact was imported.

Validation: six unit tests, all eleven public tasks, all eleven official smoke checks,
anonymous pull by digest, linux/amd64 and interface 2.0. The published image produced
byte-identical answers to the locally smoke-checked answers. Neural calls: zero.

The official toolkit 2.5.1 packed exactly submission.json and team-claim.json. The
Team Key is absent from the ZIP and image. A preliminary dataset-creation request
returned HTTP 500 before creating any submission. After matching the current web
uploader's competition/file metadata, one submission was created. Its receipt blocks
accidental duplicate POSTs.

The previous best V1 score was 0.1387778252. Scoring rules changed since those September
submissions, so a new numerical score alone is not a clean measurement of improvement.
The per-unit report and scoring version must be considered.

Algorithm/provenance: [V6_PROVENANCE.md](V6_PROVENANCE.md).
