# Fortuna Navigation QA Report

## Green: Stabilized

- Home-level screens remain rooted at Main Menu.
- More now behaves as the parent for advanced owner tools: Intelligence, Automation, Reports, Settings, Production Health, and Owner Tools.
- More has Back and Main Menu controls.
- Intelligence -> Trends returns to Intelligence.
- Proxy Vault -> Proxy Detail -> Manage returns to Proxy Detail.
- Technical Details screens now return to their executive summary before leaving the section.
- Error fallback still offers a safe route back home.

## Yellow: Cleaned Up

- Production Observability now backs out to More instead of Settings.
- Integrity now leads with a calm production check summary and hides row-level DB checks behind Technical Details.
- Proxy Vault buttons now change based on real proxy state:
  - no proxies: Paste Proxy first
  - one proxy: Assign, Rotate, View Details, Paste Another
  - multiple proxies: View/choose a proxy before managing
- Proxy rotation now records session memory and refuses recently used suffixes.

## Root-Level Screens

These are intentionally treated as top-level owner paths:

- Home
- Start Here
- Today
- Setup Progress
- First Workspace Guide
- Proxy Vault
- Opportunities
- Help
- More

## Remaining Risks

- Telegram does not expose reliable browser automation for every mobile callback path, so mobile owner QA should still validate the most important Back flows.
- Some older deep screens still have dense Technical Details by design; they are now reached through More Details or Advanced paths.

## Follow-Up Recommendations

- Continue adding callback-health coverage for any owner-reported dead buttons.
- If the product later needs true click-history Back behavior, build on `parent_page_for()` and `root_page_for()` as the fallback truth layer.
