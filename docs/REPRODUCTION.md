# Reproduction

The judge workflow was exercised on macOS/Apple Silicon with Python 3.12.13 and
uv 0.11.3. Other Unix-like systems with Python 3.12+ should work.

```bash
git clone <repository-url> kuber
cd kuber
uv sync
make test
make evaluate
```

Dependency installation requires internet access unless uv's cache is already
populated. Evaluation itself needs no internet and typically completes in
under a second on a laptop. No external API is required and default LLM cost is
zero. Expected outputs are JSON, CSV and Markdown below
`artifacts/evaluation`, plus JSONL/Markdown trajectories below
`artifacts/trajectories`.

Optional Gemini explanations are configured locally:

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY.
```

`.env` is ignored by Git. The judge evaluation does not enable Gemini, so its
results and costs remain deterministic and zero.

The live demo is separate. Its requirements and commands are in
`DEMO_GUIDE.md`; it downloads container images and was intentionally not
executed during the code-only implementation pass.
