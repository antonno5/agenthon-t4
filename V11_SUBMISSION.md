# V11 diagnostic submission

Submission **965395** was explicitly authorized and submitted once on 2026-10-06 through the designated `imak_ai_lab` account. Initial platform status: Submitting. The full-track research gate had not passed; this is the diagnostic upload the user requested after that result.

- Competition: https://www.codabench.org/competitions/17768/#participate-submit_results
- Source commit: `753007d6d64a94961adb0e655412d8ecb3bdced0`.
- Image: `ghcr.io/antonno5/agenthon-t4@sha256:b6a841f95515f217e6b9fff421191f95e228d8e1d5e1594b9c6da1c3c226c22a`.
- Build: https://github.com/antonno5/agenthon-t4/actions/runs/37507184581
- ZIP SHA256: `77c46ed188f82a73069c03e5164d0b5e38f277c7d7e921ec7285da887c636b2a`.
- Previous actual V8 submission: 964546, leaderboard 0.4755418836, analysis 0.5870408532.

V11 changes only CPI. The 2017-frozen CPI models, selector and interval calibration use no 2017–2021 confirmation targets. Other task outputs remain byte-identical to V8. The inherited EPS model and its 2022 cutoff guard are unchanged.

Validation: six new numerical/input tests; 11/11 public schema/structure/exact-quote checks; 11/11 official non-rankable smoke checks; linux/amd64 image verification; anonymous pull by digest; 11/11 published-image answers identical to local answers. The official toolkit packed the two declared model artifacts into a descriptor and team claim, with no team key in the ZIP.

Cero again accepted TCP connections but did not send an SSH banner. Publication therefore used the existing local GitHub SSH identity and GitHub Actions; CodaBench authentication/upload used the authorized local handoff file. Credentials and cookies remain outside version control. No production service was restarted.

Local audit artifacts: `test-output/submission-v11/`. The upload receipt prevents a duplicate POST. Waiting for platform evaluation; no score or rank improvement is claimed yet.
