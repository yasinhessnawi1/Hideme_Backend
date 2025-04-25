// Package constants provides shared constant values used throughout the application.
//
// The errorcodes.go file defines constants related to error handling, categorization,
// and messaging. These constants ensure consistent error reporting and handling
// throughout the application. User-facing error messages are carefully crafted to
// be informative without revealing sensitive implementation details that could aid
// in potential attacks.
package constants

// Error Types define the categories of errors that can occur in the application.
// These are used for internal error classification and handling.
const (
	// ErrorNotFound indicates that a requested resource could not be found.
	ErrorNotFound = "resource not found"

	// ErrorUnauthorized indicates that authentication is required but was not provided.
	ErrorUnauthorized = "unauthorized access"

	// ErrorForbidden indicates that the requester lacks sufficient permissions.
	ErrorForbidden = "forbidden access"

	// ErrorBadRequest indicates that the request was malformed or invalid.
	ErrorBadRequest = "invalid request"

	// ErrorInternalServer indicates an unexpected internal error.
	ErrorInternalServer = "internal server error"

	// ErrorValidation indicates that input validation failed.
	ErrorValidation = "validation error"

	// ErrorDuplicate indicates an attempt to create a resource that already exists.
	ErrorDuplicate = "duplicate resource"

	// ErrorInvalidCredentials indicates that authentication credentials are incorrect.
	ErrorInvalidCredentials = "invalid credentials"

	// ErrorExpiredToken indicates that an authentication token has expired.
	ErrorExpiredToken = "expired token"

	// ErrorInvalidToken indicates that an authentication token is malformed or invalid.
	ErrorInvalidToken = "invalid token"
)

// User-Facing Error Messages define standardized messages that can be safely presented to users.
// These messages provide useful information without exposing sensitive system details.
const (
	// MsgAuthRequired indicates that the user must authenticate to access the resource.
	MsgAuthRequired = "Authentication required"

	// MsgPasswordsDoNotMatch indicates that the provided passwords do not match.
	MsgPasswordsDoNotMatch = "Passwords do not match"

	// MsgInvalidPassword indicates that login credentials are incorrect.
	MsgInvalidPassword = "Invalid username or password"

	// MsgAccessDenied indicates that the user lacks permission for the requested action.
	MsgAccessDenied = "You don't have permission to access this resource"

	// MsgInternalServerError provides a generic server error message.
	MsgInternalServerError = "An internal server error occurred"

	// MsgTokenExpired indicates that the user's authentication token has expired.
	MsgTokenExpired = "Authentication token has expired"

	// MsgInvalidToken indicates that the provided token is invalid.
	MsgInvalidToken = "Invalid token"

	// MsgRequestBodyTooLarge indicates that the request payload exceeds size limits.
	MsgRequestBodyTooLarge = "Request body too large"

	// MsgEmptyRequestBody indicates that a request body was expected but not provided.
	MsgEmptyRequestBody = "Request body must not be empty"

	// MsgMalformedJSON indicates that the request body contains invalid JSON.
	MsgMalformedJSON = "Request body contains malformed JSON"

	// MsgResourceNotFound indicates that the requested resource does not exist.
	MsgResourceNotFound = "The requested resource could not be found"

	// MsgResourceAlreadyExists indicates a duplicate resource conflict.
	MsgResourceAlreadyExists = "A resource with the same unique identifier already exists"

	// MsgMethodNotAllowed indicates that the HTTP method is not supported for the endpoint.
	MsgMethodNotAllowed = "This method is not allowed for this resource"

	// MsgUserDeleted confirms successful account deletion.
	MsgUserDeleted = "Account successfully deleted"

	// MsgPasswordChanged confirms successful password change.
	MsgPasswordChanged = "Password successfully changed"

	// MsgSessionInvalidated confirms successful session invalidation.
	MsgSessionInvalidated = "Session successfully invalidated"

	// MsgAPIKeyRevoked confirms successful API key revocation.
	MsgAPIKeyRevoked = "API key successfully revoked"

	// MsgLogoutSuccess confirms successful logout.
	MsgLogoutSuccess = "Successfully logged out"

	// MsgLogoutAllSuccess confirms successful logout from all sessions.
	MsgLogoutAllSuccess = "Successfully logged out of all sessions"

	// MsgSettingsImported confirms successful settings import.
	MsgSettingsImported = "Settings imported successfully"
)

// Database Error Types define constants for recognizing and handling database-specific errors.
// These constants help identify specific types of database constraint violations.
const (
	// DBErrorDuplicateKey is the PostgreSQL error message for unique constraint violations.
	DBErrorDuplicateKey = "duplicate key value violates unique constraint"

	// PGErrorDuplicateConstraint is the PostgreSQL error code for unique constraint violations.
	PGErrorDuplicateConstraint = "23505"

	// PGErrorForeignKeyConstraint is the PostgreSQL error code for foreign key violations.
	PGErrorForeignKeyConstraint = "23503"

	// PGErrorNotNullConstraint is the PostgreSQL error code for not-null constraint violations.
	PGErrorNotNullConstraint = "23502"
)

// Logger Constants define values used for structured logging.
// These constants ensure consistent log formatting and categorization.
const (
	// LogCategoryUser is the log category for user-related events.
	LogCategoryUser = "user"

	// LogCategoryAuth is the log category for authentication-related events.
	LogCategoryAuth = "auth"

	// LogEventLogin is the log event type for user login.
	LogEventLogin = "login"

	// LogEventRegister is the log event type for user registration.
	LogEventRegister = "register"

	// LogEventAPIKey is the log event type for API key operations.
	LogEventAPIKey = "api_key"

	// LogEventUserUpdate is the log event type for user profile updates.
	LogEventUserUpdate = "user_update"

	// LogRedactedValue is used to replace sensitive values in logs.
	LogRedactedValue = "[REDACTED]"
)
