# Pulse scraping approach research

Date: 2025-02-14

## Constraints observed
- Pulse hosts each council on its own subdomain and renders the listings via a
  Vue single-page application.
- The public jobs list is empty until the Vue component loads data through
  JavaScript, so plain HTTP GET + parsing is insufficient.
- The Vue instance attaches to `#ctl00_ctl00_BodyContainer_BodyContainer_ctl00_JobsList`
  and exposes a `jobs` array on `__vue__`, which Playwright can access directly.
- Detail pages lazy-load extra content; a solution needs to follow the
  client-side routing and wait for selectors instead of scraping static HTML.

## Considered approaches
| Approach | Pros | Cons |
| --- | --- | --- |
| **Playwright (current)** | Works without reverse engineering APIs, resilient to DOM timing issues, allows screenshot/log capture. | Requires Chromium download in CI, slower than raw HTTP, must keep locators in sync. |
| **Headless browser + network interception** | Could replay the JSON API calls outside the browser, enabling faster cron jobs. | Needs per-tenant API discovery and headers, risk of breaking if Pulse changes contract, still needs Playwright for discovery. |
| **Static HTTP client** | Lowest resource usage, easy to host. | Not viable until the internal Pulse API is fully documented and authenticated requests are understood. |

## Recommendation
Stick with Playwright for now while instrumenting the network tab to capture the
XHR endpoint Pulse uses for search results. Once the endpoint and payload are
stable for Ballarat we can graduate to a lighter-weight client, but investing in
stability for one council provides the template required to scale to others.
