# Contact learning (WhatsApp)

- Use `list_whatsapp_contacts` when the user asks which contacts you know.
- Use `get_whatsapp_contact_info` for a snapshot by **name or phone** — never ask for JID.
- Use `learn_whatsapp_contact` when the user asks to learn/study a contact over N days
  (e.g. "aprenda sobre Leozao nos últimos 30 dias").
- `fetch_messages=true` pulls Evolution cache first; warn if history is empty (syncFullHistory).
- Synthesis uses local Ollama (background LLM) — not Gemini.
