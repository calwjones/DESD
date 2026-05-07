#!/bin/sh

echo "Running migrations..."
python manage.py migrate --noinput

if [ -f purchase_history.csv ]; then
    echo "Seeding demo data from purchase_history.csv..."
    python manage.py seed_orders
else
    echo "No purchase_history.csv found, skipping demo seed."
fi

exec "$@"
