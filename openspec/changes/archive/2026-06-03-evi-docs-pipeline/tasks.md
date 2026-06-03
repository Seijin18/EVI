# Tasks: evi-docs-pipeline

- [x] 3.1 ingest_university_folder tool
  - Files: agent/tools/rag_tool.py, registry.py
  - Verify: ./scripts/evi-test rag

- [x] 3.2 watch_and_ingest parametrized
  - Files: scripts/watch_and_ingest.sh
  - Verify: ./scripts/evi-test watcher

- [x] 3.3 systemd example
  - Files: scripts/systemd/evi-watch-ingest.service
  - Verify: manual
