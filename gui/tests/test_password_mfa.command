#!/bin/zsh
cd -- "${0:A:h}" || exit 1
exec ./planit-sandbox/.venv/bin/python ./test_password_mfa.py
