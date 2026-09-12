.PHONY: test lint audit demo web docker-build clean

test:
	python -m pytest tests/ -q

lint:
	ruff check ragevda tests || true

audit:
	pip-audit || true

demo:
	python -m ragevda.cli run -c examples/offline_demo/config.yaml

web:
	python -m ragevda.cli web --port 9000

docker-build:
	docker build -t ragevda .

clean:
	rm -rf web_output/jobs/temp ragevda_output
