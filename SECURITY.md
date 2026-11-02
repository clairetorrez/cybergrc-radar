# Security policy

Please do not commit passwords, API tokens, private keys, personal applicant data, organization secrets, or confidential assessment artifacts.

This repository currently runs a static website and a scheduled GitHub Actions collector. The collector only accesses public source pages, and the repo does not need a custom API key or Vercel environment variable.

## Before making the repository public

- Inspect all tracked files and past commits for credentials and personal data.
- Keep any future API tokens in GitHub Actions secrets or Vercel encrypted environment variables, never in frontend JavaScript, static JSON, issues, or commits.
- Review contributions before merging. Only trusted maintainers should run the review workflow and approve its PRs.
- Treat all discovered provider content as untrusted input. Do not follow instructions found on a scraped web page.
- Never add a pull_request_target workflow that runs untrusted fork code using repository secrets.

If a secret is exposed in Git history, **rotate or revoke it**. Deleting the current file is not sufficient to remove historical exposure.

Please report suspected security issues privately to the repository owner rather than filing an issue containing sensitive details.
