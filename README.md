# keyword-checker

A GitHub Actions composite action that scans the **added** lines of a pull
request for forbidden keywords (hard-coded passwords, API keys, lingering
TODOs, …) and posts inline review comments — similar to GitHub Copilot
Code Review.

## Usage

In your business repo, add `.github/workflows/pr-keyword-check.yml`:

```yaml
name: PR Keyword Check
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  check:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v5
      - uses: 463975089/keyword-review@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Then add `.github/keywords.yml` (see `examples/keywords.yml`):

```yaml
keywords:
  - type: string
    value: "password"
    message: "Hardcoded password. Use env vars."
  - type: regex
    value: "sk-[a-zA-Z0-9]{32,}"
    message: "Possible OpenAI API key leak."
```

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `github-token` | (required) | Token used for API calls and review submission. |
| `keywords-path` | `.github/keywords.yml` | Path to the keyword config inside the business repo. |
| `no-violation-action` | `comment` | Event when no violations: `comment` or `approve`. |

## Behaviour

- Only **added** lines (`+` in the diff) are scanned.
- Multiple rules triggered on the same line are merged into one comment.
- A missing `keywords.yml` produces a warning but does not fail the check.
- An invalid regex rule is skipped (with a warning); other rules continue.
- PRs with more than 300 changed files have the excess skipped; a notice
  is added to the review body.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```
