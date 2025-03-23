# HideMe Go Backend

## Overview

This repository contains the Go backend service for the HideMe application, a system designed for detecting and redacting sensitive information from documents. The Go backend complements the existing Python backend by handling user authentication, session management, API key verification, and database operations. It serves as the centralized user management system, allowing the Python backend to focus on document processing and sensitive data detection.

## Architecture

The Go backend follows a clean architecture approach with separation of concerns:

- **API Layer**: Handles HTTP requests/responses and route management
- **Service Layer**: Implements business logic and coordinates operations
- **Repository Layer**: Manages data persistence and database interactions
- **Model Layer**: Defines data structures that reflect the database schema
- **Middleware**: Handles cross-cutting concerns like authentication and logging
- **Utilities**: Provides helper functions for common operations

## Package Structure

```
gobackend/
├── cmd/
│   └── api/
│       └── main.go              # Entry point for the application
├── internal/
│   ├── config/                  # Configuration management
│   │   ├── config.go            # Loads and validates configuration
│   │   └── env.go               # Environment variable handling
│   ├── models/                  # Database models matching schema design
│   │   ├── user.go              # User model with methods
│   │   ├── document.go          # Document model
│   │   ├── detection_method.go  # Detection method model
│   │   ├── detected_entity.go   # Detected entity model
│   │   ├── user_setting.go      # User settings model
│   │   ├── model_entity.go      # Model entity model
│   │   ├── search_pattern.go    # Search pattern model
│   │   ├── ban_list.go          # Ban list model
│   │   ├── ban_list_word.go     # Ban list word model
│   │   ├── session.go           # Session management
│   │   └── api_key.go           # API key model
│   ├── database/                # Database connection and operations
│   │   ├── db.go                # DB connection setup and management
│   │   └── operations.go        # Generic CRUD operations
│   ├── repository/              # Repository layer for data access
│   │   ├── user_repository.go   # User data operations
│   │   ├── settings_repository.go # User settings operations
│   │   ├── document_repository.go # Document operations
│   │   ├── ban_list_repository.go # Ban list operations
│   │   ├── pattern_repository.go  # Search pattern operations
│   │   └── api_key_repository.go  # API key operations
│   ├── service/                 # Business logic layer
│   │   ├── auth_service.go      # Authentication service
│   │   ├── user_service.go      # User management service
│   │   ├── settings_service.go  # Settings management service
│   │   └── database_service.go  # Generic database service
│   ├── auth/                    # Authentication logic
│   │   ├── jwt.go               # JWT token generation/validation
│   │   ├── api_key.go           # API key management
│   │   ├── password.go          # Password hashing and validation
│   │   └── middleware.go        # Auth middleware
│   ├── middleware/              # HTTP middleware components
│   │   ├── auth_middleware.go   # Authentication middleware
│   │   ├── logging.go           # Request logging middleware
│   │   └── recovery.go          # Panic recovery middleware
│   ├── handlers/                # HTTP handlers
│   │   ├── auth_handlers.go     # Signup, login, logout
│   │   ├── user_handlers.go     # User CRUD operations
│   │   ├── settings_handlers.go # User settings operations
│   │   └── generic_handlers.go  # Generic DB operations
│   ├── server/                  # HTTP server setup
│   │   ├── server.go            # Server configuration
│   │   └── routes.go            # Route definitions
│   └── utils/                   # Utilities
│       ├── response.go          # Standard response formats
│       ├── validation.go        # Input validation
│       ├── logger.go            # Logging utilities
│       └── errors.go            # Error handling utilities
├── pkg/                         # Reusable packages
│   ├── validator/               # Input validation
│   │   └── validator.go
│   └── security/                # Security utilities
│       └── security.go
├── migrations/                  # Database migrations
├── scripts/                     # Utility scripts
│   ├── setup.sh                 # Development setup script
│   └── seed.go                  # Database seeding
├── api/                         # API documentation
│   └── swagger.yaml             # OpenAPI documentation
├── configs/                     # Configuration files
│   ├── config.yaml.example      # Example configuration
│   └── .env.example             # Example environment variables
├── Makefile                     # Build and development commands
├── Dockerfile                   # Container definition
├── docker-compose.yml           # Development environment setup
├── go.mod                       # Go module definition
├── go.sum                       # Go module checksums
└── README.md                    # Project documentation
```

## Core Features

### User Management
- User registration and account creation
- User login and authentication
- User profile management
- Password reset functionality

### Authentication System
- JWT-based session management
- API key generation and validation
- Token refresh mechanisms
- Access control for protected resources

### Database Operations
- Generic CRUD operations for all database tables
- User-specific data management
- Transactional operations for data integrity
- Efficient query patterns

### Integration with Python Backend
- API key validation endpoint for Python backend
- User context sharing between services
- Standardized error responses
- Cross-service logging

## Database Schema

The database schema implements the following tables as defined in the provided design document:

### Users
- `user_id` (PK): Unique identifier for users
- `username`: Unique username (with index)
- `email`: Unique email address (with index)
- `password_hash`: Hashed password using Argon2id
- `salt`: Unique salt for password hashing
- `created_at`: Timestamp of account creation
- `updated_at`: Timestamp of last update

### UserSettings
- `setting_id` (PK): Unique identifier for settings
- `user_id` (FK): Reference to Users table
- `remove_images` (boolean): Whether to remove images during processing
- `created_at`: Timestamp of settings creation
- `updated_at`: Timestamp of last update

### Documents
- `document_id` (PK): Unique identifier for documents
- `user_id` (FK): Reference to Users table
- `hashed_document_name`: Hashed version of document name
- `upload_timestamp`: When the document was uploaded
- `last_modified`: When the document was last modified

### DetectionMethods
- `method_id` (PK): Unique identifier for methods
- `method_name`: Unique name of the detection method
- `highlight_color`: Color used for highlighting detected entities

### DetectedEntities
- `entity_id` (PK): Unique identifier for detected entities
- `document_id` (FK): Reference to Documents table
- `method_id` (FK): Reference to DetectionMethods table
- `entity_name`: Name of the detected entity
- `redaction_schema` (JSON): Position and redaction details
- `detected_timestamp`: When the entity was detected

### ModelEntities
- `model_entity_id` (PK): Unique identifier for model entities
- `setting_id` (FK): Reference to UserSettings table
- `method_id` (FK): Reference to DetectionMethods table
- `entity_text`: Text of the entity

### SearchPatterns
- `pattern_id` (PK): Unique identifier for search patterns
- `setting_id` (FK): Reference to UserSettings table
- `pattern_type`: Type of pattern (Regex or Normal)
- `pattern_text`: Text of the pattern

### BanList
- `ban_id` (PK): Unique identifier for ban lists
- `setting_id` (FK): Reference to UserSettings table

### BanListWords
- `ban_word_id` (PK): Unique identifier for banned words
- `ban_id` (FK): Reference to BanList table
- `word`: The banned word

### Sessions (Additional table for Go backend)
- `session_id` (PK): Unique identifier for sessions
- `user_id` (FK): Reference to Users table
- `jwt_id`: Unique identifier for the JWT token
- `expires_at`: Expiration time
- `created_at`: Creation timestamp

### APIKeys (Additional table for Go backend)
- `key_id` (PK): Unique identifier for API keys
- `user_id` (FK): Reference to Users table
- `api_key_hash`: Hashed API key
- `expires_at`: Expiration time
- `created_at`: Creation timestamp

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Register a new user
- `POST /api/auth/login` - Authenticate and receive tokens
- `POST /api/auth/logout` - End the current session
- `POST /api/auth/refresh` - Refresh the JWT token
- `GET /api/auth/verify` - Verify authentication status

### User Management
- `GET /api/users/me` - Get current user profile
- `PUT /api/users/me` - Update current user profile
- `DELETE /api/users/me` - Delete user account

### User Settings
- `GET /api/settings` - Get user settings
- `PUT /api/settings` - Update user settings

### API Key Management
- `GET /api/keys` - Get user API keys
- `POST /api/keys` - Generate a new API key
- `DELETE /api/keys/{keyId}` - Revoke an API key

### Python Backend Integration
- `POST /api/auth/validate-key` - Validate API key and return user info

### Generic Database Operations
- `POST /api/db/{table}` - Create a new record in specified table
- `GET /api/db/{table}/{id}` - Get record by ID from specified table
- `PUT /api/db/{table}/{id}` - Update record in specified table
- `DELETE /api/db/{table}/{id}` - Delete record from specified table

## Authentication System

### JWT Authentication
The system uses JSON Web Tokens (JWT) for authentication with the following characteristics:
- Short-lived access tokens (15-60 minutes)
- Token refresh mechanism
- Token validation middleware
- Secure cookie or Authorization header transport

### API Key Generation
- Generated as UUID v4
- Stored as a hash in the database
- Limited lifetime tied to session
- Revokable by the user

### Password Security
- Argon2id password hashing
- Unique salt per user
- Configurable work factors based on environment

## Integration with Python Backend

The Python backend will interact with the Go backend primarily through the API key validation endpoint. The workflow is as follows:

1. User authenticates with the Go backend and receives an API key
2. User includes this API key in requests to the Python backend
3. Python backend calls the Go backend's validation endpoint
4. Go backend verifies the API key and returns user information
5. Python backend proceeds with the operation using the verified user context

This integration allows for:
- Centralized user management
- Consistent authentication across services
- Separation of concerns between user management and document processing
- Reduced duplication of authentication logic

## Development Setup

### Prerequisites
- Go 1.18 or higher
- PostgreSQL 13 or higher
- Docker and Docker Compose (for containerized development)
- Make (for using the Makefile commands)

### Getting Started
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/hideme-go-backend.git
   cd hideme-go-backend
   ```

2. Copy and configure environment variables:
   ```bash
   cp configs/.env.example .env
   # Edit .env with your configuration
   ```

3. Start the development environment:
   ```bash
   make dev
   ```
   This will start PostgreSQL and set up the necessary development environment.

4. Run database migrations:
   ```bash
   make migrate-up
   ```

5. Seed the database with initial data (optional):
   ```bash
   make seed
   ```

6. Start the server:
   ```bash
   make run
   ```

The server will be available at http://localhost:8080 (or the configured port).

### Build and Run Without Docker
```bash
make build
./bin/api
```

### Docker Build and Run
```bash
docker build -t hideme-go-backend .
docker run -p 8080:8080 --env-file .env hideme-go-backend
```

## Configuration

The application can be configured using environment variables or a configuration file. Environment variables take precedence over the configuration file.

### Environment Variables
- `APP_ENV` - Application environment (development, testing, production)
- `PORT` - HTTP server port
- `DB_HOST` - Database host
- `DB_PORT` - Database port
- `DB_NAME` - Database name
- `DB_USER` - Database username
- `DB_PASSWORD` - Database password
- `JWT_SECRET` - Secret key for JWT signing
- `JWT_EXPIRY` - JWT token expiration time (e.g., "15m", "1h")
- `API_KEY_EXPIRY` - API key expiration time
- `LOG_LEVEL` - Logging level (debug, info, warn, error)
- `ALLOWED_ORIGINS` - CORS allowed origins

### Configuration File
The application can also be configured using a YAML file located at `configs/config.yaml`. See `configs/config.yaml.example` for an example configuration.

## Testing

### Running Tests
```bash
make test        # Run all tests
make test-unit   # Run unit tests only
make test-int    # Run integration tests
make coverage    # Generate test coverage report
```

### Test Organization
- Unit tests are located alongside the code they test
- Integration tests are in dedicated `_test` packages
- Test utilities are in the `internal/testutil` package

## Deployment

### Docker Deployment
The repository includes a Dockerfile for containerized deployment. Build the image and deploy it to your container orchestration system.

### Environment-Specific Configuration
Configure the application for different environments by setting the `APP_ENV` environment variable and providing appropriate configuration.

### Health Checks
The application exposes a health check endpoint at `/health` that can be used by container orchestrators or load balancers to monitor the application's health.

## Security Considerations

### Password Security
- Passwords are never stored in plain text
- Argon2id hashing with appropriate parameters
- Unique salt per user

### API Security
- HTTPS only in production
- JWT signed with a secure secret
- Short-lived tokens with refresh capability
- API keys stored as hashes

### Input Validation
- All input is validated before processing
- Structured validation using a dedicated validator

### Data Protection
- GDPR-compliant user data handling
- Option to delete account and all associated data
- Proper error handling to avoid leaking sensitive information


