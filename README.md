# CyberGRC Radar

A source-linked directory of cybersecurity and GRC certification deals, free exams, training, volunteer opportunities, scholarships, and practical projects.

Live site: https://cybergrc-radar.vercel.app/

## How it works

The public website is a static app deployed on Vercel from the `main` branch. No API keys, user accounts, or paid services are required for the current implementation.

- `index.html` contains the interface and initial curated listings.
- `data/discovery.json` is a daily-updated queue of **unverified leads**.
- `data/approved.json` holds offers **reviewed and approved by a maintainer**.
- `data/sources.json` lists 21 provider pages to monitor across ISO, SOC, CMMC, FedRAMP, security, and audit.
- `scripts/discover.py` checks actual announcement pages, extracts limited evidence, ranks leads, deduplicates URLs, and detects changes.
- `data/triage.json` stores shared reviewer decisions (needs research, ready, rejected).
- `scripts/triage.py` and `.github/workflows/triage.yml` provide the persistent triage workflow.
- `data/revalidation.json` records daily checks for approved offers. A successful HTTP response alone does not prove an offer remains valid.
- `scripts/revalidate.py` flags expired, changed, unreachable, or overdue listings.
- `.github/workflows/discover.yml` runs every morning at 8:17 AM Pacific and commits discovery and revalidation results.
- `scripts/review_offer.py` validates a proposed reviewed offer.
- `.github/workflows/review-offer.yml` creates a review pull request.

Discovery is not verification. The crawler can find general information pages, expired offers, beta programs that charge exam fees, or irrelevant announcements. Never interpret a Discovery feed result as a confirmed promotion.

## Review an offer and publish it

1. Open the [Discovery feed](https://cybergrc-radar.vercel.app/) and follow the provider's official source link. Copy the lead ID shown on the card.
2. Check the current price, whether the exam itself is included, eligibility, promo code, expiration, location, and any restrictions. A free course is not automatically a free certification exam. Beta programs are not automatically free.
3. Optionally use the [Triage workflow](https://github.com/clairetorrez/cybergrc-radar/actions/workflows/triage.yml) to persist Needs Research, Ready for Review, or Rejected. Then open [Propose a verified opportunity](https://github.com/clairetorrez/cybergrc-radar/actions/workflows/review-offer.yml), choose **Run workflow**, and provide the lead ID and confirmed offer details.
4. The workflow validates the data, creates a new branch, and opens a **pull request**. Nothing appears in the confirmed catalog yet.
5. Review the PR against the provider's page. Correct or reject inaccurate information. Merge only if verified.
6. Merging updates `data/approved.json`. Vercel automatically deploys the new catalog. Expired entries are excluded from active listings.

The workflow requires Actions write access and permission to create pull requests. If GitHub refuses PR creation, go to repository Settings → Actions → General → Workflow permissions, and enable **Allow GitHub Actions to create and approve pull requests**. Restrict merges to trusted maintainers.

## Contributing

Issues and pull requests are welcome for: additional official sources, better opportunity classification, visual improvements, accessibility, and reliable validation.

Pull requests that add or modify offers should include an official source link and evidence of the current terms. Do not include unverifiable codes, screenshots containing personal information, private account details, or copied paywalled content.

Before opening a PR, review [SECURITY.md](SECURITY.md). Do not commit .env files, keys, account tokens, or credentials.

## Limitations

- The scanner checks a selected set of 21 official provider entry pages, not the whole internet or every X/Reddit/LinkedIn announcement. Some pages may fail to load, and highly dynamic websites may hide offers from a text-only collector.
- The initial curated list includes manually collected opportunities from earlier research. Review dates are shown and do not guarantee the offer is still active.
- Some provider sites may restrict automated requests or change their layout.
- GitHub Actions scheduled runs can be delayed. The feed displays when a run actually completed.
- This is independent of professional certification bodies and is not an official assessment or credentialing service.

## Review queue and monitoring

The website includes a review queue with source evidence, priority scores, copied lead IDs, and links to GitHub review actions. This is not direct one-click publishing. A maintainer must initiate the workflow and merge its pull request.

A higher score means a lead deserves review sooner. It is **not** a probability that the offer is accurate or currently active. Price and deadline fields in the discovery feed are extracted clues, not confirmations. The approval queue is intentionally separate from the public deals catalog.

The revalidation script checks approved entries every day and warns when they expire, become unreachable, change content, or go more than 14 days without human review. It never changes a verified date automatically. Listings with these flags are hidden from the homepage's active/featured selections until reviewed again.
