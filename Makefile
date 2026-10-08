.PHONY: up down logs migrate makemigrations references seed test lint shell schema

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations

references:
	docker compose exec web python manage.py load_references

seed:
	docker compose exec web python manage.py seed_demo

test:
	docker compose exec web pytest -q

lint:
	docker compose exec web ruff check .

shell:
	docker compose exec web python manage.py shell

schema:
	docker compose exec web python manage.py spectacular --validate --fail-on-warn --file schema.yml
