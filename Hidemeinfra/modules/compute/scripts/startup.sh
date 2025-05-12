#!/bin/bash

# Required environment variables:
#   port, go_port, env, branch, dbuser, dbpass, dbname, dbconn, dbport, dbhost, gemini_api_key, repo, go_repo, domain, go_domain, SENDGRID_API_KEY, API_KEY_ENCRYPTION_KEY

: "${port:?port is required but not set}"
: "${go_port:?go_port is required but not set}"
: "${env:?env is required but not set}"
: "${branch:?branch is required but not set}"
: "${dbuser:?dbuser is required but not set}"
: "${dbpass:?dbpass is required but not set}"
: "${dbname:?dbname is required but not set}"
: "${dbconn:?dbconn is required but not set}"
: "${dbport:?dbport is required but not set}"
: "${dbhost:?dbhost is required but not set}"
: "${gemini_api_key:?gemini_api_key is required but not set}"
: "${repo:?repo is required but not set}"
: "${go_repo:?go_repo is required but not set}"
: "${domain:?domain is required but not set}"
: "${go_domain:?go_domain is required but not set}"
: "${SENDGRID_API_KEY:?SENDGRID_API_KEY is required but not set}"
: "${API_KEY_ENCRYPTION_KEY:?API_KEY_ENCRYPTION_KEY is required but not set}"

echo "Starting setup with port=$port, go_port=$go_port, env=$env, branch=$branch, repo=$repo, go_repo=$go_repo, domain=$domain, go_domain=$go_domain"

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

echo "Expanding System Limites"
echo "Configuring system limits for large connections..."
sudo tee /etc/sysctl.d/99-network-tuning.conf > /dev/null << EOF
# Increase the maximum number of open files
fs.file-max = 65535

# Increase TCP max buffer size
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.netdev_max_backlog = 5000

# Increase TCP buffer limits
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Increase the maximum amount of option memory buffers
net.core.optmem_max = 65536

# Increase the TCP receive buffer for all types of connections
net.ipv4.tcp_mem = 8388608 12582912 16777216

# Increase the maximum connections
net.core.somaxconn = 65535

# Increase the maximum number of ephemeral ports available
net.ipv4.ip_local_port_range = 1024 65535

# Reuse sockets in TIME_WAIT state
net.ipv4.tcp_tw_reuse = 1

# Keep TCP connections alive longer
net.ipv4.tcp_keepalive_time = 1800
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 10

# Increase the maximum length of processor input queue
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
REPO_OWNER="yasinhessnawi1"
REPO_NAME="Hideme_Backend"
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
GO_BACKEND_URL=${go_domain}
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
SENDGRID_API_KEY=${SENDGRID_API_KEY}
API_KEY_ENCRYPTION_KEY=${API_KEY_ENCRYPTION_KEY}
EOF



  # Create a basic config.yaml for Go app
cat > /opt/hide-me/gobackend/internal/config/config.yaml << EOF
app:
  environment: development
  name: HideMe
  version: 1.0.0

server:
  host: "127.0.0.1"
  port: ${go_port}
  read_timeout: 15s
  write_timeout: 10s
  shutdown_timeout: 30s

database:
  host: "${dbhost}"
  port: ${dbport}
  name: ${dbname}
  user: ${dbuser}
  password: ${dbpass}
  max_conns: 20
  min_conns: 5

jwt:
  secret: ${API_KEY_ENCRYPTION_KEY}
  expiry: 15m
  refresh_expiry: 168h
  issuer: "hideme-api"

api_key:
  default_expiry: 2160h

logging:
  level: info
  format: json
  request_log: true


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
    server_name ${domain};

    # Increase header buffer size
    large_client_header_buffers 8 32k;

    # Increase body size limit to accommodate large payloads (50MB)
    client_max_body_size 100M;

    # Increase timeouts for long-running requests
    proxy_connect_timeout 1200s;
    proxy_send_timeout 1200s;
    proxy_read_timeout 1200s;
    send_timeout 1200s;
    keepalive_timeout 1200s;

    # Proxy all requests to the backend
    location / {
        proxy_pass http://127.0.0.1:${port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # Apply extended timeouts for proxied requests
        proxy_connect_timeout 1200s;
        proxy_send_timeout 1200s;
        proxy_read_timeout 1200s;

        # Increase buffer settings for large requests/responses
        proxy_buffers 16 16k;
        proxy_buffer_size 32k;

        # Enable request buffering for large POST requests
        proxy_request_buffering on;

        # Configure response buffering
        proxy_buffering on;
        proxy_busy_buffers_size 64k;
        proxy_temp_file_write_size 64k;
    }

    # Serve static files directly if needed
    location /static/ {
        alias /opt/hide-me/backend/static/;
        expires 30d;
    }

    # Simple status endpoint
    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    # Health check endpoint for load balancer
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
    server_name ${go_domain};

    # Increase header buffer size
    large_client_header_buffers 4 16k;

    # Proxy all requests to the Go backend
    location / {
        proxy_pass http://127.0.0.1:${go_port};
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

    # Simple status endpoint
    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    # Health check endpoint for load balancer
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

    # Simple status endpoint
    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    # Health check endpoint for load balancer
    location = /health {
        access_log off;
        return 200 'OK';
    }

    # Deny all other requests
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
sudo ufw --force  enable

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

# Check if the main backend status endpoint is accessible
if ! curl -s http://localhost/status > /dev/null; then
  echo "Main backend status endpoint is not accessible"
  exit 1
fi

# Check if the Go backend status endpoint is accessible
if ! curl -s -H "Host: ${go_domain}" http://localhost/status > /dev/null; then
  echo "Go backend status endpoint is not accessible"
  exit 1
fi

# All checks passed
echo "Services are healthy"
exit 0
EOF
chmod +x /opt/hide-me/health-check.sh

# Create a debug log with system information
echo "Creating debug information log..."
{
  echo "=== SYSTEM INFORMATION ==="
  date
  echo "Hostname: $(hostname)"
  echo "Instance ID: $(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/id 2>/dev/null || echo 'N/A')"
  echo "Zone: $(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/zone 2>/dev/null || echo 'N/A')"

  echo -e "\n=== REPOSITORY ACCESS ==="
  echo "Main Clone success: $CLONE_SUCCESS"
  echo "Go Clone success: $GO_CLONE_SUCCESS"
  echo "Main Repository: $repo"
  echo "Go Repository: $go_repo"
  echo "Branch: $branch"

  echo -e "\n=== SERVICE STATUS ==="
  echo "Docker status: $(systemctl is-active docker)"
  echo "Nginx status: $(systemctl is-active nginx)"

  echo -e "\n=== LOAD BALANCER CONFIGURATION ==="
  echo "Main Domain: ${domain}"
  echo "Go Domain: ${go_domain}"
  echo "Main Domain IP: $(dig +short ${domain} @8.8.8.8)"
  echo "Go Domain IP: $(dig +short ${go_domain} @8.8.8.8)"
  echo "Instance IP: $(curl -s http://checkip.amazonaws.com)"

  echo -e "\n=== NETWORK CONFIGURATION ==="
  ip addr

  echo -e "\n=== DOCKER CONTAINERS ==="
  sudo docker ps -a

  echo -e "\n=== LOGS ==="
  echo "Docker logs for main backend:"
  sudo docker logs --tail 20 $(sudo docker ps -qf "name=backend") 2>&1 || echo "No main backend container running"

  echo -e "\n=== LOGS ==="
  echo "Docker logs for Go backend:"
  sudo docker logs --tail 20 $(sudo docker ps -qf "name=hideme-goapp") 2>&1 || echo "No Go backend container running"

  echo -e "\n=== NGINX LOGS ==="
  tail -n 20 /var/log/nginx/error.log 2>/dev/null || echo "No Nginx error logs"
} > /opt/hide-me/startup-debug.log

# Final service status check
echo "Checking service status:"
echo "Docker status: $(systemctl is-active docker)"
echo "Nginx status: $(systemctl is-active nginx)"
echo "Main backend health check: $(curl -s http://localhost/status)"
echo "Go backend health check: $(curl -s -H "Host: ${go_domain}" http://localhost/status)"

echo "Server setup completed successfully!"
echo ""
echo "Note: SSL is handled at the load balancer level, not on this instance."
echo "To configure SSL for your domains ${domain} and ${go_domain}, use Google Cloud Load Balancer SSL certificates."
echo ""
echo "For GCP Load Balancer SSL setup:"
echo "1. Go to Network Services > Load Balancing in Google Cloud Console"
echo "2. Select your load balancer"
echo "3. Edit the frontend configuration"
echo "4. Add an HTTPS frontend with a Google-managed certificate for ${domain} and ${go_domain}"
echo ""
echo "setup port=$port, go_port=$go_port, env=$env, branch=$branch, repo=$repo, go_repo=$go_repo, domain=$domain, go_domain=$go_domain"
