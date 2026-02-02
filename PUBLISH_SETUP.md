# Publishing anymoment to PyPI

This guide walks you through setting up PyPI publishing and the GitHub Action that builds, publishes to PyPI, and creates a GitHub release when you push a version tag.

**PyPI "Pending" publisher:** If you added a Trusted Publisher on PyPI, it stays "Pending" until the first successful upload from that workflow. Once you run the workflow (push a `v*` tag) and it uploads, PyPI accepts it and the publisher is no longer pending.

## How the workflow runs

- **Trigger:** Push a tag that matches `v*` (e.g. `v0.1.0`, `v0.1.1`).
- **Steps:** Check version matches `pyproject.toml`, build the package, publish to PyPI, create a GitHub release.

**Release process:**

1. Bump `version` in `pyproject.toml` (e.g. to `0.1.1`).
2. Commit and push to `main`.
3. Create and push the tag:  
   `git tag v0.1.1` then `git push origin v0.1.1`
4. The workflow runs automatically: build → PyPI upload → GitHub release.

The workflow lives at **`.github/workflows/workflow.yml`** (repo root).

---

## Option A: Trusted Publishing (recommended)

No long-lived tokens. PyPI trusts your GitHub repo via OIDC.

### 1. Create the project on PyPI (if needed)

- Go to [pypi.org](https://pypi.org), sign in.
- **Register new project:** “Add” → “New project”.
- **Project name:** `anymoment` (must match `name` in `pyproject.toml`).
- Complete the form and create the project.

### 2. Add a Trusted Publisher on PyPI

- Open your project on PyPI → **“Publishing”** (or **“Manage”** → **“Publishing”**).
- **“Add a new publisher”** / **“Add trusted publisher”**.
- **PyPI Project name:** `anymoment`.
- **Owner:** Your GitHub org or username (e.g. `SinewaysTechnology`).
- **Repository name:** The repo that contains the workflow (e.g. `anymoment-python`). **Must match exactly** what you entered on PyPI.
- **Workflow name:** `workflow.yml` — the file must be at `.github/workflows/workflow.yml` in the repo.
- **Environment name:** `pypi` — must match the job’s `environment: pypi` in the workflow. Create this environment in GitHub (repo **Settings** → **Environments** → **New environment** → name it `pypi`) if it doesn’t exist.
- Save.

### 3. GitHub

- Ensure the workflow file is in the repo:  
  `.github/workflows/workflow.yml`
- Create the **pypi** environment if needed: repo **Settings** → **Environments** → **New environment** → name: `pypi`. The workflow uses `environment: pypi` to match your PyPI Trusted Publisher.
- No GitHub secrets are required for Trusted Publishing.
- Push a version tag (e.g. `v0.1.1`) to trigger the run.

---

## Option B: API token (legacy)

Use this if you prefer not to use Trusted Publishing yet.

### 1. Create an API token on PyPI

- [pypi.org](https://pypi.org) → **Account settings** → **API tokens**.
- **“Add API token”**.
- **Token name:** e.g. `github-actions-anymoment`.
- **Scope:** “Project” → select **anymoment** (or “Entire account” for all projects).
- Create and **copy the token** (it is shown only once).

### 2. Add the token as a GitHub secret

- GitHub repo → **Settings** → **Secrets and variables** → **Actions**.
- **“New repository secret”**.
- **Name:** `PYPI_API_TOKEN`
- **Value:** paste the PyPI token.
- Save.

### 3. Use the token in the workflow

In `.github/workflows/workflow.yml`, change the “Publish to PyPI” step to pass the token:

```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
          repository-url: https://upload.pypi.org/legacy/
```

(Remove or comment out any Trusted Publishing–only options in that step so the action uses the token.)

---

## Checklist before first release

- [ ] PyPI project `anymoment` exists (or will be created on first upload).
- [ ] Either Trusted Publisher is configured **or** `PYPI_API_TOKEN` is set in GitHub.
- [ ] Workflow file is in the correct repo (the one you used in Trusted Publisher / where you added the secret).
- [ ] `version` in `pyproject.toml` matches the tag (e.g. tag `v0.1.1` → `version = "0.1.1"`).

---

## TestPyPI (optional)

To try publishing to TestPyPI first, add `repository-url: https://test.pypi.org/legacy/` to the Publish step and use a TestPyPI token or Trusted Publisher for test.pypi.org.

---

## Troubleshooting

| Problem | What to check |
|--------|----------------|
| “Version mismatch” | Tag (e.g. `v0.1.1`) must exactly match `version` in `pyproject.toml`. |
| PyPI 403 / “Invalid or non-existent authentication” | Trusted Publisher: owner/repo/workflow name must match PyPI. Token: secret name `PYPI_API_TOKEN`, token not expired, correct scope. |
| “Project not found” on PyPI | Create the project on PyPI first (name `anymoment`) or ensure the token has scope for that project. |
| Workflow not triggering | Tag must match `v*` and be pushed to the same repo that has the workflow. |
