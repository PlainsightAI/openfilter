.PHONY: env up down

env:  ## write .env from env.example with this machine's timezone
	@cp -n env.example .env 2>/dev/null || true
	@tz=$$(readlink /etc/localtime | sed 's|.*/zoneinfo/||'); \
	  sed -i.bak "s|^TZ=.*|TZ=$$tz|" .env && rm -f .env.bak; \
	  echo "TZ=$$tz"

up: ## run the pipeline
	docker compose up -d && echo "http://localhost:$${WEB_PORT:-8000}/timings"

down: ## stop it
	docker compose down
