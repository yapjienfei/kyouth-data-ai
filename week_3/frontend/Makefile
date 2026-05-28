# Makefile for Frontend Docker Service
# Usage: make <command>

# Variables
IMAGE_NAME := frontend-server
CONTAINER_NAME := frontend-app
PORT_HOST := 8000
PORT_CONTAINER := 8000
DOCKER_FILE := Dockerfile

# Colors for output
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# Default target
.PHONY: help
help:
	@echo "$(GREEN)Available commands:$(NC)"
	@echo "  $(YELLOW)make build$(NC)        - Build Docker image"
	@echo "  $(YELLOW)make run$(NC)          - Run container (foreground)"
	@echo "  $(YELLOW)make run-detached$(NC) - Run container in background"
	@echo "  $(YELLOW)make stop$(NC)         - Stop running container"
	@echo "  $(YELLOW)make restart$(NC)      - Restart container"
	@echo "  $(YELLOW)make logs$(NC)         - View container logs"
	@echo "  $(YELLOW)make logs-follow$(NC)  - Follow container logs"
	@echo "  $(YELLOW)make shell$(NC)        - Open shell in container"
	@echo "  $(YELLOW)make status$(NC)       - Show container status"
	@echo "  $(YELLOW)make ps$(NC)           - List all containers"
	@echo "  $(YELLOW)make remove$(NC)       - Remove container"
	@echo "  $(YELLOW)make clean$(NC)        - Remove container and image"
	@echo "  $(YELLOW)make clean-all$(NC)    - Remove container, image, volumes, and cache"
	@echo "  $(YELLOW)make prune$(NC)        - Remove all unused Docker resources"
	@echo "  $(YELLOW)make rebuild$(NC)      - Rebuild without cache and run"
	@echo "  $(YELLOW)make dev$(NC)          - Run with volume mount for development"

# Build Docker image
.PHONY: build
build:
	@echo "$(GREEN)Building Docker image $(IMAGE_NAME)...$(NC)"
	docker build -t $(IMAGE_NAME) -f $(DOCKER_FILE) .
	@echo "$(GREEN)✅ Build complete$(NC)"

# Build without cache
.PHONY: build-no-cache
build-no-cache:
	@echo "$(GREEN)Building Docker image without cache...$(NC)"
	docker build --no-cache -t $(IMAGE_NAME) -f $(DOCKER_FILE) .
	@echo "$(GREEN)✅ Build complete$(NC)"

# Run container (foreground)
.PHONY: run
run: stop
	@echo "$(GREEN)Running container $(CONTAINER_NAME) in foreground...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	docker run --rm -p $(PORT_HOST):$(PORT_CONTAINER) --name $(CONTAINER_NAME) $(IMAGE_NAME)

# Run container in background (detached)
.PHONY: run-detached
run-detached: stop
	@echo "$(GREEN)Running container $(CONTAINER_NAME) in background...$(NC)"
	docker run -d --rm -p $(PORT_HOST):$(PORT_CONTAINER) --name $(CONTAINER_NAME) $(IMAGE_NAME)
	@echo "$(GREEN)✅ Container started at http://localhost:$(PORT_HOST)$(NC)"
	@echo "$(YELLOW)View logs: make logs$(NC)"

# Run with volume mount for development (live reload)
.PHONY: dev
dev: stop
	@echo "$(GREEN)Running container in development mode with volume mount...$(NC)"
	docker run --rm -p $(PORT_HOST):$(PORT_CONTAINER) \
		-v $(PWD)/src:/app/src \
		--name $(CONTAINER_NAME) \
		$(IMAGE_NAME)

# Stop container
.PHONY: stop
stop:
	@echo "$(YELLOW)Stopping container $(CONTAINER_NAME)...$(NC)"
	-docker stop $(CONTAINER_NAME) 2>/dev/null || true
	@echo "$(GREEN)✅ Container stopped$(NC)"

# Restart container
.PHONY: restart
restart: stop run-detached
	@echo "$(GREEN)✅ Container restarted$(NC)"

# View logs
.PHONY: logs
logs:
	@echo "$(GREEN)Showing logs for $(CONTAINER_NAME):$(NC)"
	docker logs $(CONTAINER_NAME)

# Follow logs in real-time
.PHONY: logs-follow
logs-follow:
	@echo "$(GREEN)Following logs for $(CONTAINER_NAME) (Ctrl+C to exit):$(NC)"
	docker logs -f $(CONTAINER_NAME)

# Open shell in container
.PHONY: shell
shell:
	@echo "$(GREEN)Opening shell in container $(CONTAINER_NAME)...$(NC)"
	docker exec -it $(CONTAINER_NAME) /bin/bash || docker exec -it $(CONTAINER_NAME) /bin/sh

# Show container status
.PHONY: status
status:
	@echo "$(GREEN)Container status:$(NC)"
	docker ps --filter "name=$(CONTAINER_NAME)"

# List all containers
.PHONY: ps
ps:
	@echo "$(GREEN)All containers:$(NC)"
	docker ps -a

# Remove container (even if running)
.PHONY: remove
remove: stop
	@echo "$(YELLOW)Removing container $(CONTAINER_NAME)...$(NC)"
	-docker rm $(CONTAINER_NAME) 2>/dev/null || true
	@echo "$(GREEN)✅ Container removed$(NC)"

# Remove image
.PHONY: remove-image
remove-image:
	@echo "$(YELLOW)Removing image $(IMAGE_NAME)...$(NC)"
	-docker rmi $(IMAGE_NAME) 2>/dev/null || true
	@echo "$(GREEN)✅ Image removed$(NC)"

# Clean: remove container and image
.PHONY: clean
clean: remove remove-image
	@echo "$(GREEN)✅ Cleanup complete (container + image)$(NC)"

# Clean all: remove container, image, volumes, and build cache
.PHONY: clean-all
clean-all: clean
	@echo "$(YELLOW)Removing volumes and build cache...$(NC)"
	-docker volume prune -f
	-docker builder prune -f
	@echo "$(GREEN)✅ Complete cleanup finished$(NC)"

# Prune all unused Docker resources (caution!)
.PHONY: prune
prune:
	@echo "$(RED)⚠️  This will remove ALL unused containers, networks, images, and volumes.$(NC)"
	@echo "$(RED)Are you sure? Type 'yes' to continue:$(NC)" \
	&& read answer \
	&& if [ "$$answer" = "yes" ]; then \
		docker system prune -a --volumes -f; \
		echo "$(GREEN)✅ Prune complete$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

# Rebuild without cache and run
.PHONY: rebuild
rebuild: clean build-no-cache run-detached
	@echo "$(GREEN)✅ Rebuild complete. Container running at http://localhost:$(PORT_HOST)$(NC)"

# Show container resource usage
.PHONY: stats
stats:
	@echo "$(GREEN)Container stats (Ctrl+C to exit):$(NC)"
	docker stats $(CONTAINER_NAME)

# Copy logs to file
.PHONY: save-logs
save-logs:
	@echo "$(GREEN)Saving logs to logs_$(shell date +%Y%m%d_%H%M%S).txt$(NC)"
	docker logs $(CONTAINER_NAME) > logs_$(shell date +%Y%m%d_%H%M%S).txt 2>&1

# Check Docker daemon status
.PHONY: docker-status
docker-status:
	@echo "$(GREEN)Checking Docker daemon...$(NC)"
	@docker info > /dev/null 2>&1 && echo "$(GREEN)✅ Docker is running$(NC)" || echo "$(RED)❌ Docker is not running$(NC)"

# Display image info
.PHONY: image-info
image-info:
	@echo "$(GREEN)Image information:$(NC)"
	docker images $(IMAGE_NAME)

# Export image to tar file
.PHONY: export-image
export-image:
	@echo "$(GREEN)Exporting image to $(IMAGE_NAME).tar...$(NC)"
	docker save $(IMAGE_NAME) -o $(IMAGE_NAME).tar
	@echo "$(GREEN)✅ Image exported to $(IMAGE_NAME).tar$(NC)"

# Import image from tar file
.PHONY: import-image
import-image:
	@echo "$(GREEN)Importing image from $(IMAGE_NAME).tar...$(NC)"
	docker load -i $(IMAGE_NAME).tar
	@echo "$(GREEN)✅ Image imported$(NC)"

# Run container with custom port
.PHONY: run-custom-port
run-custom-port:
	@echo "$(GREEN)Enter custom host port:$(NC)" \
	&& read custom_port \
	&& echo "$(YELLOW)Running on port $$custom_port...$(NC)" \
	&& docker run --rm -p $$custom_port:$(PORT_CONTAINER) --name $(CONTAINER_NAME) $(IMAGE_NAME)

# Health check
.PHONY: health
health:
	@echo "$(GREEN)Checking health endpoint...$(NC)"
	@curl -s http://localhost:$(PORT_HOST)/health || echo "$(RED)❌ Container not responding$(NC)"

# Quick start (build + run)
.PHONY: start
start: build run

# Quick start in background
.PHONY: start-detached
start-detached: build run-detached

# Development mode with auto-restart on code changes
.PHONY: dev-watch
dev-watch: stop
	@echo "$(GREEN)Running in development watch mode...$(NC)"
	docker run --rm -p $(PORT_HOST):$(PORT_CONTAINER) \
		-v $(PWD)/src:/app/src \
		-e UVICORN_RELOAD=true \
		--name $(CONTAINER_NAME) \
		$(IMAGE_NAME) \
		uv run uvicorn --app-dir src --host 0.0.0.0 --port 8000 --reload main:app