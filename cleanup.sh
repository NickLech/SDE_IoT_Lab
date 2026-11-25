# Post-lab cleanup
set -e
cd "$(dirname "$0")"

docker compose --profile debug down --rmi all

echo "Cleanup completed"