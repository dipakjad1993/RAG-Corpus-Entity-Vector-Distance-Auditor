# Publishing — pip + Docker (GHCR)

`uv sync` is for devs. Adoption needs one-liners:

* **PyPI (planned `pip install ragevda`)**: build backend is hatchling;
  `.github/workflows/publish.yml` builds + publishes on GitHub Release.
  Until first publish, install from source: `pip install -e .` then
  `python -m spacy download en_core_web_sm`.
* **Docker (GHCR versioned images, planned)**: `Dockerfile` = FULL
  (nomic + hybrid + reranker), `Dockerfile.render` = LITE (MiniLM-90MB,
  reranker/hybrid OFF, model-free `/health`, fits 512 MB free tier).
  `publish.yml` builds + pushes `ghcr.io/<owner>/ragevda:<version>` on
  release. Until then: `docker build -f Dockerfile.render -t ragevda:lite .`.
* **Versions**: single source `ragevda/version.py`; CI `version-check`
  asserts README == version.py == pyproject. Bump all three together.

Status: workflow files ship in this release; first PyPI/GHCR push happens on
the next tagged release (`v2.3.0`). No secrets needed in-repo.
