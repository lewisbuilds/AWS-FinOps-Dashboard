# AWS FinOps Dashboard - Development Makefile
# Provides consistent commands for development, testing, and deployment

# Variables
APP_NAME := aws-finops-dashboard
# Pin application version (keep in sync with pyproject.toml [tool.poetry] version)
APP_VERSION := 0.1.0
DOCKER_IMAGE := $(APP_NAME):$(APP_VERSION)
DOCKER_DEV_IMAGE := $(APP_NAME):dev
PORT := 8501
DEV_PORT := 8502

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help install install-dev clean test lint format run run-dev build build-dev docker-run docker-dev logs stop health check-deps security-scan

# Default target
help: ## Show this help message
	@echo "$(BLUE)AWS FinOps Dashboard - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# Development Setup
install: ## Install production dependencies using Poetry
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	poetry install --only=main
	@echo "$(GREEN)Production dependencies installed successfully$(NC)"

install-dev: ## Install all dependencies including development tools
	@echo "$(BLUE)Installing all dependencies...$(NC)"
	poetry install
	@echo "$(GREEN)All dependencies installed successfully$(NC)"

clean: ## Clean up temporary files and caches
	@echo "$(BLUE)Cleaning up temporary files...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	@echo "$(GREEN)Cleanup completed$(NC)"

# Code Quality
test: ## Run test suite
	@echo "$(BLUE)Running test suite...$(NC)"
	poetry run pytest tests/ -v --cov=app --cov-report=term-missing
	@echo "$(GREEN)Tests completed$(NC)"

lint: ## Run code linting
	@echo "$(BLUE)Running code linting...$(NC)"
	poetry run flake8 app/ tests/
	poetry run mypy app/
	@echo "$(GREEN)Linting completed$(NC)"

format: ## Format code using black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black app/ tests/
	poetry run isort app/ tests/
	@echo "$(GREEN)Code formatting completed$(NC)"

security-scan: ## Run security vulnerability scan
	@echo "$(BLUE)Running security scan...$(NC)"
	poetry run bandit -r app/
	poetry run safety check
	@echo "$(GREEN)Security scan completed$(NC)"

# Local Development
run: ## Run application locally with Poetry
	@echo "$(BLUE)Starting AWS FinOps Dashboard on port $(PORT)...$(NC)"
	@echo "$(YELLOW)Access the dashboard at: http://localhost:$(PORT)$(NC)"
	poetry run streamlit run app/streamlit_app.py --server.port=$(PORT)

run-dev: ## Run application in development mode with file watching
	@echo "$(BLUE)Starting AWS FinOps Dashboard in development mode on port $(DEV_PORT)...$(NC)"
	@echo "$(YELLOW)Access the dashboard at: http://localhost:$(DEV_PORT)$(NC)"
	poetry run streamlit run app/streamlit_app.py --server.port=$(DEV_PORT) --server.runOnSave=true

# Docker Operations
build: ## Build production Docker image
	@echo "$(BLUE)Building production Docker image...$(NC)"
	docker build -t $(DOCKER_IMAGE) .
	@echo "$(GREEN)Production image built: $(DOCKER_IMAGE)$(NC)"

build-dev: ## Build development Docker image
	@echo "$(BLUE)Building development Docker image...$(NC)"
	docker build -t $(DOCKER_DEV_IMAGE) --target builder .
	@echo "$(GREEN)Development image built: $(DOCKER_DEV_IMAGE)$(NC)"

docker-run: build ## Build and run application in Docker container
	@echo "$(BLUE)Starting Docker container on port $(PORT)...$(NC)"
	@echo "$(YELLOW)Access the dashboard at: http://localhost:$(PORT)$(NC)"
	docker run -d \
		--name $(APP_NAME) \
		-p $(PORT):8501 \
		--env-file .env \
		$(DOCKER_IMAGE)
	@echo "$(GREEN)Container started successfully$(NC)"

docker-run-profile: build ## Run container mounting host AWS credentials (uses AWS_PROFILE from .env)
	@echo "$(BLUE)Starting container with host AWS credentials mounted...$(NC)"
	@if not exist %USERPROFILE%\.aws ( echo "$(RED)No %USERPROFILE%\.aws directory found – aborting$(NC)" && exit 1 )
	docker run -d \
		--name $(APP_NAME)-profile \
		-p $(PORT):8501 \
		--env-file .env \
		-v %USERPROFILE%\.aws:/app/.aws:ro \
		$(DOCKER_IMAGE)
	@echo "$(GREEN)Container started with mounted credentials (profile mode)$(NC)"

docker-dev: build-dev ## Build and run development container with volume mounting
	@echo "$(BLUE)Starting development Docker container...$(NC)"
	docker run -it --rm \
		-p $(DEV_PORT):8501 \
		-v $(PWD):/app \
		--env-file .env \
		$(DOCKER_DEV_IMAGE) \
		bash

logs: ## Show Docker container logs
	@echo "$(BLUE)Showing container logs...$(NC)"
	docker logs -f $(APP_NAME)

stop: ## Stop and remove Docker container
	@echo "$(BLUE)Stopping Docker container...$(NC)"
	docker stop $(APP_NAME) || true
	docker rm $(APP_NAME) || true
	@echo "$(GREEN)Container stopped and removed$(NC)"

health: ## Check application health
	@echo "$(BLUE)Checking application health...$(NC)"
	@curl -f http://localhost:$(PORT)/_stcore/health || echo "$(RED)Health check failed$(NC)"
	@echo "$(GREEN)Health check completed$(NC)"

# Environment Management
check-deps: ## Check for dependency updates
	@echo "$(BLUE)Checking for dependency updates...$(NC)"
	poetry show --outdated
	@echo "$(GREEN)Dependency check completed$(NC)"

setup-env: ## Setup environment file from template
	@echo "$(BLUE)Setting up environment file...$(NC)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN).env file created from template$(NC)"; \
		echo "$(YELLOW)Please update .env with your AWS credentials$(NC)"; \
	else \
		echo "$(YELLOW).env file already exists$(NC)"; \
	fi

# AWS Operations
aws-validate: ## Validate AWS credentials and permissions
	@echo "$(BLUE)Validating AWS credentials...$(NC)"
	poetry run python -c "from app.aws_session import AWSSessionManager; sm = AWSSessionManager(); print('AWS Connection:', sm.validate_permissions())"
	@echo "$(GREEN)AWS validation completed$(NC)"

# CI/CD Helpers
ci-install: ## Install dependencies for CI environment
	@echo "$(BLUE)Installing dependencies for CI...$(NC)"
	pip install poetry
	poetry config virtualenvs.create false
	poetry install
	@echo "$(GREEN)CI dependencies installed$(NC)"

ci-test: ## Run full test suite for CI
	@echo "$(BLUE)Running full CI test suite...$(NC)"
	make lint
	make test
	make security-scan
	@echo "$(GREEN)CI test suite completed$(NC)"

# Database/Storage Operations (Future)
migrate: ## Run database migrations (placeholder)
	@echo "$(YELLOW)Database migrations not implemented yet$(NC)"

backup: ## Backup application data (placeholder)
	@echo "$(YELLOW)Backup functionality not implemented yet$(NC)"

# Monitoring and Logs
monitor: ## Start monitoring dashboard (placeholder)
	@echo "$(YELLOW)Monitoring dashboard not implemented yet$(NC)"

export-logs: ## Export application logs (placeholder)
	@echo "$(YELLOW)Log export not implemented yet$(NC)"

# Quick Start
quickstart: setup-env install-dev ## Quick setup for new developers
	@echo "$(GREEN)Quick setup completed!$(NC)"
	@echo "$(BLUE)Next steps:$(NC)"
	@echo "  1. Update .env with your AWS credentials"
	@echo "  2. Run 'make aws-validate' to test AWS connection"
	@echo "  3. Run 'make run-dev' to start the development server"
	@echo "  4. Open http://localhost:$(DEV_PORT) in your browser"
