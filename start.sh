#!/bin/bash
# Fallback to 8080 if PORT is not set
export PORT=${PORT:-8080}
exec gunicorn -w 1 -b 0.0.0.0:$PORT server:app
