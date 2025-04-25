// Package constants provides shared constant values used throughout the application.
//
// The defaults.go file defines default values and limits used throughout the application.
// These constants provide sensible defaults for configuration settings, establish
// boundaries for resource usage, and define security parameters. Changes to these
// values may significantly impact application behavior, performance, and security.
package constants

// Default Pagination Values define the parameters used for paginated responses.
// These constants ensure consistent and reasonable pagination behavior.
const (
	// DefaultPage is the default page number for paginated results when not specified.
	DefaultPage = 1

	// DefaultPageSize is the default number of items per page when not specified.
	DefaultPageSize = 20

	// MaxPageSize is the maximum allowable page size to prevent excessive resource usage.
	MaxPageSize = 100

	// MinPageSize is the minimum allowable page size.
	MinPageSize = 1
)

// Default Configuration Values define fallback settings when not specified in configuration.
// These constants provide sensible defaults for core application settings.
const (
	// DefaultServerPort is the default HTTP server port.
	DefaultServerPort = 8080

	// DefaultDBMaxConnections is the default maximum number of database connections.
	DefaultDBMaxConnections = 20

	// DefaultDBMinConnections is the default minimum number of database connections.
	DefaultDBMinConnections = 5

	// DefaultLogLevel is the default logging verbosity level.
	DefaultLogLevel = "info"

	// DefaultLogFormat is the default logging output format.
	DefaultLogFormat = "json"
)

// Environment Types define the recognized application running environments.
// These constants are used to adjust behavior based on the deployment environment.
const (
	// EnvDevelopment identifies a development environment with debugging features enabled.
	EnvDevelopment = "development"

	// EnvTesting identifies a testing environment for automated tests.
	EnvTesting = "testing"

	// EnvProduction identifies a production environment with optimized settings.
	EnvProduction = "production"
)

// File Size Limits define the maximum allowed sizes for various uploads.
// These constants help prevent denial of service attacks via excessive resource consumption.
const (
	// MaxRequestBodySize is the maximum size in bytes for HTTP request bodies.
	MaxRequestBodySize = 1048576 // 1MB in bytes
)

// Default Password Hash Settings define the parameters for password hashing.
// These constants balance security and performance for password storage.
const (
	// DefaultPasswordHashMemory is the memory cost parameter for Argon2id hashing.
	// Higher values increase security but require more memory.
	DefaultPasswordHashMemory = 64 * 1024

	// DefaultPasswordHashIterations is the number of iterations for Argon2id hashing.
	// Higher values increase security but require more CPU time.
	DefaultPasswordHashIterations = 3

	// DefaultPasswordHashParallelism is the parallelism parameter for Argon2id hashing.
	// This affects the number of threads used during hashing.
	DefaultPasswordHashParallelism = 2

	// DefaultPasswordHashSaltLength is the length in bytes of the random salt.
	// Longer salts increase resistance to rainbow table attacks.
	DefaultPasswordHashSaltLength = 16

	// DefaultPasswordHashKeyLength is the length in bytes of the generated hash.
	// Longer hashes increase resistance to brute force attacks.
	DefaultPasswordHashKeyLength = 32

	// DevPasswordHashMemory is a reduced memory setting for development environments.
	// This allows faster startup in resource-constrained development environments.
	DevPasswordHashMemory = 16 * 1024

	// DevPasswordHashIterations is a reduced iteration count for development environments.
	// This allows faster startup in resource-constrained development environments.
	DevPasswordHashIterations = 1
)

// Default GDPR Retention Periods define how long different categories of logs are kept.
// These constants ensure compliance with data minimization principles.
const (
	// StandardLogRetentionDays is the number of days to retain standard logs.
	StandardLogRetentionDays = 90

	// PersonalDataRetentionDays is the number of days to retain logs with personal data.
	PersonalDataRetentionDays = 30

	// SensitiveDataRetentionDays is the number of days to retain logs with sensitive data.
	SensitiveDataRetentionDays = 15
)

// API Key and Auth Constants define values related to API key and token management.
// These constants control API key generation and authentication token behavior.
const (
	// DefaultJWTIssuer is the issuer claim value for JWT tokens.
	DefaultJWTIssuer = "hideme-api"

	// BearerTokenPrefix is the prefix for Authorization header bearer tokens.
	BearerTokenPrefix = "Bearer "

	// APIKeyRandomStringLength is the length of randomly generated API key strings.
	APIKeyRandomStringLength = 32

	// APIKeyDurationFormat30Days is the string representation of a 30-day API key duration.
	APIKeyDurationFormat30Days = "30d"

	// APIKeyDurationFormat90Days is the string representation of a 90-day API key duration.
	APIKeyDurationFormat90Days = "90d"

	// APIKeyDurationFormat180Days is the string representation of a 180-day API key duration.
	APIKeyDurationFormat180Days = "180d"

	// APIKeyDurationFormat365Days is the string representation of a 365-day API key duration.
	APIKeyDurationFormat365Days = "365d"
)
