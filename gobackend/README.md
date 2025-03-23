gobackend/
├── cmd/
│   └── api/
│       └── main.go              # Entry point for the application
├── internal/
│   ├── config/                  # Configuration management
│   │   └── config.go
│   ├── models/                  # Database models matching schema design
│   │   ├── user.go
│   │   ├── document.go
│   │   ├── detection_method.go
│   │   ├── detected_entity.go
│   │   ├── user_setting.go
│   │   ├── model_entity.go
│   │   ├── search_pattern.go
│   │   ├── ban_list.go
│   │   └── ban_list_word.go
│   ├── database/                # Database connection and operations
│   │   ├── db.go                # DB connection setup
│   │   └── operations.go        # Generic CRUD operations
│   ├── auth/                    # Authentication logic
│   │   ├── jwt.go               # JWT token generation/validation
│   │   ├── api_key.go           # API key management
│   │   ├── password.go          # Password hashing and validation
│   │   └── middleware.go        # Auth middleware
│   ├── handlers/                # HTTP handlers
│   │   ├── auth_handlers.go     # Signup, login, logout
│   │   ├── user_handlers.go     # User CRUD operations
│   │   ├── settings_handlers.go # User settings operations
│   │   └── generic_handlers.go  # Generic DB operations
│   └── utils/                   # Utilities
│       ├── response.go          # Standard response formats
│       └── validation.go        # Input validation
├── pkg/                         # Reusable packages
│   └── validator/               # Input validation
└── api/                         # API documentation
└── swagger.yaml             # OpenAPI documentation


System Logic
Authentication Flow

User Signup:

Validate input data
Hash password with salt
Create user record
Create default user settings
Generate session token and API key
Return tokens to user


User Login:

Validate credentials
Generate new session token and API key
Return tokens to user


Session Management:

JWT tokens for authentication
Token includes user ID and expiration time
API key tied to session expiration
Middleware validates tokens for protected routes


API Key Validation:

Endpoint for Python backend to validate API keys
Returns user information if valid
Returns error if invalid or expired



Database Operations

Generic Operations:

Create: Insert record into specified table
Read: Get record(s) from specified table with optional filters
Update: Update record in specified table
Delete: Delete record from specified table


User-Specific Operations:

Update user profile
Update user settings
Manage ban lists and search patterns



Integration with Python Backend

The Python backend will call the Go backend's API key validation endpoint
The validation endpoint will verify if the API key is valid and return user information
The Python backend can then process the request with the verified user context

Key Technical Decisions

Database Access: Use a SQL driver (likely pgx for PostgreSQL) with transaction support.
Authentication: JWT for session tokens and UUID v4 for API keys.
API Design: RESTful API with JSON responses.
Error Handling: Consistent error responses with appropriate HTTP status codes.
Validation: Request validation using a structured approach.
Security: Proper password hashing with Argon2 or bcrypt.
Logging: Structured logging for monitoring and debugging.
Configuration: Environment-based configuration with sensible defaults.

Specific Implementation Details
API Key Design

Format: UUID v4
Storage: Hashed in database alongside user record
Expiration: Linked to JWT session expiration
Validation: API endpoint for Python backend

Database Connection Pooling

Implement connection pooling to efficiently handle multiple requests
Set appropriate connection limits based on expected load

Rate Limiting

Implement rate limiting for authentication endpoints to prevent brute force attacks

Logging and Monitoring

Implement structured logging for easier parsing and analysis
Log authentication events and sensitive operations

Error Handling

Provide clear error messages for client applications
Use appropriate HTTP status codes
Don't expose sensitive information in error responses