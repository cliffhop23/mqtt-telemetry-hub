.PHONY: install run test lint docker

install:
	pip install -r requirements.txt -r requirements-dev.txt

run:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check .

docker:
	docker compose up --build
