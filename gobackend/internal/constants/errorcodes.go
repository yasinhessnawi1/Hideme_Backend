package constants

// Error Types
const (
	ErrorNotFound           = "resource not found"
	ErrorUnauthorized       = "unauthorized access"
	ErrorForbidden          = "forbidden access"
	ErrorBadRequest         = "invalid request"
	ErrorInternalServer     = "internal server error"
	ErrorValidation         = "validation error"
	ErrorDuplicate          = "duplicate resource"
	ErrorInvalidCredentials = "invalid credentials"
	ErrorExpiredToken       = "expired token"
	ErrorInvalidToken       = "invalid token"
)

// User-Facing Error Messages
const (
	MsgAuthRequired          = "Authentication required"
	MsgPasswordsDoNotMatch   = "Passwords do not match"
	MsgInvalidPassword       = "Invalid username or password"
	MsgAccessDenied          = "You don't have permission to access this resource"
	MsgInvalidRequest        = "The request contains invalid data"
	MsgInternalServerError   = "An internal server error occurred"
	MsgTokenExpired          = "Authentication token has expired"
	MsgInvalidToken          = "Invalid token"
	MsgRequestBodyTooLarge   = "Request body too large"
	MsgEmptyRequestBody      = "Request body must not be empty"
	MsgMalformedJSON         = "Request body contains malformed JSON"
	MsgResourceNotFound      = "The requested resource could not be found"
	MsgResourceAlreadyExists = "A resource with the same unique identifier already exists"
	MsgMethodNotAllowed      = "This method is not allowed for this resource"
	MsgUserDeleted           = "Account successfully deleted"
	MsgPasswordChanged       = "Password successfully changed"
	MsgSessionInvalidated    = "Session successfully invalidated"
	MsgAPIKeyRevoked         = "API key successfully revoked"
	MsgLogoutSuccess         = "Successfully logged out"
	MsgLogoutAllSuccess      = "Successfully logged out of all sessions"
	MsgSettingsImported      = "Settings imported successfully"
)

// Database Error Types
const (
	DBErrorDuplicateKey         = "duplicate key value violates unique constraint"
	DBErrorForeignKeyViolation  = "foreign key constraint violation"
	DBErrorNotNullViolation     = "not-null constraint violation"
	DBErrorTableDoesNotExist    = "relation does not exist"
	DBErrorColumnDoesNotExist   = "column does not exist"
	PGErrorDuplicateConstraint  = "23505"
	PGErrorForeignKeyConstraint = "23503"
	PGErrorNotNullConstraint    = "23502"
)

// Logger Constants
const (
	LogCategoryUser    = "user"
	LogCategoryAuth    = "auth"
	LogCategoryAPI     = "api"
	LogCategoryDB      = "database"
	LogCategorySystem  = "system"
	LogEventLogin      = "login"
	LogEventLogout     = "logout"
	LogEventRegister   = "register"
	LogEventAPIKey     = "api_key"
	LogEventUserUpdate = "user_update"
	LogRedactedValue   = "[REDACTED]"
)
