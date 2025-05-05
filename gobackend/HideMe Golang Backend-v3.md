# HideMe Go Backend

[![Build Status](https://img.shields.io/badge/Status-In%20Testing-blue)]()
[![Test Coverage](https://img.shields.io/badge/Coverage-75%25-brightgreen)]()
[![Go Version](https://img.shields.io/badge/Go-1.23%2B-blue)]()
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)]()

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture & Components](#architecture--components)
- [API Documentation](#api-documentation)
- [Database Schema](#database-schema)
- [Setup & Installation](#setup--installation)
- [Testing](#testing)
- [Security Considerations](#security-considerations)
- [Integration with Python Backend](#integration-with-python-backend)
- [Contributing](#contributing)
- [License](#license)

## Project Overview

**HideMe Go Backend** is a robust backend service developed in Golang, designed to manage user authentication, session handling, API key verification, and core database operations for the HideMe application suite. This service acts as the central user management hub, complementing the HideMe Python Backend which focuses on the specialized tasks of document processing, sensitive data detection (particularly for Norwegian language), and redaction.

The primary purpose of the HideMe Go Backend is to provide a secure and efficient foundation for user-related functionalities, ensuring that the Python backend can operate independently on its core data processing tasks while relying on this service for user context and authorization. By separating these concerns, the overall system achieves better modularity, scalability, and maintainability.

### Key Features

- **User Authentication:** Secure user registration, login (with password hashing using Argon2id), and session management via JWT.
- **API Key Management:** Generation, validation, and revocation of API keys for service-to-service communication (e.g., Python backend validation).
- **Session Management:** Robust handling of user sessions, including listing active sessions and enabling users to revoke specific sessions.
- **Database Operations:** Provides a structured interface for interacting with the PostgreSQL database, managing user data, settings, API keys, sessions, and related entities.
- **Configuration Management:** Flexible configuration using environment variables and YAML files.
- **Clean Architecture:** Follows a layered architecture (API, Service, Repository, Model) for separation of concerns and testability.
- **Security Focused:** Implements security best practices including secure password hashing, JWT security, input validation, and secure error handling.
- **Docker Support:** Includes Dockerfile and docker-compose setup for easy development and deployment.

## Architecture & Components

The HideMe Go Backend is designed using a **Clean Architecture** approach, emphasizing a clear separation of concerns between different layers of the application. This promotes modularity, testability, and maintainability. The core principle is that dependencies flow inwards: outer layers (like the API) depend on inner layers (like Services and Repositories), but inner layers remain independent of the outer ones.
*Diagram illustrating the layered architecture:*
```mermaid
graph TD
    A[User/Client] --> B(API Layer / Handlers);
    B --> C{Service Layer};
    C --> D{Repository Layer};
    D --> E[Database (PostgreSQL)];
    B --> F(Middleware);
    F --> B;
    C --> G(Models);
    D --> G;
    H(Config) --> B;
    H --> C;
    H --> D;
    I(Utils) --> B;
    I --> C;
    I --> D;

    subgraph Application Core
        C
        D
        G
    end

    subgraph Infrastructure
        E
        H
        I
    end

    subgraph Presentation
        B
        F
    end
```

### Package Structure

The project follows a standard Go project layout, organizing code into logical packages primarily within the `internal` directory to prevent unintended external usage. Key directories include:

```
gobackend/
├── cmd/api/                  # Main application entry point
│   └── main.go
├── internal/
│   ├── api/                  # (Potentially merged with handlers/server)
│   ├── auth/                 # Authentication logic (JWT, API Key, Password)
│   ├── config/               # Configuration loading (YAML, Env Vars)
│   ├── constants/            # Application-wide constants
│   ├── database/             # Database connection & core operations (using GORM or similar)
│   ├── handlers/             # HTTP request handlers (controllers)
│   ├── middleware/           # HTTP middleware (Auth, Logging, Recovery)
│   ├── models/               # Data structures representing DB tables/entities
│   ├── repository/           # Data access layer (interacts with the database)
│   ├── server/               # HTTP server setup and routing
│   ├── service/              # Business logic layer
│   └── utils/                # Utility functions (Logging, Errors, Validation, Response)
│       └── gdprlog/          # GDPR-compliant logging utilities
├── migrations/               # Database schema migrations
├── scripts/                  # Utility scripts (Setup, Seeding)
├── logs/                     # Log file storage (standard, sensitive, personal)
├── .env                      # Environment variables (local)
├── config.yaml               # Application configuration file
├── Dockerfile                # Docker container definition
├── docker-compose.yml        # Docker Compose for development environment
├── go.mod                    # Go module dependencies
└── README.md                 # This file
```

### Layers Explained

1.  **API/Handlers Layer (`internal/handlers`, `internal/server/routes.go`):**
    *   Receives HTTP requests.
    *   Parses request data (body, parameters, headers).
    *   Performs initial input validation.
    *   Calls the appropriate methods in the Service Layer.
    *   Formats responses (using `internal/utils/response.go`) and sends them back to the client.
    *   Defines API routes and associates them with handler functions.

2.  **Middleware Layer (`internal/middleware`, `internal/auth/middleware.go`):**
    *   Intercepts requests before they reach the handlers.
    *   Handles cross-cutting concerns like:
        *   Authentication & Authorization (verifying JWTs, API keys).
        *   Request Logging.
        *   Panic Recovery.
        *   CORS handling.
        *   Rate Limiting.

3.  **Service Layer (`internal/service`):**
    *   Contains the core business logic of the application.
    *   Orchestrates operations by coordinating calls to one or more Repositories.
    *   Implements complex workflows and use cases.
    *   Remains independent of the HTTP layer.

4.  **Repository Layer (`internal/repository`):**
    *   Abstracts data persistence details.
    *   Provides an interface for accessing and manipulating data in the database.
    *   Contains specific queries and operations for each data model (e.g., `UserRepository`, `SessionRepository`).
    *   Interacts directly with the database driver/ORM (`internal/database`).

5.  **Model Layer (`internal/models`):**
    *   Defines the data structures (structs) that represent the application's entities and database tables.
    *   Used across different layers (Service, Repository, Handlers) for data transfer.

6.  **Database Layer (`internal/database`):**
    *   Manages the database connection (e.g., PostgreSQL using GORM or `database/sql`).
    *   Provides low-level database operation capabilities, potentially including generic CRUD functions.
    *   Handles database migrations (`migrations/`).

7.  **Config Layer (`internal/config`, `config.yaml`, `.env`):**
    *   Loads and manages application configuration from files (YAML) and environment variables.
    *   Provides access to configuration values throughout the application.

8.  **Utils Layer (`internal/utils`):**
    *   Contains shared utility functions and packages used across various layers.
    *   Includes helpers for logging (`logger.go`, `gdprlog/`), error handling (`errors.go`), response formatting (`response.go`), input validation (`validation.go`), etc.

### Security Features Overview

Security is integrated throughout the architecture:

- **Authentication:** JWT for user sessions, hashed API keys for service communication.
- **Password Storage:** Argon2id hashing with unique salts.
- **Authorization:** Middleware checks ensure users/services have appropriate permissions.
- **Input Validation:** Rigorous validation of all incoming data.
- **Secure Logging:** GDPR-aware logging utilities (`gdprlog`) to handle sensitive data appropriately.
- **Error Handling:** Prevents leaking sensitive information in error messages.
- **Dependency Management:** Using Go modules (`go.mod`) for secure dependency tracking.

## API Documentation

The HideMe Go Backend provides a comprehensive RESTful API for managing users, authentication, API keys, and settings. All API endpoints are prefixed with `/api`.

### Self-Documenting API

The server includes a built-in, self-documenting endpoint that provides complete, up-to-date API documentation:

- **`GET /api/routes`**  
  Returns comprehensive documentation for all available API routes, including request/response formats, headers, authentication requirements, and more.

This endpoint serves as the source of truth for API documentation and should be consulted for the most accurate and current information.

### API Category Overview

The API is organized into the following functional categories:

| Category | Base Path | Description |
|----------|-----------|-------------|
| System/Health | `/health`, `/version`, `/api/routes` | Basic service health and version information |
| Authentication | `/api/auth/...` | User registration, login, logout, token refresh, API key validation |
| User Management | `/api/users/...` | User profile management, password changes, session management |
| API Key Management | `/api/keys/...` | Generation, listing, and revocation of API keys |
| Settings Management | `/api/settings/...` | User preferences, ban lists, search patterns, model entities |
| Database Operations | `/api/db/...` | Direct CRUD access to database tables (admin/development only) |

### Authentication Methods

1.  **JWT (JSON Web Tokens):** Used for user sessions after login. The client receives an `access_token` (short-lived) and a `refresh_token` (long-lived, stored in an HTTP-only cookie). The `access_token` must be sent in the `Authorization: Bearer <token>` header for protected endpoints.
2.  **API Keys:** Used primarily for the Python backend to validate user context. The key is sent in the `X-API-Key` header.

### Endpoints

*(Note: Examples below use placeholder data. Refer to the Postman collection `Golang Server Testing.postman_collection.json` for detailed request/response examples.)*

#### Health & System

-   **`GET /health`**
    -   **Description:** Checks the health of the service, including database connectivity.
    -   **Authentication:** None
    -   **Response:**
        ```json
        {
        "success": true,
        "data": {
        "status": "healthy",
        "version": "1.0.0"
          }
        }
        ```

-   **`GET /version`**
    -   **Description:** Returns the application version and environment.
    -   **Authentication:** None
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "environment": "production",
            "version": "1.0.0"
          }
        }
        ```

-   **`GET /api/routes`**
    -   **Description:** Provides documentation for all available API routes (self-documenting endpoint).
    -   **Authentication:** None
    -   **Response:** A JSON object detailing all endpoints, methods, descriptions, headers, bodies, and responses.


#### Authentication (`/api/auth`)

-   **`POST /api/auth/signup`**
    -   **Description:** Registers a new user.
    -   **Authentication:** None
    -   **Request Body:**
        ```json
        {
          "username": "jojojo1234",
          "email": "jojojo1234@gmail.com",
          "password": "jojojo1234",
          "confirm_password": "jojojo1234"
        }
        ```
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "id": 8,
            "username": "jojojo1234",
            "email": "jojojo1234@gmail.com",
            "created_at": "2025-05-05T15:23:17.608720Z",
            "updated_at": "2025-05-05T15:23:17.608720Z"
          }
        }
        ```

-   **`POST /api/auth/login`**
    -   **Description:** Authenticates a user and returns JWT tokens.
    -   **Authentication:** None
    -   **Request Body:**
        ```json
        {
          "username": "jojojo1234",
          "password": "jojojo1234"
        }
        ```
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "expires_in": 900,
            "token_type": "Bearer",
            "user": {
              "id": 8,
              "username": "jojojo1234",
              "email": "jojojo1234@gmail.com",
              "created_at": "2025-05-05T15:23:17.608727",
              "updated_at": "2025-05-05T15:23:17.608727"
            }
          }
        }
        ```

-   **`POST /api/auth/refresh`**
    -   **Description:** Refreshes the JWT access token using the `refresh_token` cookie.
    -   **Authentication:** Requires valid `refresh_token` cookie.
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "expires_in": 900,
            "token_type": "Bearer"
          }
        }
        ```

-   **`POST /api/auth/logout`**
    -   **Description:** Logs out the current user session by invalidating the refresh token.
    -   **Authentication:** Requires valid `refresh_token` cookie.
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "message": "Successfully logged out"
          }
        }
        ```

-   **`POST /api/auth/logout-all`**
    -   **Description:** Logs out the user from all active sessions.
    -   **Authentication:** JWT Bearer Token
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "message": "Successfully logged out of all sessions"
          }
        }
        ```

-   **`GET /api/auth/verify`**
    -   **Description:** Verifies the validity of the current JWT access token.
    -   **Authentication:** JWT Bearer Token
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "authenticated": true,
            "email": "john@example.com",
            "user_id": 1,
            "username": "johndoe"
          }
        }
        ```

-   **`POST /api/auth/validate-key`**
    -   **Description:** Validates an API key (typically used by the Python backend).
    -   **Authentication:** Requires `X-API-Key` header: `kH2TRbZkGKFJGiY-6W22nfuQKp2uvzhz`
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "email": "hahaha123@gmail.com",
            "user_id": 6,
            "username": "hahaha123",
            "valid": true
          }
        }
        ```

-   **`GET /api/auth/verify-key`**
    -   **Description:** Verifies an API key without requiring user authentication (simple check).
    -   **Authentication:** Requires `X-API-Key` header: `J1UTzHAguod_VBX1mfOhb6BowUWzJVkP`
    -   **Response (Success):**
        ```json
        {
          "success": true,
          "data": {
            "valid": true
          }
        }
        ```

#### User Management (`/api/users`)

-   **`GET /api/users/check/username?username={username}`**
    -   **Description:** Checks if a username is available.
    -   **Authentication:** None
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "available": true,
            "username": "johndoe"
          }
        }
        ```

-   **`GET /api/users/check/email?email={email}`**
    -   **Description:** Checks if an email is available.
    -   **Authentication:** None
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "available": true,
            "email": "john@example.com"
          }
        }
        ```

-   **`GET /api/users/me`**
    -   **Description:** Gets the profile of the currently authenticated user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 8,
            "username": "jojojo1234",
            "email": "jojojo1234@gmail.com",
            "created_at": "2025-05-05T15:23:17.608727",
            "updated_at": "2025-05-05T15:23:17.608727"
          }
        }
        ```

-   **`PUT /api/users/me`**
    -   **Description:** Updates the profile of the currently authenticated user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** Fields to update (e.g., `{"email": "new@example.com"}`).
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "created_at": "2023-01-01T12:00:00Z",
            "email": "john@example.com",
            "updated_at": "2023-01-01T12:00:00Z",
            "user_id": 1,
            "username": "johndoe"
          }
        }
        ```

-   **`DELETE /api/users/me`**
    -   **Description:** Deletes the account of the currently authenticated user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** `{"password": "current_password", "confirm": "DELETE"}`
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "Account successfully deleted"
          }
        }
        ```

-   **`POST /api/users/me/change-password`**
    -   **Description:** Changes the password for the currently authenticated user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:**
        ```json
        {
          "current_password": "jojojo1234",
          "new_password": "jojojo12345A",
          "confirm_password": "jojojo12345A"
        }
        ```
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "Password successfully changed"
          }
        }
        ```

-   **`GET /api/users/me/sessions`**
    -   **Description:** Lists all active sessions for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": [
            {
              "created_at": "2023-01-01T12:00:00Z",
              "expires_at": "2023-01-08T12:00:00Z",
              "id": "session-id-1"
            }
          ]
        }
        ```

-   **`DELETE /api/users/me/sessions`**
    -   **Description:** Invalidates a specific session for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** `{"session_id": "session_uuid_to_delete"}`
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "Session successfully invalidated"
          }
        }
        ```

#### API Key Management (`/api/keys`)

-   **`GET /api/keys`**
    -   **Description:** Lists all API keys for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": [
            {
              "created_at": "2023-01-01T12:00:00Z",
              "expires_at": "2023-12-31T23:59:59Z",
              "id": "key-id-1",
              "name": "My API Key"
            }
          ]
        }
        ```

-   **`POST /api/keys`**
    -   **Description:** Generates a new API key for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** `{"name": "hei", "duration": "30d"}` (duration optional, e.g., "7d", "90d")
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": "34d72b80-83be-47eb-8319-8022867af60f",
            "name": "hei",
            "key": "J1UTzHAguod_VBX1mfOhb6BowUWzJVkP",
            "expires_at": "2025-06-04T15:31:02.213671Z",
            "created_at": "2025-05-05T15:31:02.213671Z"
          }
        }
        ```

-   **`DELETE /api/keys/{keyID}`**
    -   **Description:** Revokes/deletes a specific API key.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `keyID` (UUID of the key to delete).
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "API key successfully revoked"
          }
        }
        ```

-   **`GET /api/keys/{keyID}/decode`**
    -   **Description:** Retrieves the decoded (plain text) API key. *Use with caution.* Should ideally only be available immediately after creation or require re-authentication.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `keyID` (UUID of the key).
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "created_at": "2025-05-05T15:31:02.213672Z",
            "expires_at": "2025-06-04T15:31:02.213672Z",
            "id": "34d72b80-83be-47eb-8319-8022867af60f",
            "key": "J1UTzHAguod_VBX1mfOhb6BowUWzJVkP",
            "name": "hei"
          }
        }
        ```

#### Settings Management (`/api/settings`)

-   **`GET /api/settings`**
    -   **Description:** Retrieves all settings for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 5,
            "user_id": 8,
            "remove_images": true,
            "theme": "system",
            "auto_processing": true,
            "detection_threshold": 0.5,
            "use_banlist_for_detection": true,
            "created_at": "2025-05-05T15:33:48.043901Z",
            "updated_at": "2025-05-05T15:33:48.043901Z"
          }
        }
        ```

-   **`PUT /api/settings`**
    -   **Description:** Updates settings for the current user.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:**
        ```json
        {
          "remove_images": false
        }
        ```
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 5,
            "user_id": 8,
            "remove_images": false,
            "theme": "system",
            "auto_processing": true,
            "detection_threshold": 0.5,
            "use_banlist_for_detection": true,
            "created_at": "2025-05-05T15:33:48.043901Z",
            "updated_at": "2025-05-05T15:34:18.459418Z"
          }
        }
        ```

-   **`GET /api/settings/export`**
    -   **Description:** Exports user settings, ban lists, patterns, and entities as a JSON file.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "user_id": 8,
          "export_date": "2025-05-05T15:36:27.433808Z",
          "general_settings": {
            "id": 5,
            "user_id": 8,
            "remove_images": true,
            "theme": "system",
            "auto_processing": true,
            "detection_threshold": 0.5,
            "use_banlist_for_detection": true,
            "created_at": "2025-05-05T15:33:48.043901Z",
            "updated_at": "2025-05-05T15:35:46.524748Z"
          },
          "ban_list": {
            "id": 3,
            "words": [
              "confidential",
              "restricted"
            ]
          }
        }
        ```

-   **`POST /api/settings/import`**
    -   **Description:** Imports settings from a previously exported JSON file.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** Multipart form data with the JSON file.
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "Settings imported successfully"
          }
        }
        ```

-   **`GET /api/settings/ban-list`**
    -   **Description:** Retrieves the ban list words for the user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 3,
            "words": [
              "aef",
              "eaf",
              "restricted"
            ]
          }
        }
        ```

-   **`POST /api/settings/ban-list/words`**
    -   **Description:** Adds words to the user's ban list.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** `{"words": ["word1", "word2"]}`
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 1,
            "words": [
              "word1",
              "word2",
              "word3",
              "word4",
              "word5"
            ]
          }
        }
        ```

-   **`DELETE /api/settings/ban-list/words`**
    -   **Description:** Removes words from the user's ban list.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:** `{"words": ["word1", "word2"]}`
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 1,
            "words": [
              "word3",
              "word4",
              "word5"
            ]
          }
        }
        ```

-   **`GET /api/settings/patterns`**
    -   **Description:** Retrieves all search patterns for the user.
    -   **Authentication:** JWT Bearer Token
    -   **Response:**
        ```json
        {
          "success": true,
          "data": [
            {
              "id": 3,
              "setting_id": 5,
              "pattern_type": "ai_search",
              "pattern_text": "hello mt"
            }
          ]
        }
        ```

-   **`POST /api/settings/patterns`**
    -   **Description:** Creates a new search pattern.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:**
        ```json
        {
          "pattern_type": "ai_search",
          "pattern_text": "kewnfklewni"
        }
        ```
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "id": 4,
            "setting_id": 5,
            "pattern_type": "ai_search",
            "pattern_text": "kewnfklewni"
          }
        }
        ```

-   **`PUT /api/settings/patterns/{patternID}`**
    -   **Description:** Updates an existing search pattern.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `patternID`.
    -   **Request Body:** Fields to update.
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "pattern_id": 3,
            "pattern_text": "updated pattern",
            "pattern_type": "Normal",
            "setting_id": 1
          }
        }
        ```

-   **`DELETE /api/settings/patterns/{patternID}`**
    -   **Description:** Deletes a search pattern.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `patternID`.
    -   **Response:**
        ```json
        {
          "success": true,
          "no_content": true,
          "status_code": 204
        }
        ```

-   **`GET /api/settings/entities/{methodID}`**
    -   **Description:** Retrieves model entities associated with a specific detection method ID.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `methodID`.
    -   **Response:**
        ```json
        {
          "success": true,
          "data": [
            {
              "id": 55,
              "setting_id": 5,
              "method_id": 7,
              "entity_text": "eifijiewo",
              "method_name": "Search"
            },
            {
              "id": 53,
              "setting_id": 5,
              "method_id": 7,
              "entity_text": "Email Address",
              "method_name": "Search"
            }
          ]
        }
        ```

-   **`POST /api/settings/entities`**
    -   **Description:** Adds new model entities.
    -   **Authentication:** JWT Bearer Token
    -   **Request Body:**
        ```json
        {
          "method_id": 7,
          "entities": ["Phone Number", "Email Address"]
        }
        ```
    -   **Response:**
        ```json
        {
          "success": true,
          "data": [
            {
              "id": 52,
              "setting_id": 5,
              "method_id": 7,
              "entity_text": "Phone Number"
            },
            {
              "id": 53,
              "setting_id": 5,
              "method_id": 7,
              "entity_text": "Email Address"
            }
          ]
        }
        ```

-   **`DELETE /api/settings/entities/{entityID}`**
    -   **Description:** Deletes a specific model entity.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `entityID`.
    -   **Response:**
        ```json
        {
          "success": true,
          "no_content": true,
          "status_code": 204
        }
        ```

-   **`DELETE /api/settings/entities/delete_entities_by_method_id/{methodID}`**
    -   **Description:** Deletes all model entities associated with a specific detection method ID.
    -   **Authentication:** JWT Bearer Token
    -   **Path Parameter:** `methodID`.
    -   **Response:**
        ```json
        {
          "success": true,
          "data": {
            "message": "All entities for method ID successfully deleted"
          }
        }
        ```

#### Generic Database Operations (`/api/db`) - *Admin/Development Only*

*These endpoints provide direct CRUD access to database tables and should be restricted in production environments.*

-   **`GET /api/db/{table}`** - List records from a table.
    -   **Example:** `GET /api/db/detection_methods`
    -   **Response:**
        ```json
        [
          {
            "Method ID": 1,
            "Method Name": "Presidio",
            "Highlight Color": "#33FF57"
          },
          {
            "Method ID": 2,
            "Method Name": "Gliner",
            "Highlight Color": "#F033FF"
          },
          {
            "Method ID": 3,
            "Method Name": "Gemini",
            "Highlight Color": "#FFFF33"
          },
          {
            "Method ID": 4,
            "Method Name": "HideMeModel",
            "Highlight Color": "#33FF57"
          },
          {
            "Method ID": 5,
            "Method Name": "AiSearch",
            "Highlight Color": "#33A8FF"
          },
          {
            "Method ID": 6,
            "Method Name": "CaseSensitive",
            "Highlight Color": "#33A8FF"
          },
          {
            "Method ID": 7,
            "Method Name": "Search",
            "Highlight Color": "#33A8FF"
          },
          {
            "Method ID": 8,
            "Method Name": "Manual",
            "Highlight Color": "#FF5733"
          }
        ]
        ```

-   **`POST /api/db/{table}`** - Create a new record in a table.
-   **`GET /api/db/{table}/{id}`** - Get a specific record by ID.
-   **`PUT /api/db/{table}/{id}`** - Update a specific record.
-   **`DELETE /api/db/{table}/{id}`** - Delete a specific record.
-   **`GET /api/db/{table}/schema`** - Get the schema/structure of a table.

    -   **Authentication:** JWT Bearer Token (potentially with admin role check).
    -   **Path Parameters:** `table` (table name), `id` (record ID).

## Database Schema

The application utilizes a PostgreSQL database to persist user data, settings, sessions, API keys, and related information. The schema is designed to support the core functionalities of authentication, user management, and settings configuration. Database interactions are primarily managed through the Repository layer, often utilizing an ORM like GORM (verify based on `go.mod` and `database/db.go`).

*(Diagram illustrating the database relationships and structure:)*
```mermaid
erDiagram
    USERS ||--o{ SESSIONS : has
    USERS ||--o{ API_KEYS : has
    USERS ||--o{ USER_SETTINGS : has
    USERS ||--o{ DOCUMENTS : has

    USER_SETTINGS ||--o{ MODEL_ENTITIES : configures
    USER_SETTINGS ||--o{ SEARCH_PATTERNS : configures
    USER_SETTINGS ||--o{ BAN_LIST : configures

    DOCUMENTS ||--o{ DETECTED_ENTITIES : contains

    DETECTION_METHODS ||--o{ DETECTED_ENTITIES : detected_by
    DETECTION_METHODS ||--o{ MODEL_ENTITIES : applies_to

    BAN_LIST ||--o{ BAN_LIST_WORDS : contains

    USERS {
        BIGINT user_id PK
        VARCHAR username UK
        VARCHAR email UK
        BYTEA password_hash
        BYTEA salt
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    SESSIONS {
        UUID session_id PK
        BIGINT user_id FK
        UUID jwt_id UK
        TIMESTAMP expires_at
        TIMESTAMP created_at
    }

    API_KEYS {
        UUID key_id PK
        BIGINT user_id FK
        VARCHAR name
        BYTEA api_key_hash UK
        TIMESTAMP expires_at
        TIMESTAMP created_at
    }

    USER_SETTINGS {
        BIGINT setting_id PK
        BIGINT user_id FK UK
        BOOLEAN remove_images
        TIMESTAMP created_at
        TIMESTAMP updated_at
        JSONB other_settings -- Placeholder for potential future settings
    }

    DOCUMENTS {
        BIGINT document_id PK
        BIGINT user_id FK
        VARCHAR hashed_document_name
        TIMESTAMP upload_timestamp
        TIMESTAMP last_modified
    }

    DETECTION_METHODS {
        BIGINT method_id PK
        VARCHAR method_name UK
        VARCHAR highlight_color
    }

    DETECTED_ENTITIES {
        BIGINT entity_id PK
        BIGINT document_id FK
        BIGINT method_id FK
        VARCHAR entity_name
        JSONB redaction_schema
        TIMESTAMP detected_timestamp
    }

    MODEL_ENTITIES {
        BIGINT model_entity_id PK
        BIGINT setting_id FK
        BIGINT method_id FK
        VARCHAR entity_text
    }

    SEARCH_PATTERNS {
        BIGINT pattern_id PK
        BIGINT setting_id FK
        VARCHAR pattern_type -- e.g., 'Regex', 'Normal'
        VARCHAR pattern_text
    }

    BAN_LIST {
        BIGINT ban_id PK
        BIGINT setting_id FK UK
    }

    BAN_LIST_WORDS {
        BIGINT ban_word_id PK
        BIGINT ban_id FK
        VARCHAR word
    }

```
### Tables

1.  **`users`**
    *   **Purpose:** Stores core user account information.
    *   **Key Columns:** `user_id` (PK), `username` (UK), `email` (UK), `password_hash`, `salt`.

2.  **`sessions`**
    *   **Purpose:** Manages active user sessions, primarily tracking refresh tokens.
    *   **Key Columns:** `session_id` (PK), `user_id` (FK), `jwt_id` (UK, identifier within the JWT), `expires_at`.

3.  **`api_keys`**
    *   **Purpose:** Stores API keys generated by users, primarily for service-to-service authentication.
    *   **Key Columns:** `key_id` (PK), `user_id` (FK), `name`, `api_key_hash` (UK), `expires_at`.

4.  **`user_settings`**
    *   **Purpose:** Stores user-specific configuration preferences.
    *   **Key Columns:** `setting_id` (PK), `user_id` (FK, UK), `remove_images`, potentially other JSONB settings.

5.  **`documents`**
    *   **Purpose:** Stores metadata about documents processed by the system (likely managed more by the Python backend, but potentially referenced here).
    *   **Key Columns:** `document_id` (PK), `user_id` (FK), `hashed_document_name`.

6.  **`detection_methods`**
    *   **Purpose:** Defines the different methods used for sensitive data detection (e.g., Presidio, Gemini, Custom).
    *   **Key Columns:** `method_id` (PK), `method_name` (UK).

7.  **`detected_entities`**
    *   **Purpose:** Records instances of sensitive data found within documents.
    *   **Key Columns:** `entity_id` (PK), `document_id` (FK), `method_id` (FK), `entity_name`, `redaction_schema` (JSON).

8.  **`model_entities`**
    *   **Purpose:** Stores custom entities defined by the user for specific detection methods, linked to user settings.
    *   **Key Columns:** `model_entity_id` (PK), `setting_id` (FK), `method_id` (FK), `entity_text`.

9.  **`search_patterns`**
    *   **Purpose:** Stores custom search patterns (e.g., regex) defined by the user, linked to user settings.
    *   **Key Columns:** `pattern_id` (PK), `setting_id` (FK), `pattern_type`, `pattern_text`.

10. **`ban_list`**
    *   **Purpose:** Represents the container for a user's banned words list, linked to user settings.
    *   **Key Columns:** `ban_id` (PK), `setting_id` (FK, UK).

11. **`ban_list_words`**
    *   **Purpose:** Stores the actual words included in a user's ban list.
    *   **Key Columns:** `ban_word_id` (PK), `ban_id` (FK), `word`.

### Migrations

Database schema changes are managed using migration files located in the `/migrations` directory. These migrations ensure that the database schema can be updated consistently across different environments. Tools like `golang-migrate/migrate` or GORM's auto-migration features might be used (verify based on project setup).

To apply migrations, typically a command like `make migrate-up` or a specific Go command is used (see [Setup & Installation](#setup--installation)).

## Setup & Installation

This section provides instructions for setting up the HideMe Go Backend for both development and deployment.

### Prerequisites

Before you begin, ensure you have the following installed on your system:

-   **Go:** Version 1.23 or higher (Verify using `go version`. Project uses Go 1.23 with toolchain 1.24).
-   **PostgreSQL:** Version 13 or higher (Required for the database).
-   **Docker & Docker Compose:** Required for containerized development and deployment.
-   **Make:** (Optional, but recommended) Used for running common development commands defined in the `Makefile` (if present).
-   **Git:** For cloning the repository.

### Environment Configuration

The application requires configuration through environment variables and/or a YAML file. Environment variables take precedence over values defined in the YAML file.

1.  **`.env` File:**
    *   Copy the example environment file: `cp .env.example .env` (or use the provided `upload/.env` as a base).
    *   Edit the `.env` file with your specific settings, especially for the database connection and JWT secret.
    *   Key variables (refer to `internal/config/env.go` and `upload/.env` for a complete list):
        *   `APP_ENV`: Application environment (`development`, `testing`, `production`).
        *   `PORT`: HTTP server port (e.g., `8080`).
        *   `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`: PostgreSQL connection details.
        *   `JWT_SECRET`: Secret key for signing JWT tokens (generate a strong random key).
        *   `JWT_ACCESS_EXPIRY`, `JWT_REFRESH_EXPIRY`: Token expiration times (e.g., "15m", "7d").
        *   `API_KEY_EXPIRY`: Default API key expiration (e.g., "30d").
        *   `LOG_LEVEL`: Logging level (`debug`, `info`, `warn`, `error`).
        *   `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins (e.g., `http://localhost:5173,https://yourfrontend.com`).

2.  **`config.yaml` File:**
    *   Located at the root or `/configs` directory (e.g., `upload/config.yaml`).
    *   Provides default settings and can structure configuration more hierarchically.
    *   Values here can be overridden by environment variables.

### Local Setup (Without Docker)

This setup is suitable for development directly on your host machine.

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yasinhessnawi1/Hideme_Backend.git
    cd gobackend # Or your project's root directory
    ```

2.  **Install Dependencies:**
    ```bash
    go mod download
    # or
    go mod tidy
    ```

3.  **Setup PostgreSQL:**
    *   Ensure your PostgreSQL server is running.
    *   Create the database specified in your `.env` file (`DB_NAME`).
    *   Ensure the user (`DB_USER`) has the necessary privileges.

4.  **Configure Environment:**
    *   Create and configure your `.env` file as described above.

5.  **Run Database Migrations:**
    *   Check the `/migrations` directory and `Makefile` or `scripts/setup.sh` for migration commands.
    *   Example using `golang-migrate/migrate` (if used):
        ```bash
        # Install migrate tool if needed
        # migrate -database "postgres://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=${DB_SSLMODE}" -path migrations up
        ```
    *   Example using `make` (if defined):
        ```bash
        make migrate-up
        ```

6.  **Seed Database (Optional):**
    *   If a seeding script (`scripts/seed.go`) exists, run it:
        ```bash
        go run scripts/seed.go
        # or (if defined in Makefile)
        make seed
        ```

7.  **Build and Run:**
    *   **Build:**
        ```bash
        go build -o bin/api ./cmd/api/
        ./bin/api
        ```
    *   **Run directly:**
        ```bash
        go run ./cmd/api/main.go
        ```
    *   **Using Make (if defined):**
        ```bash
        make run
        ```
    *   The server should now be running, typically on `http://localhost:8080`.

### Docker Setup (Development)

Using Docker Compose is the recommended way for setting up a consistent development environment.

1.  **Clone the Repository:** (If not already done)
    ```bash
    git clone https://github.com/yasinhessnawi1/Hideme_Backend.git
    cd gobackend # Or your project's root directory
    ```

2.  **Configure Environment:**
    *   Create and configure your `.env` file. Ensure `DB_HOST` points to the service name defined in `docker-compose.yml` (e.g., `postgres`).

3.  **Start Services:**
    ```bash
    docker-compose up -d
    # or use make command if available (e.g., make dev)
    # make dev
    ```
    This command will build the necessary images (if not already built) and start the Go application container and the PostgreSQL database container.

4.  **Run Database Migrations (inside container):**
    ```bash
    docker-compose exec api make migrate-up
    # or if make is not used:
    # docker-compose exec api migrate -database "postgres://${DB_USER}:${DB_PASSWORD}@postgres:${DB_PORT}/${DB_NAME}?sslmode=${DB_SSLMODE}" -path migrations up
    ```

5.  **Seed Database (Optional, inside container):**
    ```bash
    docker-compose exec api make seed
    # or if make is not used:
    # docker-compose exec api go run scripts/seed.go
    ```

6.  **Access the Application:**
    *   The API should be accessible at `http://localhost:8080` (or the port mapped in `docker-compose.yml`).

7.  **View Logs:**
    ```bash
    docker-compose logs -f api
    ```

8.  **Stop Services:**
    ```bash
    docker-compose down
    ```

### Docker Build (Production)

To build a standalone Docker image for deployment:

1.  **Build the Image:**
    ```bash
    docker build -t hideme-go-backend:latest .
    ```
    The `Dockerfile` typically uses a multi-stage build to create a minimal final image.

2.  **Run the Container:**
    ```bash
    docker run -d --name hideme-go \
      -p 8080:8080 \
      --env-file .env \
      hideme-go-backend:latest
    ```
    *   Ensure your production `.env` file is correctly configured and securely managed.
    *   Adjust port mapping (`-p`) as needed.
    *   Connect the container to the appropriate network to access the production database.

## Testing

Testing is a crucial part of the development process for the HideMe Go Backend, ensuring code quality, reliability, and correctness. The project utilizes Go's built-in testing framework along with additional libraries including DATA-DOG/go-sqlmock for database testing and stretchr/testify for assertions.

### Test Coverage Statistics

The project maintains high test coverage across its codebase:

[![Test Coverage](https://img.shields.io/badge/Coverage-75%25-brightgreen)]()

Current coverage statistics per package:
- Overall: 75% statement coverage
- Models: 100% coverage
- Middleware: 93.7% coverage
- Repository: 93.3% coverage
- Handlers: 85.6% coverage
- Config: 85.6% coverage
- Utils: 81.5% coverage
- Migrations: 84.4% coverage

Several key utility files have 100% statement coverage, including error handling utilities, providing confidence in the reliability of core components.

### Running Tests

Tests can be executed using standard Go commands or potentially via `make` targets if defined in a `Makefile`.

1.  **Run All Tests:**
    ```bash
    go test ./...
    # or (if defined in Makefile)
    make test
    ```

2.  **Run Tests with Coverage:**
    ```bash
    go test ./... -coverprofile=coverage.out
    go tool cover -html=coverage.out -o coverage.html
    # or (if defined in Makefile)
    make coverage
    ```
    This generates an HTML report (`coverage.html`) detailing test coverage for each package and file. You can open this file in a browser to view the results.

3.  **Run Specific Tests:**
    *   Run tests for a specific package:
        ```bash
        go test ./internal/auth/
        ```
    *   Run a specific test function:
        ```bash
        go test ./internal/auth/ -run TestJWTService_GenerateToken
        ```

### Types of Tests

The project includes:

-   **Unit Tests:** Located alongside the code they test (e.g., `jwt_test.go` tests `jwt.go`). These tests focus on individual functions or components in isolation, often using mocks for dependencies (like database interactions).

Test files follow the `*_test.go` naming convention.

## Security Considerations

Security is a primary concern for the HideMe Go Backend, especially given its role in handling user authentication and sensitive API keys. Several measures are implemented across the application:

### Authentication & Authorization

-   **JWT Security:**
    -   Access tokens are short-lived (e.g., 15 minutes) to minimize the window of opportunity if compromised.
    -   Refresh tokens are longer-lived (e.g., 7 days), stored securely in HTTP-only cookies to prevent access via client-side scripts (XSS).
    -   Tokens are signed using a strong secret key (`JWT_SECRET`) configured via environment variables.
    -   The `jwt_id` (JTI) claim is used to link tokens to specific sessions, allowing for targeted session invalidation.
    -   All protected endpoints are guarded by JWT authentication middleware (`internal/middleware/auth_middleware.go`).
-   **API Key Security:**
    -   API keys are generated using cryptographically secure random methods (e.g., UUIDs combined with random strings).
    -   Keys are **hashed** using a strong, one-way hashing algorithm (e.g., SHA-256 or bcrypt - *verify implementation in `internal/auth/api_key.go`*) before being stored in the database (`api_keys` table).
    -   The plain text key is shown to the user only once upon creation.
    -   API key validation (`/api/auth/validate-key`) involves hashing the provided key and comparing it against the stored hash.
    -   Keys have configurable expiration dates.
-   **Role-Based Access Control (RBAC):** While not explicitly detailed in the provided files, consider implementing RBAC if different user roles require different permissions (e.g., admin access to generic DB endpoints).

### Password Security

-   **Hashing:** User passwords are never stored in plain text. They are hashed using **Argon2id**, a modern, memory-hard hashing algorithm resistant to GPU cracking attacks. (Verify implementation in `internal/auth/password.go`).
-   **Salting:** A unique, cryptographically secure salt is generated for each user and stored alongside the password hash in the `users` table. This prevents rainbow table attacks.
-   **Password Policies:** Input validation enforces minimum password complexity requirements during signup and password change (check `internal/utils/validation.go` or handler logic).

### Data Protection & GDPR

-   **Secure Logging (`internal/utils/gdprlog`):**
    -   Specialized logging utilities are provided to handle potentially sensitive data according to GDPR principles.
    -   Logs might be separated into different files (`standard.log`, `sensitive.log`, `personal.log`) based on data sensitivity.
    -   Mechanisms for redacting or anonymizing sensitive information in logs should be employed.
-   **Data Minimization:** Only necessary user data is collected and stored.
-   **Right to Erasure:** The `DELETE /api/users/me` endpoint allows users to delete their accounts and associated data, supporting the right to be forgotten.
-   **Data Encryption:** Consider encrypting sensitive data at rest in the database if required, beyond just password and API key hashing.

### Input Validation

-   All data received from clients (request bodies, query parameters, path parameters) is rigorously validated before processing.
-   This is typically handled in the Handler layer or via dedicated validation utilities (`internal/utils/validation.go`), preventing injection attacks, invalid data states, and unexpected errors.

### Secure Headers & CORS

-   **Security Headers:** Middleware (`internal/middleware/middleware.go`) adds important security headers to HTTP responses (e.g., `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`) to mitigate common web vulnerabilities like XSS and clickjacking.
-   **CORS Configuration:** Cross-Origin Resource Sharing is carefully configured (`internal/server/routes.go`) via `ALLOWED_ORIGINS` to only permit requests from trusted frontend domains, preventing unauthorized cross-origin attacks.

### Error Handling

-   Generic error messages are returned to clients to avoid leaking internal implementation details or sensitive information (`internal/utils/response.go`, `internal/utils/errors.go`).
-   Detailed errors are logged internally for debugging purposes.
-   Panic recovery middleware (`internal/middleware/recovery.go`) prevents unexpected crashes from terminating the server and logs the panic details.

### Dependency Management

-   Go modules (`go.mod`, `go.sum`) are used to manage dependencies, ensuring reproducible builds and allowing for vulnerability scanning of third-party libraries.

## Integration with Python Backend

The HideMe Go Backend serves as the central authentication and user management service for the larger HideMe system. It integrates primarily with the HideMe Python Backend (responsible for document processing and redaction) through API calls.

### Authentication Flow

The primary integration point is the validation of API keys provided by users when interacting with the Python backend.

1.  **User Authentication (Go Backend):** A user logs into the system via the Go backend's UI or API (`/api/auth/login`) and obtains JWT tokens.
2.  **API Key Generation (Go Backend):** The user generates an API key via the Go backend's interface (`/api/keys`). This key is intended for programmatic access, such as configuring the Python backend or other clients.
3.  **Request to Python Backend:** The user (or an application acting on their behalf) makes a request to the Python backend, including the generated API key in the `X-API-Key` header.
4.  **API Key Validation (Go Backend):** The Python backend receives the request and calls the Go backend's `/api/auth/validate-key` endpoint, passing the received `X-API-Key`.
5.  **Go Backend Verification:** The Go backend receives the validation request:
    *   It extracts the key ID and the key secret from the provided `X-API-Key`.
    *   It looks up the key ID in the `api_keys` table.
    *   If found and not expired, it hashes the provided key secret and compares it with the stored `api_key_hash`.
    *   If the hash matches, the key is valid.
6.  **User Context Return (Go Backend):** Upon successful validation, the Go backend returns relevant user information (like User ID, potentially username or permissions) to the Python backend.
7.  **Python Backend Processing:** The Python backend uses the validated user context received from the Go backend to authorize the request and perform the requested document processing or redaction task under the correct user's scope.

### Benefits of this Integration

-   **Centralized User Management:** All user accounts, credentials, and sessions are managed solely by the Go backend.
-   **Separation of Concerns:** The Python backend focuses entirely on its core competency (document processing and AI detection) without needing to implement complex authentication logic.
-   **Consistent Authentication:** Users have a single point of authentication, and services use a standardized method (API keys) for inter-service authorization.
-   **Enhanced Security:** Authentication logic is consolidated, reducing the attack surface and allowing security efforts to be focused on the Go backend.

### Communication

-   **Protocol:** Communication between the Python and Go backends occurs via synchronous HTTP REST API calls.
-   **Key Endpoint:** `/api/auth/validate-key` on the Go backend.
-   **Error Handling:** Standardized error responses should be used for communication failures or invalid keys to ensure the Python backend can react appropriately.

## Contributing

Contributions to the HideMe Go Backend are welcome! Please follow these guidelines to ensure a smooth process.

### Reporting Issues

-   Use the GitHub Issues tracker to report bugs, suggest features, or ask questions.
-   Provide as much detail as possible, including steps to reproduce, expected behavior, actual behavior, and your environment setup.

### Development Process

1.  **Fork the Repository:** Create your own fork of the main repository.
2.  **Create a Branch:** Create a new branch for your feature or bug fix from the `main` or `develop` branch (confirm branching strategy if specified).
    ```bash
    git checkout -b feature/your-feature-name
    # or
    git checkout -b fix/your-bug-fix
    ```
3.  **Make Changes:** Implement your changes, adhering to the project's coding style and conventions.
4.  **Write Tests:** Add unit or integration tests to cover your changes.
5.  **Run Tests:** Ensure all tests pass, including existing ones.
    ```bash
    make test
    # or
    go test ./...
    ```
6.  **Linting/Formatting:** Ensure your code adheres to Go formatting standards.
    ```bash
    go fmt ./...
    # Add any specific linter commands if used (e.g., golangci-lint)
    ```
7.  **Commit Changes:** Write clear and concise commit messages.
    ```bash
    git commit -m "feat: Add user profile update endpoint"
    ```
8.  **Push to Fork:** Push your changes to your forked repository.
    ```bash
    git push origin feature/your-feature-name
    ```
9.  **Create Pull Request:** Open a pull request (PR) from your branch to the main repository's `main` or `develop` branch.
    *   Provide a clear description of the changes in the PR.
    *   Link any relevant issues.
    *   Ensure all automated checks (CI/CD) pass.

### Coding Standards

-   Follow standard Go coding practices (`go fmt`, Effective Go).
-   Write clear, concise, and well-commented code where necessary.
-   Maintain consistency with the existing codebase style.
-   Ensure error handling is robust.

### Pull Request Process

1.  PRs will be reviewed by maintainers.
2.  Feedback may be provided, requiring further changes.
3.  Once approved and all checks pass, the PR will be merged.

## License

This project is licensed under the MIT License.

```text
MIT License

Copyright (c) 2025 HideMe AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

For licensing inquiries, please contact: *licensing@hidemeai.com*