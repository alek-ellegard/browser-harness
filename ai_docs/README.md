# ai_docs

Routing table for browser-harness extension knowledge.

## Routes

USE `custom-sites.md` WHEN registering a new website (domain skill or site-specific Python helpers)
USE `docker-headless.md` WHEN running browser-harness in Docker with self-hosted headless Chrome (4-service compose: frontend + chrome + cdp-proxy + harness; no third-party services; suitable for sensitive / company-internal sites). Working reference at `docker/`.
USE `docker-headless-cloud.md` WHEN running browser-harness in Docker via Browser Use cloud browsers (hosted, billed; sends page traffic to api.browser-use.com; no cdp-proxy sidecar needed)
