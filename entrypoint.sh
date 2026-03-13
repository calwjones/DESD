#!/bin/sh

echo "Running migrations..."
python manage.py migrate --noinput

echo "Loading fixtures...(demo data)"
python manage.py loaddata accounts
python manage.py loaddata producers
python manage.py loaddata products

exec "$@"