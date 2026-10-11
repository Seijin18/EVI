# EVI — operação local.  make up | make status | make down
#
#   make up      sobe a stack (Docker), espera o agent-api e liga o watchdog
#   make status  containers, saúde do agent-api, WhatsApp, Telegram, schedules, watchdog
#   make down    desliga a stack e o watchdog (senão ele alertaria "fora do ar" a cada minuto)
#
# Dados em ./data e volumes são preservados. Neo4j é opcional (profile `graph`):
#   make up GRAPH=1

SHELL := /bin/bash
.DEFAULT_GOAL := status

COMPOSE   := docker compose $(if $(GRAPH),--profile graph,)
API_URL   ?= http://127.0.0.1:8002
EVO_URL   ?= http://127.0.0.1:8082
WMILL_URL ?= http://127.0.0.1:8001
WATCHDOG  := evi-watchdog.timer

# Lê só uma variável do .env (nunca faz source do arquivo).
envval = $$(grep -m1 '^$(1)=' .env 2>/dev/null | cut -d= -f2-)

.PHONY: up status down logs

up:
	@echo "==> Subindo a stack (docker compose up -d)..."
	@$(COMPOSE) up -d
	@./scripts/evi-wait-agent-api.sh
	@if systemctl --user cat $(WATCHDOG) >/dev/null 2>&1; then \
	  systemctl --user start $(WATCHDOG) && echo "==> Watchdog ligado"; \
	else \
	  echo "==> Watchdog não instalado (ver docs/operations.md)"; \
	fi
	@echo
	@$(MAKE) --no-print-directory status

down:
	@if systemctl --user cat $(WATCHDOG) >/dev/null 2>&1; then \
	  systemctl --user stop $(WATCHDOG) evi-watchdog.service 2>/dev/null; echo "==> Watchdog desligado"; \
	fi
	@echo "==> Desligando a stack (volumes e dados preservados)..."
	@docker compose --profile graph stop
	@docker compose --profile graph ps --format 'table {{.Service}}\t{{.State}}'

status:
	@echo "== Containers =="
	@docker compose --profile graph ps -a --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' 2>/dev/null || echo "docker indisponível"
	@echo
	@echo "== agent-api =="
	@curl -s -m 15 -o /tmp/evi-health.json -w "/health HTTP %{http_code} em %{time_total}s\n" $(API_URL)/health \
	  && python3 -c "import json;d=json.load(open('/tmp/evi-health.json'));print('status:',d.get('status'));print('  ' + ', '.join(k+('✓' if v.get('ok') else '✗') for k,v in d.get('checks',{}).items()))" 2>/dev/null \
	  || echo "agent-api não respondeu (make up)"
	@echo
	@echo "== WhatsApp (Evolution) =="
	@KEY=$(call envval,EVOLUTION_API_KEY); INST=$(call envval,EVOLUTION_INSTANCE_NAME); \
	  curl -s -m 8 -H "apikey: $$KEY" $(EVO_URL)/instance/connectionState/$${INST:-evi} 2>/dev/null \
	  | python3 -c "import json,sys;s=json.load(sys.stdin)['instance']['state'];print('instância',s,'' if s=='open' else '→ desconectado: gere o QR e escaneie em Dispositivos conectados')" 2>/dev/null \
	  || echo "Evolution não respondeu"
	@echo
	@echo "== Telegram =="
	@S=$$(docker inspect -f '{{.State.Running}} {{.State.StartedAt}}' $$(docker compose ps -a -q agent-api) 2>/dev/null); \
	  if [[ "$$S" == true* ]] && docker compose logs --since "$${S#true }" agent-api 2>/dev/null | grep -q "Telegram poller started"; \
	  then echo "poller ativo (long polling)"; else echo "poller inativo (agent-api parado ou sem TELEGRAM_MODE=polling)"; fi
	@echo
	@echo "== Windmill =="
	@curl -s -m 5 -o /dev/null -w "servidor HTTP %{http_code}\n" $(WMILL_URL)/api/version || echo "Windmill não respondeu"
	@cd windmill && ../scripts/wmill.sh schedule list --workspace evi 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep -E "f/integrations" | sed 's/[│┌┐└┘├┤┬┴┼─]/ /g' | tr -s ' ' | sed 's/^/  /' || true
	@echo
	@echo "== Watchdog =="
	@systemctl --user is-active $(WATCHDOG) 2>/dev/null | sed 's/^/timer: /' || echo "timer: não instalado"

logs:
	@docker compose logs -f --tail=50 agent-api
