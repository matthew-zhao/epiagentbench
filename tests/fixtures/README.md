# Test-fixture provenance

These small files exercise parsers and scientific guardrails. They are not
calibration or validation cohorts.

- `nors_ltc_observation.csv` is synthetic. Its metadata preserves the official
  NORS dataset identifier and required column names solely to test the pinned
  LTC observation contract. Its outbreak counts and trend are invented and
  must never be reported as CDC estimates.
- `cms_provider_information_development.csv` contains three public rows and a
  morphology-relevant column projection transcribed from the official CMS
  Provider Information release identified by its matching metadata. It is a
  development parser fixture, not a national sample and not a holdout.

Empirical runs must use separately pinned source bytes and metadata, record the
resulting hashes, and remain outside the test-fixture directory.
