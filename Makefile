.PHONY: run-setup
run-setup:
	python examples/invoke_function.py setup

.PHONY: run-invoke
run-invoke:
	python examples/invoke_function.py invoke

.PHONY: run-teardown
run-teardown:
	python examples/invoke_function.py teardown
