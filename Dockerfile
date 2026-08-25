# Single stage, deliberately.
#
# The arena ships as plain files — Vue is vendored, there is no bundler and no
# node_modules — so there is nothing to build and no Node in the image. That is
# what makes "clone it and run one command" true for a judge on any machine,
# and it keeps the image small enough to deploy on a free tier.
#
# torch is not installed here. Tier 3 runs a lexicon, not an embedding model,
# and the campaign results the arena replays are committed rather than computed.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PRAMAN_MODE=replay

WORKDIR /app

COPY pyproject.toml ./
COPY praman/ ./praman/
RUN pip install --no-cache-dir .

COPY fixtures/ ./fixtures/
COPY results/ ./results/

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

# 0.0.0.0 and $PORT are not optional: binding 127.0.0.1 is the single most
# common cause of a deploy that builds green and then health-checks dead.
CMD ["sh", "-c", "uvicorn praman.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
