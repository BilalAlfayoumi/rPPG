.PHONY: install install-dev sync run dev stop test test-signal test-face bench bench-selftest lint format docker-build docker-up docker-down docker-logs docker-shell clean help

# ── Environnement ──────────────────────────────────────────────────────────────

install:        ## Installe les dépendances (prod)
	uv sync --no-dev

install-dev:    ## Installe les dépendances + outils dev
	uv sync --all-extras
	uv pip install opencv-python-headless --force-reinstall

sync:           ## Synchronise l'env uv avec pyproject.toml
	uv sync

# ── Développement local ────────────────────────────────────────────────────────

stop:           ## Arrête tout serveur uvicorn en cours
	@pkill -f "uvicorn backend.main" 2>/dev/null && echo "Serveur(s) arrêté(s)" || echo "Aucun serveur actif"

run: stop       ## Lance le serveur FastAPI (prod)
	uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

dev: stop       ## Lance le serveur FastAPI avec hot-reload (surveille backend/ et frontend/ uniquement)
	uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
		--reload \
		--reload-dir backend --reload-dir frontend \
		--reload-include '*.py' --reload-include '*.html' \
		--reload-include '*.js' --reload-include '*.css'

# ── Tests ──────────────────────────────────────────────────────────────────────

test:           ## Lance tous les tests
	uv run pytest tests/ -v

test-signal:    ## Tests du pipeline signal uniquement
	uv run pytest tests/test_bpm_estimator.py tests/test_signal_processor.py -v

test-face:      ## Tests de la détection visage
	uv run pytest tests/test_face_roi.py -v

bench:          ## Benchmark UBFC-rPPG (data/UBFC) ou self-test si absent
	uv run python tests/bench_ubfc.py --data data/UBFC

bench-selftest: ## Valide la mécanique du benchmark sans dataset (signal synthétique)
	uv run python tests/bench_ubfc.py --self-test

# ── Docker ─────────────────────────────────────────────────────────────────────

docker-build:   ## Build l'image Docker
	docker build -t rppg .

docker-up:      ## Démarre le conteneur avec docker-compose
	docker compose up -d

docker-down:    ## Arrête le conteneur
	docker compose down

docker-logs:    ## Affiche les logs du conteneur
	docker compose logs -f rppg

docker-shell:   ## Shell interactif dans le conteneur
	docker compose exec rppg bash

# ── Qualité ────────────────────────────────────────────────────────────────────

lint:           ## Vérifie le code (ruff)
	uv run ruff check backend/ tests/

format:         ## Formate le code (ruff)
	uv run ruff format backend/ tests/

# ── Utilitaires ────────────────────────────────────────────────────────────────

clean:          ## Supprime les caches Python et pytest
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	echo "Nettoyage terminé"

help:           ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
