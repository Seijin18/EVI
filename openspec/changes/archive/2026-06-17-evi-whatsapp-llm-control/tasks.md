# Tasks: evi-whatsapp-llm-control

- [x] **2.1 Infra filter**
  - **Files:** `evolution_filter.py`, `.env.example`
  - **Verify:** `./scripts/evi-test evolution`

- [x] **2.2 Controle → grafo**
  - **Files:** `telegram_handler.py`, `whatsapp_control.py`, `direct_handlers.py`
  - **Verify:** `./scripts/evi-test telegram`

- [x] **2.3 Extract + contact context**
  - **Files:** `whatsapp_llm_extract.py`, `contact_filesystem.py`, `whatsapp_processor.py`
  - **Verify:** `./scripts/evi-test whatsapp`

- [x] **2.4 List pending filter**
  - **Files:** `db.py`, `commitment_tools.py`
  - **Verify:** `./scripts/evi-test whatsapp`

- [x] **2.5 Context builder JID**
  - **Files:** `context_assembly.py`, `main.py`
  - **Verify:** `./scripts/evi-test contact-memory`
