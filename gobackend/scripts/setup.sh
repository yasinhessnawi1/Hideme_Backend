# Setup script for HideMe Backend development environment

set -e

# Function to display colorful messages
function log_message() {
  echo -e "\e[34m>>> $1\e[0m"
}

log_message "Setting up HideMe Backend development environment..."

# Check if Go is installed
if ! command -v go &> /dev/null; then
  log_message "Go is not installed. Please install Go 1.18 or higher."
  exit 1
fi

# Check Go version
GO_VERSION=$(go version | grep -oP 'go\K[0-9]+\.[0-9]+')
if (( $(echo "$GO_VERSION < 1.18" | bc -l) )); then
  log_message "Go version $GO_VERSION is installed. Please upgrade to Go 1.18 or higher."
  exit 1
fi

log_message "Go version $GO_VERSION detected."

# Check for PostgreSQL
if ! command -v psql &> /dev/null; then
  log_message "PostgreSQL is not installed. Please install PostgreSQL 13 or higher."
  exit 1
fi

log_message "PostgreSQL detected."

# Set up environment file if it doesn't exist
if [ ! -f .env ]; then
  log_message "Creating .env file from template..."
  cp configs/.env.example .env
  log_message "Please edit .env file with your configuration."
fi

# Create configs directory if it doesn't exist
if [ ! -d configs ]; then
  log_message "Creating configs directory..."
  mkdir -p configs
fi

# Copy config template if it doesn't exist
if [ ! -f configs/config.yaml ]; then
  log_message "Creating config.yaml from template..."
  cp configs/config.yaml.example configs/config.yaml
  log_message "Please edit configs/config.yaml with your configuration."
fi

# Install development tools
log_message "Installing development tools..."
go install github.com/cosmtrek/air@latest
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
go install golang.org/x/tools/cmd/goimports@latest

# Download Go dependencies
log_message "Downloading dependencies..."
go mod download

# Build the application
log_message "Building application..."
go build -o bin/api cmd/api/main.go

# Set up database
log_message "Setting up database..."
if [ -f migrations/setup_db.sql ]; then
  # Load database configuration from .env file
  source .env
  DB_HOST=${DB_HOST:-localhost}
  DB_PORT=${DB_PORT:-5432}
  DB_NAME=${DB_NAME:-hideme}
  DB_USER=${DB_USER:-postgres}
  DB_PASSWORD=${DB_PASSWORD}

  # Create database if it doesn't exist
  log_message "Creating database if it doesn't exist..."
  PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || true

  # Run setup script
  log_message "Running database setup script..."
  PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f migrations/setup_db.sql
else
  log_message "Database setup script not found. Skipping database setup."
fi

# Run migrations
if command -v migrate &> /dev/null; then
  log_message "Running database migrations..."
  source .env
  migrate -path migrations -database "postgres://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME?sslmode=disable" up
else
  log_message "migrate tool not found. Please install it to run migrations."
  log_message "Visit: https://github.com/golang-migrate/migrate"
fi

log_message "Setup completed successfully!"
log_message "You can start the development server with: make run"