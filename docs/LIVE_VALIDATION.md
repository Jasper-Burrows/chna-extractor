# Live validation

Live checks are deliberately absent from normal tests and CI.

1. Rotate old credentials and create a new, scoped OpenAI sandbox project/key.
2. Run `chna estimate fixture.pdf`; review the one expected Responses call, two-call schema-retry
   maximum, token assumptions, expected cost, and worst-case cost. Each call is reserved before it
   starts and the application refuses the next attempt if it would cross
   `CHNA_TOTAL_BUDGET_USD` (US$10 by default).
3. Set `CHNA_OPENAI_API_KEY` only in an untracked `.env` or process environment.
4. Use a synthetic report, run `chna extract ... --mode live`, then remove the key and `.data/`.
5. Record the date/model and mark OpenAI **live verified** only after inspecting evidence and usage.

Google Maps similarly requires a new sandbox key plus `CHNA_ENABLE_GOOGLE_MAPS=true`. Opt-in web
fallback uses one bounded Responses request for missing locations only, requires HTTPS source links,
never overwrites document values, and reserves a configurable tool-cost allowance before running.
Enable it with `CHNA_ENABLE_WEB_SEARCH=true`. Until a fresh-key run occurs, both providers must be
described as **contract verified**, not live verified.
