## ADDED Requirements

### Requirement: Fill mode calls the real LLM only for changed requests
`evi-sim run --llm fill` SHALL serve every call whose normalized request key is in the scenario's cassette from the cassette, and SHALL call the real provider only for keys that are not recorded or are used more times than recorded, for chat and structured calls alike. With `--repeat N`, every attempt SHALL start from the cassette as it was when the run began, so that only the changed calls are exercised N times live. A passing attempt SHALL rewrite the cassette with exactly the calls it used, in order; a failed provider call SHALL NOT be recorded. The `sim-fill` provider SHALL exist only when `EVI_SIM=1`.

#### Scenario: SCN-SIM-10
- **GIVEN** the `critical` cassettes are up to date with the current prompts and tools
- **WHEN** `evi-sim run --tag critical --repeat 3 --llm fill` runs
- **THEN** it makes 0 real LLM calls, passes, and leaves the cassettes unchanged
- **AND** after a change to one tool's docstring, only the calls whose request changed go to the real LLM, 3 times each

### Requirement: The simulation report separates real from served LLM calls
The `evi-sim` report SHALL show, per attempt and in total, the LLM calls that reached a real provider, the calls served from a cassette, and the real input/output tokens. `--max-llm-calls` SHALL count only real calls.

#### Scenario: SCN-SIM-11
- **WHEN** a fill run serves 7 calls from the cassette and makes 2 real calls
- **THEN** the report shows "real 2 · served 7" with the tokens of the 2 real calls

### Requirement: LLM evaluations reuse unchanged answers
`evi-test llm-eval` SHALL cache each structured answer by task, provider, models, prompt and schema in `data/eval/cache.jsonl`, using the i-th cached sample for the i-th identical call of a run and calling the provider only when the sample does not exist. Failed calls SHALL NOT be cached. `--no-cache` or `EVI_LLM_EVAL_CACHE=0` SHALL bypass the cache.

#### Scenario: SCN-SIM-12
- **GIVEN** `llm-eval debt` ran once with the current prompt and model
- **WHEN** it runs again unchanged
- **THEN** it reports the same accuracy with 0 provider calls and 0 cost
- **AND** with `--no-cache` every case calls the provider
