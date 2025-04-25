package constants

// Default Pagination Values
const (
	DefaultPage     = 1
	DefaultPageSize = 20
	MaxPageSize     = 100
	MinPageSize     = 1
)

// Default Configuration Values
const (
	DefaultServerPort       = 8080
	DefaultDBMaxConnections = 20
	DefaultDBMinConnections = 5
	DefaultLogLevel         = "info"
	DefaultLogFormat        = "json"
	DefaultTheme            = "system"
)

// Environment Types
const (
	EnvDevelopment = "development"
	EnvTesting     = "testing"
	EnvProduction  = "production"
)

// File Size Limits
const (
	MaxRequestBodySize = 1048576  // 1MB in bytes
	MaxUploadFileSize  = 10485760 // 10MB in bytes
)

// Default Password Hash Settings
const (
	DefaultPasswordHashMemory      = 64 * 1024
	DefaultPasswordHashIterations  = 3
	DefaultPasswordHashParallelism = 2
	DefaultPasswordHashSaltLength  = 16
	DefaultPasswordHashKeyLength   = 32

	DevPasswordHashMemory     = 16 * 1024
	DevPasswordHashIterations = 1
)

// Default GDPR Retention Periods (in days)
const (
	StandardLogRetentionDays   = 90
	PersonalDataRetentionDays  = 30
	SensitiveDataRetentionDays = 15
)

// API Key and Auth Constants
const (
	DefaultJWTIssuer            = "hideme-api"
	BearerTokenPrefix           = "Bearer "
	APIKeyRandomStringLength    = 32
	APIKeyDurationFormat30Days  = "30d"
	APIKeyDurationFormat90Days  = "90d"
	APIKeyDurationFormat180Days = "180d"
	APIKeyDurationFormat365Days = "365d"
)
