PYTHON ?= python3

.PHONY: test check doctor demo
test:
	$(PYTHON) -m unittest discover -s tests -v
check: test
	$(PYTHON) scripts/check_skill.py
doctor:
	$(PYTHON) -m research_relay doctor
demo:
	$(PYTHON) scripts/demo.py
