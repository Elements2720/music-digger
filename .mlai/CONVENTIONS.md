# Conventions

## Guards (added after a mistake repeated)
- Before finishing, stop the servers and background commands you started; long-lived work goes in a job or the preview.

## Quality gates (frontend + backend, ML-REFACTOR)
- Run after any change: `node --check` on every `frontend/js/**/*.js`; `ruff check src tests` and `ruff format --check src tests` from `backend/`; `uv run --python 3.13 pytest -q -p no:cacheprovider` (814 tests, ~12s); AST purity test `tests/domain/test_domain_purity.py`; ASCII-only check on `backend/src/presentation/cli/commands.py`; browser check of the preview at 390px and 1280px.
- Frontend display rule: BPM, percentages and clock values are shown exactly as stored — no `Math.round`/`Math.floor`/percent-thinning arithmetic in view code.
- The preview's `/healthz` 404 comes from the static frontend server (no health route); it is not an app error.
- Preview nav: top tabs are `role="tab"` buttons; Library sub-tabs are `data-libmode` buttons ("Artists Hub", "Tracks Cleanup", "Seeds & Blacklist").
