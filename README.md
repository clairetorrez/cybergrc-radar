# CyberGRC Radar

Cybersecurity, GRC, IT audit, cloud security, and AI governance opportunities in one source-linked directory.

Website: https://cybergrc-radar.vercel.app/

## How it works

CyberGRC Radar automatically searches selected official provider pages every day using GitHub Actions, then redeploys the static website on Vercel.

1. **Discover**: `scripts/discover.py` finds and scores relevant pages from provider sources listed in `data/sources.json`.
2. **Evaluate**: `scripts/auto_publish.py` reads the provider's page again and checks for explicit evidence of an offer, its cost and deadline. It rejects generic pages, unsupported prices, expired campaigns, and unclear claims.
3. **Publish**: High-confidence offers go into `data/approved.json` automatically, without a manual review queue or approval step.
4. **Recheck**: `scripts/revalidate.py` checks current and original catalog entries daily and flags expired, changed or unreachable source pages. Ambiguous offers are excluded or paused instead of being presented as valid.
5. **Deploy**: The automated workflow commits updated JSON; GitHub triggers Vercel's production deployment.

The normal schedule is 8:17 AM Pacific. GitHub may delay scheduled jobs.

## Files

- `index.html`: frontend, search, filters and Best Deals Today section.
- `data/discovery.json`: discovered candidate links. A discovery lead is not a verified offer.
- `data/approved.json`: automatically accepted offers plus any older curator entries.
- `data/auto_decisions.json`: reasons leads were accepted, rejected, or withheld.
- `data/revalidation.json`: expiration, page reachability and content drift checks.
- `data/sources.json`: monitored source locations.
- `scripts/auto_publish.py`: conservative rule-based source checking and publication.
- `.github/workflows/discover.yml`: daily end-to-end automation.

No paid API or external database is needed for the current system.

## Accuracy and limitations

Automated source checking cannot guarantee that a code still works, that registration has capacity, or that membership or geographic restrictions have not changed. An HTTP 200 response is not proof of offer availability.

The system errs on the side of withholding unsupported leads, so some legitimate offers will be missed. Beta programs do **not** imply free examinations. Free courses do **not** imply a free certification voucher. A priority score indicates relevance, not proof.

All automatically promoted records include an official provider URL, extracted evidence, an automated-check date and a publication status. Official provider terms control eligibility, pricing and availability.

Original manually curated listings may still appear in the catalog, subject to expiry and source health checks.

## Contributing

Issues and pull requests that add source providers, classification improvements, better verification tests, and interface or accessibility improvements are welcome. You do not need to review opportunities for them to publish. Maintainership of the repo stays with the repository owner.

Read `SECURITY.md` before contributing. Never commit tokens, credentials, or confidential information.
