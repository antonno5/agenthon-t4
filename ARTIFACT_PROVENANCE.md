# Track 4 V2 artifact provenance

The V2 image contains Python source, a deterministic BM25 index built at runtime
from the supplied official frozen corpus, and the Python 3.13 standard library.
No fitted local model, learned weights, cached corpus, task answer, or external
evidence is bundled. The Python base image is `python:3.13-slim`.

When the harness supplies the House route, the agent calls only the approved
`nvidia/nemotron-3-super-120b-a12b` model at revision `rl-030326-fp8` through
that route. Its training cutoff is unpublished; the organizer provides and
controls this model. The agent does not adapt or fine-tune it.

The source retrieval and prompt code is derived from the official MIT-licensed
Track 4 strong RAG baseline. The image's inputs at evaluation are solely the
mounted task and corpus. Citation spans are located in those corpus documents,
and documents dated after the task cutoff are excluded before retrieval.
