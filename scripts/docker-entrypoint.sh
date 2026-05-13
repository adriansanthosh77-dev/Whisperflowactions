#!/bin/bash
set -e

echo "Waiting for Ollama..."
until curl -s http://ollama:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama ready."

MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
if ! curl -s http://ollama:11434/api/tags | grep -q "$MODEL"; then
  echo "Pulling model: $MODEL..."
  curl -X POST http://ollama:11434/api/pull -d "{\"name\": \"$MODEL\"}"
  echo "Model $MODEL pulled."
fi

echo "Starting JARVIS..."
exec python -m core.orchestrator
