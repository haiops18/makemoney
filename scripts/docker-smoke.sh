#!/usr/bin/env sh
set -eu

cleanup() {
  docker compose down --remove-orphans
}

trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  cp .env.example .env
fi

docker compose up --build --detach

attempt=0
until curl --fail --silent --show-error http://localhost:8000/health/ready >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    docker compose ps
    docker compose logs --tail=120
    exit 1
  fi
  sleep 2
done

curl --fail --silent --show-error --output /dev/null http://localhost:3000/
docker compose ps
