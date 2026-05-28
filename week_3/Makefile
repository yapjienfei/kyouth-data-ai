# Makefile for Resume Helper Chatbot (Frontend + Backend)
# Usage: make <command>

# Colors for output
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Project name
PROJECT_NAME := resume-chatbot

# Docker Compose file
COMPOSE_FILE := docker-compose.yml

# Default target
.PHONY: help
help:
	@echo "$(GREEN)Resume Helper Chatbot - Docker Commands$(NC)"
	@echo ""
	@echo "$(BLUE)Basic Commands:$(NC)"
	@echo "  $(YELLOW)make up$(NC)          - Start all services (frontend + backend)"
	@echo "  $(YELLOW)make down$(NC)        - Stop all services"
	@echo "  $(YELLOW)make restart$(NC)     - Restart all services"
	@echo "  $(YELLOW)make build$(NC)       - Build or rebuild images"
	@echo "  $(YELLOW)make logs$(NC)        - View all logs"
	@echo "  $(YELLOW)make status$(NC)      - Show service status"
	@echo ""
	@echo "$(BLUE)Service-Specific Commands:$(NC)"
	@echo "  $(YELLOW)make frontend$(NC)    - Start only frontend"
	@echo "  $(YELLOW)make backend$(NC)     - Start only backend"
	@echo "  $(YELLOW)make logs-frontend$(NC) - View frontend logs"
	@echo "  $(YELLOW)make logs-backend$(NC)  - View backend logs"
	@echo ""
	@echo "$(BLUE)Utility Commands:$(NC)"
	@echo "  $(YELLOW)make shell-frontend$(NC) - Open shell in frontend container"
	@echo "  $(YELLOW)make shell-backend$(NC)  - Open shell in backend container"
	@echo "  $(YELLOW)make clean$(NC)       - Stop and remove containers, networks"
	@echo "  $(YELLOW)make clean-all$(NC)   - Clean + remove volumes and images"
	@echo "  $(YELLOW)make rebuild$(NC)     - Rebuild and restart all services"
	@echo ""

# Start all services (in background)
.PHONY: up
up:
	@echo "$(GREEN)Starting all services...$(NC)"
	docker compose -f $(COMPOSE_FILE) up -d
	@echo "$(GREEN)✅ Services started!$(NC)"
	@echo "$(BLUE)Frontend:$(NC) http://localhost:8000"
	@echo "$(BLUE)Backend:$(NC)  http://localhost:8001"
	@echo "$(BLUE)Backend Docs:$(NC) http://localhost:8001/docs"
	@echo ""
	@echo "$(YELLOW)View logs: make logs$(NC)"

# Start services in foreground (see logs)
.PHONY: up-foreground
up-foreground:
	@echo "$(GREEN)Starting all services in foreground...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	docker compose -f $(COMPOSE_FILE) up

# Stop all services
.PHONY: down
down:
	@echo "$(YELLOW)Stopping all services...$(NC)"
	docker compose -f $(COMPOSE_FILE) down
	@echo "$(GREEN)✅ All services stopped$(NC)"

# Restart all services
.PHONY: restart
restart: down up
	@echo "$(GREEN)✅ Services restarted$(NC)"

# Build images
.PHONY: build
build:
	@echo "$(GREEN)Building Docker images...$(NC)"
	docker compose -f $(COMPOSE_FILE) build
	@echo "$(GREEN)✅ Build complete$(NC)"

# Build without cache
.PHONY: build-no-cache
build-no-cache:
	@echo "$(GREEN)Building Docker images without cache...$(NC)"
	docker compose -f $(COMPOSE_FILE) build --no-cache
	@echo "$(GREEN)✅ Build complete$(NC)"

# View all logs
.PHONY: logs
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# View frontend logs only
.PHONY: logs-frontend
logs-frontend:
	docker compose -f $(COMPOSE_FILE) logs -f frontend

# View backend logs only
.PHONY: logs-backend
logs-backend:
	docker compose -f $(COMPOSE_FILE) logs -f backend

# Show service status
.PHONY: status
status:
	@echo "$(GREEN)Service Status:$(NC)"
	docker compose -f $(COMPOSE_FILE) ps

# Start only frontend
.PHONY: frontend
frontend:
	@echo "$(GREEN)Starting frontend only...$(NC)"
	docker compose -f $(COMPOSE_FILE) up -d frontend
	@echo "$(GREEN)✅ Frontend started at http://localhost:8000$(NC)"

# Start only backend
.PHONY: backend
backend:
	@echo "$(GREEN)Starting backend only...$(NC)"
	docker compose -f $(COMPOSE_FILE) up -d backend
	@echo "$(GREEN)✅ Backend started at http://localhost:8001$(NC)"
	@echo "$(BLUE)API Docs: http://localhost:8001/docs$(NC)"

# Open shell in frontend container
.PHONY: shell-frontend
shell-frontend:
	docker compose -f $(COMPOSE_FILE) exec frontend /bin/bash || docker compose -f $(COMPOSE_FILE) exec frontend /bin/sh

# Open shell in backend container
.PHONY: shell-backend
shell-backend:
	docker compose -f $(COMPOSE_FILE) exec backend /bin/bash || docker compose -f $(COMPOSE_FILE) exec backend /bin/sh

# Stop and remove containers, networks
.PHONY: clean
clean: down
	@echo "$(YELLOW)Removing containers, networks...$(NC)"
	docker compose -f $(COMPOSE_FILE) down -v
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

# Clean everything including volumes and images
.PHONY: clean-all
clean-all: clean
	@echo "$(YELLOW)Removing images...$(NC)"
	docker rmi resume-frontend resume-backend 2>/dev/null || true
	@echo "$(GREEN)✅ Complete cleanup finished$(NC)"

# Rebuild and restart
.PHONY: rebuild
rebuild: clean build up
	@echo "$(GREEN)✅ Rebuild complete!$(NC)"

# Pull latest base images
.PHONY: pull
pull:
	@echo "$(GREEN)Pulling latest base images...$(NC)"
	docker compose -f $(COMPOSE_FILE) pull
	@echo "$(GREEN)✅ Pull complete$(NC)"

# Check if services are healthy
.PHONY: health
health:
	@echo "$(GREEN)Checking service health...$(NC)"
	@echo -n "Frontend (port 8000): "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "❌ Not responding"
	@echo ""
	@echo -n "Backend (port 8001): "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health || echo "❌ Not responding"
	@echo ""

# Show container resource usage
.PHONY: stats
stats:
	@echo "$(GREEN)Container stats (Ctrl+C to exit):$(NC)"
	docker stats resume-frontend resume-backend

# Export logs to file
.PHONY: save-logs
save-logs:
	@echo "$(GREEN)Saving logs to logs_$(shell date +%Y%m%d_%H%M%S).txt$(NC)"
	docker compose -f $(COMPOSE_FILE) logs > logs_$(shell date +%Y%m%d_%H%M%S).txt 2>&1
	@echo "$(GREEN)✅ Logs saved$(NC)"

# Quick start (build + up)
.PHONY: start
start: build up
	@echo "$(GREEN)✅ Chatbot is ready!$(NC)"
	@echo "$(BLUE)Open http://localhost:8000 in your browser$(NC)"

# Development mode with live reload
.PHONY: dev
dev:
	@echo "$(GREEN)Starting in development mode...$(NC)"
	@echo "$(YELLOW)Code changes will auto-reload$(NC)"
	docker compose -f $(COMPOSE_FILE) up --build

# Show all running containers
.PHONY: ps
ps:
	@echo "$(GREEN)All Docker containers:$(NC)"
	docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Prune unused Docker resources
.PHONY: prune
prune:
	@echo "$(RED)⚠️  This will remove all unused containers, networks, and images.$(NC)"
	@echo "$(RED)Are you sure? Type 'yes' to continue:$(NC)" \
	&& read answer \
	&& if [ "$$answer" = "yes" ]; then \
		docker system prune -a -f; \
		echo "$(GREEN)✅ Prune complete$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

.PHONY: fclean-force
fclean-force:
	@echo "$(RED)Force cleaning everything...$(NC)"
	docker stop $$(docker ps -aq) 2>/dev/null || true
	docker rm $$(docker ps -aq) 2>/dev/null || true
	docker rmi $$(docker images -q) 2>/dev/null || true
	docker volume rm $$(docker volume ls -q) 2>/dev/null || true
	docker network rm $$(docker network ls -q | grep -v "bridge\|host\|none") 2>/dev/null || true
	docker builder prune -a -f 2>/dev/null || true
	docker system prune -a --volumes -f 2>/dev/null || true
	@echo "$(GREEN)✅ Force full cleanup complete!$(NC)"