seed:
	docker compose run --rm backend python -m app.cli seed
demo:
	docker compose run --rm backend python -m app.cli demo
test:
	cd backend && python -m pytest -q tests
eval:
	python eval/run.py
