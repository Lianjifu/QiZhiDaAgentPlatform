# 企智搭 · 智能体平台 — root Makefile
#
# Ports (defined in bin/qzdap-stack/qzdap-env.sh, override via env):
#   QZDAP_FRONTEND_PORT   5200  (Vite dev server)
#   QZDAP_LISTEN_PORT     9200  (qzdap-gateway → qzdap-app)
#   QZDAP_APP_PORT        8200  (Python qzdap-app)
#   QZDAP_PG_PORT         5434  (QZDAP Postgres, when started)

QZDAP_STACK_DIR := bin/qzdap-stack

.PHONY: qzdap-up qzdap-down qzdap-status qzdap-logs qzdap-clean \
        help

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

qzdap-up: ## Start QZDAP dev stack (gateway + Vite + de-app)
	@$(QZDAP_STACK_DIR)/run-qzdap-stack.sh

qzdap-down: ## Stop QZDAP dev stack
	@$(QZDAP_STACK_DIR)/stop-qzdap-stack.sh

qzdap-status: ## Show QZDAP stack status
	@$(QZDAP_STACK_DIR)/status-qzdap-stack.sh

qzdap-logs: ## Tail QZDAP logs (gateway + vite)
	@tail -F $(QZDAP_STACK_DIR)/logs/qzdap-*.log

qzdap-clean: ## Clean QZDAP logs + pid files
	@rm -f $(QZDAP_STACK_DIR)/logs/*.log $(QZDAP_STACK_DIR)/logs/*.pid
	@echo "cleaned"