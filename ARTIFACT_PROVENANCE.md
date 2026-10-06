# Current V6 diagnostic

For Dockerfile.v6, the authoritative record is [V6_PROVENANCE.md](V6_PROVENANCE.md). It uses no House calls or offline-fitted models. The historical V2–V5 record below applies only to those earlier images.

# Track 4 V2/V3/V4 artifact provenance

The V2 image contains Python source, a deterministic BM25 index built at runtime
from the supplied official frozen corpus, and the Python 3.13 standard library.
No fitted local model, learned weights, cached corpus, task answer, or external
evidence is bundled. The Python base image is `python:3.13-slim`.

V3 adds a deterministic CPI-component forecast from the supplied corpus's
pre-cutoff three-month average and historical range notes. The note itself is
the exact citation. For macro revisions, V3 predicts continuation of the
latest pre-cutoff revision direction in the official vintage notes and cites
that note. For Treasury auctions, it forecasts the note's average
bid-to-cover ratio over recent same-tenor auctions and uses the note's
historical range as its interval. There is no fitted coefficient or external
dataset.

V4 adds an unfitted rule for rate-curve tasks when the supplied snapshot
explicitly records a policy move and either ongoing hikes or an easing path
already priced more aggressively than the Committee's projections. The
rule forecasts a fraction of the announced policy move, declining with
maturity, and cites the full pre-cutoff policy and positioning passage.
House-model regression intervals receive a broad floor derived from the
pre-existing feature-scaled fallback. These constants were chosen as
conservative uncertainty allowances, without fitting to any resolved task.

V5 enables the approved House model's documented thinking mode and permits
up to 4,000 generated tokens per request, the published per-request limit.
This is a global inference setting for all House tasks, without fitting to
any post-cutoff label or switching per task.

When the harness supplies the House route, the agent calls only the approved
`nvidia/nemotron-3-super-120b-a12b` model at revision `rl-030326-fp8` through
that route. Its training cutoff is unpublished; the organizer provides and
controls this model. The agent does not adapt or fine-tune it.

The source retrieval and prompt code is derived from the official MIT-licensed
Track 4 strong RAG baseline. The image's inputs at evaluation are solely the
mounted task and corpus. Citation spans are located in those corpus documents,
and documents dated after the task cutoff are excluded before retrieval.
