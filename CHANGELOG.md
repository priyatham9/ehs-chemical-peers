# Changelog

## 0.1.0 - 2026-09-27

First version.

- Pipeline joining OSHA Form 300A injury logs (2016-2024), EPA Risk Management Program facilities and accident histories (Data Liberation Project FOIA copy, through 2025) and OSHA Severe Injury Reports (January 2015 to November 2025) for NAICS 325 plants, by ZIP plus street number with a name fallback.
- Plain-language product types (from NAICS) and chemical families (from chemicals held).
- Findings in `outputs/summary.json`: size noise, year-to-year stability, injury rate against next-year releases and serious injuries, release predictors, release and serious-injury anatomy.
- Plant explorer (`docs/index.html`): baseline picker, filters, exact-Poisson comparison band, year-by-year view, releases, serious injuries, peer list with CSV download.
- Story (`docs/story.html`) and data and method page (`docs/method.html`).
- Synthetic fixture tests, real-data regression tests, README number check.
