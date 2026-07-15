PACKAGE=
PARAMS?=

CURRENT_DIR=$(shell pwd)

## Help
help:
	@printf "Available targets:\n\n"
	@awk '/^[a-zA-Z\-\_0-9%:\\]+/ { \
		helpMessage = match(lastLine, /^## (.*)/); \
		if (helpMessage) { \
		helpCommand = $$1; \
		helpMessage = substr(lastLine, RSTART + 3, RLENGTH); \
	gsub("\\\\", "", helpCommand); \
	gsub(":+$$", "", helpCommand); \
		printf "  \x1b[32;01m%-35s\x1b[0m %s\n", helpCommand, helpMessage; \
		} \
	} \
	{ lastLine = $$0 }' $(MAKEFILE_LIST) | sort -u
	@printf "\n"

## Lint the Worker source with ruff - gates the deploy targets below.
check/lint:
	UV_PROJECT_ENVIRONMENT=.venv-worker uv run ruff check src

## Clean merged branches and tracking branches deleted from remote
git/cleanup:
	git branch --merged | grep -Ev "(^\*|master|main)" | xargs git branch -d
	git remote prune origin

## Create a local virtualenv with dependencies, for IDE autocomplete on main_telegram_to_mastodon.py
venv/create:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip

## Remove the local virtualenv
venv/clean:
	rm -rf .venv

## Print the install location of a package in the local venv. make venv/locate PACKAGE=telebot
venv/locate:
	.venv/bin/python -c "import $(PACKAGE), os; print(os.path.dirname($(PACKAGE).__file__))"

## Install a package. make venv/locate PACKAGE=pywaybackup
venv/install:
	.venv/bin/pip install $(PACKAGE)

## archiver. Usage: make archiver PARAMS=-h
archiver:
	.venv/bin/archiver --email-result --log-to-file out.log ${PARAMS} 
