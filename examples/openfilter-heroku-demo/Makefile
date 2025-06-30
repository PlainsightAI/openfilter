# Makefile  ──────────────────────────────────────────────────
# Simple task runner for dev & Heroku helpers
.PHONY: help install run dev clean deploy logs heroku-shell

ENVFILE ?= .env      # change if you use .env.local
HEROKU_APP ?= openfilter-demo   # override on CLI if needed

# --- utils --------------------------------------------------
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?##"} {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- local dev ---------------------------------------------
install:  ## pip install deps into current venv
	pip install -r requirements.txt

run:  ## Run app.py (auto-loads .env if present)
	python app.py

run-pipeline:
	openfilter run - VideoIn --sources 'file://./assets/sample-video.mp4!loop' - Webvis --port 8000

# restart helpers
restart:        ## Restart all dynos on Heroku
	heroku ps:restart --app $(HEROKU_APP)

restart-local:  ## Stop any running local app.py and start it again with .env
	@echo "⟲ Restarting local dev server …"
	# Try to kill a previous python app.py (ignore if none running)
	-pkill -f "python app.py" || true
	# Wait a sec so the port frees up
	sleep 1
	# Relaunch with dotenv (needs python-dotenv[cli])
	@which dotenv >/dev/null || pip install python-dotenv[cli]
	dotenv -f $(ENVFILE) -- python app.py

start: ## Start the Heroku app by scaling web dyno back up
	heroku ps:scale web=1 --app $(HEROKU_APP)


stop: ## Stop the Heroku app by scaling dynos to 0
	heroku ps:scale web=0 --app $(HEROKU_APP)

dev:  ## Run app.py with .env loaded via dotenv-cli
	@which dotenv >/dev/null || pip install python-dotenv[cli]
	dotenv -f $(ENVFILE) -- python app.py

clean: ## Remove __pycache__ and *.pyc
	find . -name '__pycache__' -type d -exec rm -rf {} +
	find . -name '*.py[co]'     -exec rm -f  {} +

# --- Heroku helpers ----------------------------------------
deploy: ## Push current branch to Heroku using subtree
	cd ../.. && git subtree push --prefix examples/openfilter-heroku-demo heroku main

logs:   ## Stream Heroku logs
	heroku logs --tail --app $(HEROKU_APP)
	
logs-dyno:
	heroku logs --num 1500 --ps web --app $(HEROKU_APP)

heroku-shell: ## One-off dyno with your env
	heroku run bash --app $(HEROKU_APP)
