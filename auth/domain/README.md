# Domain Structure (Phase 1)

This folder introduces feature-oriented modules inside the existing `auth` app.

Current phase goals:

- Keep all public URLs and route names unchanged.
- Keep existing models and migrations unchanged.
- Route requests through domain `urls.py` modules.
- Use domain `views.py` wrappers as compatibility exports while logic still lives in `auth/views.py`.

Planned next step:

- Move logic from `auth/views.py` and `auth/tests.py` into domain-local `services.py`, `selectors.py`, and `tests/`.

