# Track 4 V2/V3 artifact provenance

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

When the harness supplies the House route, the agent calls only the approved
`nvidia/nemotron-3-super-120b-a12b` model at revision `rl-030326-fp8` through
that route. Its training cutoff is unpublished; the organizer provides and
controls this model. The agent does not adapt or fine-tune it.

The source retrieval and prompt code is derived from the official MIT-licensed
Track 4 strong RAG baseline. The image's inputs at evaluation are solely the
mounted task and corpus. Citation spans are located in those corpus documents,
and documents dated after the task cutoff are excluded before retrieval.
