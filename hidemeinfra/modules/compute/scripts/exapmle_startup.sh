#!/bin/bash

# Define variables with defaults (will be overridden by terraform)
# Sensitive defaults are replaced with placeholders
if [ -z "$port" ]; then
  port=8000
fi
if [ -z "$go_port" ]; then
  go_port=8080
fi
if [ -z "$env" ]; then
  env="dev" # Example: dev, staging, prod
fi
if [ -z "$branch" ]; then
  branch="main"
fi
if [ -z "$dbuser" ]; then
  dbuser="hidemedba"
fi
if [ -z "$dbpass" ]; then
  dbpass="YOUR_DB_PASSWORD" # Placeholder - Set via Terraform variable
fi
if [ -z "$dbname" ]; then
  dbname="hide-me-db"
fi
if [ -z "$dbconn" ]; then
  dbconn="" # Connection string if needed
fi
if [ -z "$dbport" ]; then
  dbport="5432"
fi
if [ -z "$dbhost" ]; then
  dbhost="YOUR_PRIVATE_DB_HOST_IP" # Placeholder - Set via Terraform variable
fi
if [ -z "$gemini_api_key" ]; then
  gemini_api_key="YOUR_GEMINI_API_KEY" # Placeholder - Set via Terraform variable
fi
if [ -z "$repo" ]; then
  repo="git@github.com:YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git" # Placeholder
fi
if [ -z "$go_repo" ]; then
  go_repo="git@github.com:YOUR_GITHUB_USERNAME/YOUR_GO_REPO_NAME.git" # Placeholder
fi
if [ -z "$domain" ]; then
  domain="api.yourdomain.com" # Placeholder
fi
if [ -z "$go_domain" ]; then
  go_domain="goapi.yourdomain.com" # Placeholder
fi

echo "Starting setup for environment: $env, branch: $branch"

#############################################
# PHASE 1: System Preparation and Software Installation
#############################################

echo "Phase 1: System preparation and software installation"

# Update the system
echo "Updating system packages..."
sudo apt-get update

# Install dependencies
echo "Installing dependencies..."
sudo apt-get install -y ca-certificates curl ufw nginx git apt-transport-https gnupg

# Install Google Cloud SDK if not present
if ! command -v gcloud &> /dev/null; then
  echo "Installing Google Cloud SDK..."
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
  sudo apt-get update && sudo apt-get install -y google-cloud-sdk
fi

echo "Expanding System Limits"
echo "Configuring system limits for large connections..."
sudo tee /etc/sysctl.d/99-network-tuning.conf > /dev/null << EOF
fs.file-max = 65535
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.optmem_max = 65536
net.ipv4.tcp_mem = 8388608 12582912 16777216
net.core.somaxconn = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_keepalive_time = 1800
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 10
net.core.netdev_max_backlog = 10000
EOF

# Apply the new sysctl settings
sudo sysctl --system
sudo snap install go --classic


# Adjust Docker settings for long-running containers
echo "Configuring Docker for long-running containers..."
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65536,
      "Soft": 65536
    }
  },
  "live-restore": true,
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
EOF

# Restart Docker to apply the changes
sudo systemctl restart docker

# Install Docker
echo "Installing Docker..."
sudo apt-get remove -y docker docker-engine docker.io containerd runc || true
sudo apt-get install -y docker.io

# Install Docker Compose
echo "Installing Docker Compose..."
sudo apt-get install -y docker-compose

# Ensure Docker is running
sudo systemctl enable docker
sudo systemctl start docker

#############################################
# PHASE 2: GitHub Authentication and Repositories Clone
#############################################

echo "Phase 2: GitHub authentication and repository clone"

# Clean up existing directories if they exist
if [ -d "/opt/hide-me" ]; then
  echo "Cleaning up existing hide-me directory..."
  sudo rm -rf /opt/hide-me
fi


# Create application directories
echo "Creating application directories..."
sudo mkdir -p /opt/hide-me
sudo chown -R $(whoami):$(whoami) /opt/hide-me

# Extract repository owner and name for better URL construction
REPO_OWNER="YOUR_GITHUB_USERNAME" # Placeholder
REPO_NAME="YOUR_REPO_NAME" # Placeholder
CLONE_SUCCESS=0
# Securely retrieve GitHub token from Secret Manager
echo "Fetching GitHub token from Secret Manager..."
GITHUB_TOKEN=$(gcloud secrets versions access latest --secret="hide-me-github-token-${env}" 2>/dev/null)

if [ ! -z "$GITHUB_TOKEN" ]; then
  echo "Retrieved GitHub token successfully."

  # Use the token securely without exposing it in logs
  echo "Cloning repository using token authentication..."
  # The set +x prevents the token from being logged
  set +x
  if git clone "https://${GITHUB_TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
    set -x  # Turn logging back on
    echo "Repository cloned successfully with token!"
    CLONE_SUCCESS=0
  else
    set -x  # Turn logging back on
    echo "Token-based clone failed. Trying SSH..."
    CLONE_SUCCESS=1
  fi
else
  echo "Failed to retrieve GitHub token. Trying SSH key authentication..."
  CLONE_SUCCESS=1
fi

# If token-based clone failed, try SSH key authentication
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "Setting up SSH for GitHub..."

  # Fetch the SSH key from Secret Manager
  if SSH_KEY=$(gcloud secrets versions access latest --secret="hide-me-github-ssh-key-${env}" 2>/dev/null) && [ ! -z "$SSH_KEY" ]; then
    echo "Retrieved SSH key successfully."

    # Set up SSH configuration securely
    mkdir -p ~/.ssh
    echo "$SSH_KEY" > ~/.ssh/id_github
    chmod 600 ~/.ssh/id_github

    # Configure SSH to use this key for GitHub
    cat > ~/.ssh/config << EOF
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_github
  StrictHostKeyChecking no
EOF
    chmod 600 ~/.ssh/config

    # Try cloning with SSH
    if git clone "git@github.com:${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
      echo "Repository cloned successfully with SSH!"
      CLONE_SUCCESS=0
    else
      echo "SSH clone failed. Trying public HTTPS clone..."
      CLONE_SUCCESS=1
    fi
  else
    echo "Failed to retrieve SSH key. Trying public HTTPS clone..."
    CLONE_SUCCESS=1
  fi
fi

# Last resort - try public HTTPS if it's a public repository
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "Trying public HTTPS clone as last resort..."
  if git clone "https://github.com/${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
    echo "Repository cloned successfully with public HTTPS!"
    CLONE_SUCCESS=0
  else
    echo "All clone attempts failed."
    CLONE_SUCCESS=1
  fi
fi

# If all cloning methods failed, create minimal structure
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "All GitHub authentication methods failed. Creating minimal structure..."

  # Create minimal application structure
  mkdir -p /opt/hide-me/backend/html/status

  # Create a simple docker-compose.yml file
  cat > /opt/hide-me/backend/docker-compose.yml << EOF
version: '3'
services:
  app:
    image: nginx:alpine
    ports:
      - "${port}:80"
    volumes:
      - ./html:/usr/share/nginx/html
EOF

  # Create basic HTML files
  cat > /opt/hide-me/backend/html/index.html << EOF
<!DOCTYPE html>
<html>
<head>
  <title>Hide Me App</title>
</head>
<body>
  <h1>Hide Me Application</h1>
  <p>The application is running.</p>
  <p>GitHub repository access failed. This is a fallback page.</p>
</body>
</html>
EOF

  echo '{"status":"ok","repository":"access_failed"}' > /opt/hide-me/backend/html/status/index.html
fi

#############################################
# PHASE 3: Application Configuration
#############################################

echo "Phase 3: Application configuration"

# Set up environment variables for main backend
cd /opt/hide-me/backend
echo "Creating .env file for main backend..."

cat > .env << EOF
GEMINI_API_KEY=${gemini_api_key}
EOF

# Set up environment variables for Go backend
cd /opt/hide-me/gobackend
echo "Creating .env file for Go backend..."

cat > .env << EOF
APP_ENV=${env}
DB_HOST=${dbhost}
DB_PORT=${dbport}
DB_NAME=${dbname}
DB_USER=${dbuser}
DB_PASSWORD=${dbpass}
SERVER_HOST=0.0.0.0
SERVER_PORT=${go_port}
DB_CONNECTION=${dbconn}
EOF



  # Create a basic config.yaml for Go app (with placeholders for sensitive defaults)
cat > /opt/hide-me/gobackend/internal/config/config.yaml << EOF
app:
  environment: ${env} # Set dynamically
  name: HideMe
  version: 1.0.0

server:
  host: "127.0.0.1"
  port: ${go_port} # Set dynamically
  read_timeout: 15s
  write_timeout: 10s
  shutdown_timeout: 30s

database:
  host: "${dbhost}" # Set dynamically
  port: ${dbport} # Set dynamically
  name: ${dbname} # Set dynamically
  user: ${dbuser} # Set dynamically
  password: ${dbpass} # Set dynamically
  max_conns: 20
  min_conns: 5

jwt:
  secret: "YOUR_JWT_SECRET_KEY" # Placeholder - Should be managed securely
  expiry: 15m
  refresh_expiry: 168h
  issuer: "hideme-api"

api_key:
  default_expiry: 2160h

logging:
  level: info
  format: json
  request_log: true

cors:
  allowed_origins:
    - "*" # Adjust for production
  allow_credentials: true

password_hash:
  memory: 16384
  iterations: 1
  parallelism: 2
  salt_length: 16
  key_length: 32
EOF



# Stop any running containers
echo "Stopping any running containers..."
sudo docker ps -q | xargs -r sudo docker stop || true

# Build and start Docker containers for main backend
echo "Building and starting Docker containers for main backend..."
cd /opt/hide-me/backend
sudo docker-compose build
sudo docker-compose up -d

# Build and start Docker containers for Go backend
echo "Building and starting Docker containers for Go backend..."
cd /opt/hide-me/gobackend
sudo go mod tidy
sudo go mod download
sudo docker-compose build
sudo docker-compose up -d

#############################################
# PHASE 4: Nginx Configuration for Backend Services
#############################################

echo "Phase 4: Nginx configuration"

# Make sure Nginx is stopped before reconfiguring
sudo systemctl stop nginx || true

# Remove any existing configuration
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-available/backend
sudo rm -f /etc/nginx/sites-available/gobackend

# Create a new Nginx configuration for the main backend
MAIN_NGINX_CONF="/etc/nginx/sites-available/backend"

sudo tee $MAIN_NGINX_CONF > /dev/null << EOF
server {
    listen 80;
    server_name ${domain}; # Set dynamically

    large_client_header_buffers 8 32k;
    client_max_body_size 100M;
    proxy_connect_timeout 1200s;
    proxy_send_timeout 1200s;
    proxy_read_timeout 1200s;
    send_timeout 1200s;
    keepalive_timeout 1200s;

    location / {
        proxy_pass http://127.0.0.1:${port}; # Set dynamically
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 1200s;
        proxy_send_timeout 1200s;
        proxy_read_timeout 1200s;
        proxy_buffers 16 16k;
        proxy_buffer_size 32k;
        proxy_request_buffering on;
        proxy_buffering on;
        proxy_busy_buffers_size 64k;
        proxy_temp_file_write_size 64k;
    }

    location /static/ {
        alias /opt/hide-me/backend/static/;
        expires 30d;
    }

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }
}
EOF

# Create a new Nginx configuration for the Go backend
GO_NGINX_CONF="/etc/nginx/sites-available/gobackend"

sudo tee $GO_NGINX_CONF > /dev/null << EOF
server {
    listen 80;
    server_name ${go_domain}; # Set dynamically

    large_client_header_buffers 4 16k;

    location / {
        proxy_pass http://127.0.0.1:${go_port}; # Set dynamically
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_cookie_path / "/";
        proxy_cookie_domain localhost ${go_domain};
        proxy_pass_header Set-Cookie;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_buffers 8 16k;
        proxy_buffer_size 32k;
    }

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }
}
EOF

# Create a default configuration for handling unknown domains
DEFAULT_NGINX_CONF="/etc/nginx/sites-available/default"

sudo tee $DEFAULT_NGINX_CONF > /dev/null << EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }

    location / {
        return 444;
    }
}
EOF

# Enable the configurations
sudo ln -sf $MAIN_NGINX_CONF /etc/nginx/sites-enabled/
sudo ln -sf $GO_NGINX_CONF /etc/nginx/sites-enabled/
sudo ln -sf $DEFAULT_NGINX_CONF /etc/nginx/sites-enabled/

# Test and start Nginx
echo "Testing Nginx configuration..."
sudo nginx -t
sudo systemctl start nginx

#############################################
# PHASE 5: Firewall Configuration
#############################################

echo "Phase 5: Firewall configuration"

# Configure UFW firewall
echo "Configuring firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'Allow SSH'
sudo ufw allow 80/tcp comment 'Allow HTTP'
sudo ufw allow 443/tcp comment 'Allow HTTPS'
sudo ufw allow ${port}/tcp comment 'Allow main application port'
sudo ufw allow ${go_port}/tcp comment 'Allow Go application port'
sudo ufw --force enable

#############################################
# PHASE 6: Final Verification
#############################################

echo "Phase 6: Final verification"

# Create a health check script
echo "Creating health check script..."
cat > /opt/hide-me/health-check.sh << EOF
#!/bin/bash
# Health check script

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
  echo "Docker is not running"
  exit 1
fi

# Check if Nginx is running
if ! systemctl is-active --quiet nginx; then
  echo "Nginx is not running"
  exit 1
fi

# Check if the main backend container is running
if ! sudo docker ps --filter "name=backend_app" --filter "status=running" --format '{{.Names}}' | grep -q "backend_app"; then
  echo "Main backend container is not running"
  exit 1
fi

# Check if the Go backend container is running
if ! sudo docker ps --filter "name=gobackend_app" --filter "status=running" --format '{{.Names}}' | grep -q "gobackend_app"; then
  echo "Go backend container is not running"
  exit 1
fi

# Check main backend status endpoint
if ! curl -s --fail http://127.0.0.1:${port}/status > /dev/null; then
  echo "Main backend status endpoint failed"
  exit 1
fi

# Check Go backend status endpoint
if ! curl -s --fail http://127.0.0.1:${go_port}/status > /dev/null; then
  echo "Go backend status endpoint failed"
  exit 1
fi

echo "All checks passed. System is healthy."
exit 0
EOF

chmod +x /opt/hide-me/health-check.sh

echo "Setup complete."
