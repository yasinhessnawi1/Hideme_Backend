// Package constants provides shared constant values used throughout the application.
//
// The securityparams.go file defines security-related constants and parameters
// used for authentication, authorization, and data privacy. These values
// ensure consistent security behavior across the application and should be
// modified with caution, as changes may affect user access, authentication,
// and data protection mechanisms.
package constants

// Context Key Names define keys used to store and retrieve values from request contexts.
// These keys are used for passing authentication and request metadata through middleware.
const (
	// UserIDContextKey is the context key for storing the authenticated user's ID.
	UserIDContextKey = "user_id"

	// UsernameContextKey is the context key for storing the authenticated user's username.
	UsernameContextKey = "username"

	// EmailContextKey is the context key for storing the authenticated user's email.
	EmailContextKey = "email"

	// RequestIDContextKey is the context key for storing the unique request identifier.
	RequestIDContextKey = "request_id"
)

// Auth Token Types define the different types of authentication tokens used in the system.
// These distinguish between short-lived access tokens and longer-lived refresh tokens.
const (
	// TokenTypeAccess identifies a token as an access token, which grants access to protected resources.
	TokenTypeAccess = "access"

	// TokenTypeRefresh identifies a token as a refresh token, which can be used to obtain new access tokens.
	TokenTypeRefresh = "refresh"
)

// Password Validation constants define requirements for passwords and usernames.
// These values enforce security policies for authentication credentials.
const (
	// MinPasswordLength is the minimum number of characters required in a password.
	MinPasswordLength = 8

	// MinUsernameLength is the minimum number of characters required in a username.
	MinUsernameLength = 3

	// MaxUsernameLength is the maximum number of characters allowed in a username.
	MaxUsernameLength = 50

	// MaxEmailLength is the maximum number of characters allowed in an email address.
	MaxEmailLength = 255
)

// Theme Types define the supported UI themes in the application.
// These values are used for user preference settings.
const (
	// ThemeSystem indicates to use the system's theme preference.
	ThemeSystem = "system"

	// ThemeLight indicates to use the light theme.
	ThemeLight = "light"

	// ThemeDark indicates to use the dark theme.
	ThemeDark = "dark"
)

// Cookie Names define the names of cookies used for storing authentication tokens.
// These cookie names are used for client-side storage of authentication state.
const (
	// RefreshTokenCookie is the name of the cookie storing the refresh token.
	RefreshTokenCookie = "refresh_token"

	// AuthTokenCookie is the name of the cookie storing the access token.
	AuthTokenCookie = "auth_token"

	// CSRFTokenCookie is the name of the cookie storing the CSRF token.
	CSRFTokenCookie = "csrf_token"
)

// Default Log Paths define the filesystem locations for different categories of logs.
// These paths separate logs based on data sensitivity for GDPR compliance.
const (
	// DefaultStandardLogPath is the default path for standard, non-sensitive logs.
	DefaultStandardLogPath = "./logs/standard"

	// DefaultPersonalLogPath is the default path for logs containing personal data.
	DefaultPersonalLogPath = "./logs/personal"

	// DefaultSensitiveLogPath is the default path for logs containing sensitive personal data.
	DefaultSensitiveLogPath = "./logs/sensitive"
)
