// Package config provides configuration management for the HideMe API Server.
// It handles loading application settings from both YAML files and environment
// variables, with environment variables taking precedence for easier deployment
// configuration and containerization.
//
// The package implements a robust configuration system with sensible defaults,
// validation, and secure handling of sensitive information. It supports different
// environments (development, testing, production) with environment-specific defaults.
//
// Configuration is loaded once at application startup and then available globally
// through the Get() function. All sensitive configuration values are masked in logs.
package config

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
	"gopkg.in/yaml.v3"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// AppConfig represents the entire application configuration.
// It contains all settings needed by the application, organized into logical groups
// to maintain a clear structure as the application grows.
// AppConfig represents the entire application configuration.
type AppConfig struct {
	// App contains general application metadata and environment settings
	App AppSettings `yaml:"app"`

	// Database contains database connection and pool settings
	Database DatabaseSettings `yaml:"database"`

	// Server contains HTTP server configuration
	Server ServerSettings `yaml:"server"`

	// JWT contains JSON Web Token authentication settings
	JWT JWTSettings `yaml:"jwt"`

	// APIKey contains API key authentication settings
	APIKey APIKeySettings `yaml:"api_key"`

	// Logging contains logging configuration
	Logging LoggingSettings `yaml:"logging"`

	// CORS contains Cross-Origin Resource Sharing settings
	CORS CORSSettings `yaml:"cors"`

	// PasswordHash contains password hashing algorithm settings
	PasswordHash HashSettings `yaml:"password_hash"`

	// GDPRLogging contains GDPR-compliant logging configuration
	GDPRLogging GDPRLoggingSettings `yaml:"gdpr_logging"`

	// Security contains settings for rate limiting and IP banning
	Security SecuritySettings `yaml:"security"`
}

// GDPRLoggingSettings contains GDPR-compliant logging configuration.
// These settings ensure that personal and sensitive data are handled according
// to data protection regulations, with appropriate retention policies.
type GDPRLoggingSettings struct {
	// PersonalDataRetentionDays defines how many days to keep logs containing personal data
	PersonalDataRetentionDays int `yaml:"personal_data_retention_days" env:"GDPR_PERSONAL_RETENTION_DAYS"`

	// SensitiveDataRetentionDays defines how many days to keep logs containing sensitive data
	SensitiveDataRetentionDays int `yaml:"sensitive_data_retention_days" env:"GDPR_SENSITIVE_RETENTION_DAYS"`

	// StandardLogRetentionDays defines how many days to keep standard operational logs
	StandardLogRetentionDays int `yaml:"standard_log_retention_days" env:"GDPR_STANDARD_RETENTION_DAYS"`

	// PersonalLogPath defines the file path for logs containing personal data
	PersonalLogPath string `yaml:"personal_log_path" env:"GDPR_PERSONAL_LOG_PATH"`

	// SensitiveLogPath defines the file path for logs containing sensitive data
	SensitiveLogPath string `yaml:"sensitive_log_path" env:"GDPR_SENSITIVE_LOG_PATH"`

	// StandardLogPath defines the file path for standard operational logs
	StandardLogPath string `yaml:"standard_log_path" env:"GDPR_STANDARD_LOG_PATH"`

	// LogSanitizationLevel defines how aggressively to sanitize logs (low, medium, high)
	LogSanitizationLevel string `yaml:"log_sanitization_level" env:"GDPR_SANITIZATION_LEVEL"`

	// EnableDataSubjectAPI enables endpoints for data subject rights (access, erasure, etc.)
	EnableDataSubjectAPI bool `yaml:"enable_data_subject_api" env:"GDPR_ENABLE_SUBJECT_API"`
}

// AppSettings contains general application settings such as environment and version.
type AppSettings struct {
	// Environment is the deployment environment (development, testing, production)
	Environment string `yaml:"environment" env:"APP_ENV"`

	// Name is the application name used in logs and other identifiers
	Name string `yaml:"name" env:"APP_NAME"`

	// Version is the application version, typically set during build
	Version string `yaml:"version" env:"APP_VERSION"`
}

// DatabaseSettings contains database connection settings.
// These settings are used to establish and configure the database connection pool.
type DatabaseSettings struct {
	// Host is the database server hostname or IP address
	Host string `yaml:"host" env:"DB_HOST"`

	// Port is the database server port
	Port int `yaml:"port" env:"DB_PORT"`

	// Name is the database name
	Name string `yaml:"name" env:"DB_NAME"`

	// User is the database username
	User string `yaml:"user" env:"DB_USER"`

	// Password is the database password (handled securely in logging)
	Password string `yaml:"password" env:"DB_PASSWORD"`

	// MaxConns is the maximum number of connections in the connection pool
	MaxConns int `yaml:"max_conns" env:"DB_MAX_CONNS"`

	// MinConns is the minimum number of idle connections in the connection pool
	MinConns int `yaml:"min_conns" env:"DB_MIN_CONNS"`
}

// ServerSettings contains HTTP server settings.
// These settings control the behavior of the HTTP server, including timeouts.
type ServerSettings struct {
	// Host is the server hostname or IP address to bind to
	Host string `yaml:"host" env:"SERVER_HOST"`

	// Port is the server port to listen on
	Port int `yaml:"port" env:"SERVER_PORT"`

	// ReadTimeout is the maximum duration for reading the entire request
	ReadTimeout time.Duration `yaml:"read_timeout" env:"SERVER_READ_TIMEOUT"`

	// WriteTimeout is the maximum duration for writing the response
	WriteTimeout time.Duration `yaml:"write_timeout" env:"SERVER_WRITE_TIMEOUT"`

	// ShutdownTimeout is the maximum duration to wait for active connections to close during shutdown
	ShutdownTimeout time.Duration `yaml:"shutdown_timeout" env:"SERVER_SHUTDOWN_TIMEOUT"`
}

// JWTSettings contains JWT authentication settings.
// These settings control the generation and validation of JWT tokens.
type JWTSettings struct {
	// Secret is the signing key for JWT tokens (handled securely in logging)
	Secret string `yaml:"secret" env:"JWT_SECRET"`

	// Expiry is the lifetime of access tokens
	Expiry time.Duration `yaml:"expiry" env:"JWT_EXPIRY"`

	// RefreshExpiry is the lifetime of refresh tokens
	RefreshExpiry time.Duration `yaml:"refresh_expiry" env:"JWT_REFRESH_EXPIRY"`

	// Issuer is the JWT issuer claim value
	Issuer string `yaml:"issuer" env:"JWT_ISSUER"`
}

// APIKeySettings contains API key settings.
type APIKeySettings struct {
	// DefaultExpiry is the default lifetime of generated API keys
	DefaultExpiry time.Duration `yaml:"default_expiry" env:"API_KEY_EXPIRY"`

	// EncryptionKey is the key used for API key encryption
	EncryptionKey string `yaml:"encryption_key" env:"API_KEY_ENCRYPTION_KEY"`
}

// LoggingSettings contains logging configuration.
// These settings control the verbosity, format, and behavior of logging.
type LoggingSettings struct {
	// Level is the minimum log level to output (debug, info, warn, error, etc.)
	Level string `yaml:"level" env:"LOG_LEVEL"`

	// Format is the log output format (json, pretty, etc.)
	Format string `yaml:"format" env:"LOG_FORMAT"`

	// RequestLog enables or disables HTTP request logging
	RequestLog bool `yaml:"request_log" env:"LOG_REQUESTS"`
}

// CORSSettings contains Cross-Origin Resource Sharing configuration.
// These settings control which origins can access the API.
type CORSSettings struct {
	// AllowedOrigins is a list of origins that can access the API
	AllowedOrigins []string `yaml:"allowed_origins" env:"ALLOWED_ORIGINS"`

	// AllowCredentials enables the Access-Control-Allow-Credentials header
	AllowCredentials bool `yaml:"allow_credentials" env:"CORS_ALLOW_CREDENTIALS"`
}

// HashSettings contains password hashing settings.
// These settings control the Argon2id password hashing algorithm parameters.
type HashSettings struct {
	// Memory is the amount of memory used by the hashing algorithm, in KiB
	Memory uint32 `yaml:"memory" env:"HASH_MEMORY"`

	// Iterations is the number of iterations (passes) over the memory
	Iterations uint32 `yaml:"iterations" env:"HASH_ITERATIONS"`

	// Parallelism is the degree of parallelism (number of threads)
	Parallelism uint8 `yaml:"parallelism" env:"HASH_PARALLELISM"`

	// SaltLength is the length of the salt in bytes
	SaltLength uint32 `yaml:"salt_length" env:"HASH_SALT_LENGTH"`

	// KeyLength is the length of the generated hash in bytes
	KeyLength uint32 `yaml:"key_length" env:"HASH_KEY_LENGTH"`
}

// SecuritySettings contains configuration for security features.
type SecuritySettings struct {
	// RateLimiting configures request rate limiting
	RateLimiting RateLimitSettings `yaml:"rate_limiting" env:"RATE_LIMITING"`

	// IPBanning configures IP address banning
	IPBanning IPBanSettings `yaml:"ip_banning" env:"IP_BANNING"`
}

// RateLimitSettings configures rate limiting behavior.
type RateLimitSettings struct {
	// Enabled determines if rate limiting is active
	Enabled bool `yaml:"enabled" env:"RATE_LIMIT_ENABLED"`

	// DefaultRate is the default requests per second allowed
	DefaultRate float64 `yaml:"default_rate" env:"RATE_LIMIT_DEFAULT_RATE"`

	// DefaultBurst is the default maximum burst allowed
	DefaultBurst int `yaml:"default_burst" env:"RATE_LIMIT_DEFAULT_BURST"`

	// AuthRate is the rate limit for authentication endpoints
	AuthRate float64 `yaml:"auth_rate" env:"RATE_LIMIT_AUTH_RATE"`

	// AuthBurst is the burst limit for authentication endpoints
	AuthBurst int `yaml:"auth_burst" env:"RATE_LIMIT_AUTH_BURST"`

	// APIRate is the rate limit for API endpoints
	APIRate float64 `yaml:"api_rate" env:"RATE_LIMIT_API_RATE"`

	// APIBurst is the burst limit for API endpoints
	APIBurst int `yaml:"api_burst" env:"RATE_LIMIT_API_BURST"`
}

// IPBanSettings configures IP address banning behavior.
type IPBanSettings struct {
	// Enabled determines if IP banning is active
	Enabled bool `yaml:"enabled" env:"IP_BAN_ENABLED"`

	// CacheRefreshInterval is how often to refresh the ban cache
	CacheRefreshInterval time.Duration `yaml:"cache_refresh_interval" env:"IP_BAN_CACHE_REFRESH"`

	// AutoBanEnabled enables automatic banning of suspicious IPs
	AutoBanEnabled bool `yaml:"auto_ban_enabled" env:"IP_BAN_AUTO_ENABLED"`

	// AutoBanThreshold is the number of suspicious activities before ban
	AutoBanThreshold int `yaml:"auto_ban_threshold" env:"IP_BAN_AUTO_THRESHOLD"`

	// AutoBanWindow is the time window to consider for suspicious activities
	AutoBanWindow time.Duration `yaml:"auto_ban_window" env:"IP_BAN_AUTO_WINDOW"`

	// AutoBanDuration is how long automatic bans last
	AutoBanDuration time.Duration `yaml:"auto_ban_duration" env:"IP_BAN_AUTO_DURATION"`
}

// ConnectionString returns the database connection string formatted for the database driver.
// It properly escapes and formats all connection parameters for MariaDB/MySQL.
//
// Returns:
//   - A connection string in the format "username:password@tcp(host:port)/dbname?params"
func (dbs *DatabaseSettings) ConnectionString() string {
	// MariaDB/MySQL connection string format: username:password@tcp(host:port)/dbname
	password := dbs.Password
	if password != "" {
		password = ":" + password
	}

	// Build the connection string with additional parameters
	// - parseTime=true: Handles DATE and DATETIME values properly
	// - charset=utf8mb4: Uses full UTF-8 support for 4-byte characters
	// - collation=utf8mb4_unicode_ci: Case-insensitive Unicode collation
	return fmt.Sprintf(
		"%s%s@tcp(%s:%d)/%s?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
		dbs.User, password, dbs.Host, dbs.Port, dbs.Name,
	)
}

// ServerAddress returns the complete server address as a string.
// This is used for binding the HTTP server to the configured host and port.
//
// Returns:
//   - A formatted string in the form "host:port"
func (ss *ServerSettings) ServerAddress() string {
	return fmt.Sprintf("%s:%d", ss.Host, ss.Port)
}

// IsDevelopment checks if the application is running in development mode.
//
// Returns:
//   - true if the environment is "development", false otherwise
func (as *AppSettings) IsDevelopment() bool {
	return strings.ToLower(as.Environment) == constants.EnvDevelopment
}

// IsProduction checks if the application is running in production mode.
//
// Returns:
//   - true if the environment is "production", false otherwise
func (as *AppSettings) IsProduction() bool {
	return strings.ToLower(as.Environment) == constants.EnvProduction
}

// IsTesting checks if the application is running in testing mode.
//
// Returns:
//   - true if the environment is "testing", false otherwise
func (as *AppSettings) IsTesting() bool {
	return strings.ToLower(as.Environment) == constants.EnvTesting
}

var (
	// cfg holds the current application configuration.
	// It's initialized by Load() and accessed via Get().
	cfg *AppConfig
)

// Load loads the configuration from a config file and environment variables.
// Environment variables take precedence over file-based configuration to allow
// for easy deployment configuration and containerization.
//
// Parameters:
//   - configPath: Path to the YAML configuration file (can be empty if using only environment variables)
//
// Returns:
//   - A pointer to the loaded and validated AppConfig
//   - An error if loading or validation fails
func Load(configPath string) (*AppConfig, error) {
	config := &AppConfig{}

	// Load configuration from file if it exists
	if _, err := os.Stat(configPath); err == nil {
		data, err := os.ReadFile(configPath)
		if err != nil {
			return nil, fmt.Errorf("error reading config file: %w", err)
		}

		err = yaml.Unmarshal(data, config)
		if err != nil {
			return nil, fmt.Errorf("error parsing config file: %w", err)
		}
	}

	// Override with environment variables
	// This allows for easy configuration in container environments
	if err := LoadEnv(config); err != nil {
		return nil, fmt.Errorf("error loading environment variables: %w", err)
	}

	// Set defaults for missing values
	// This ensures the application can run with minimal configuration
	setDefaults(config)

	// Validate the configuration
	// This catches configuration errors early, before they cause runtime issues
	if err := validateConfig(config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	// Save the configuration globally for access through Get()
	cfg = config

	// Log the configuration (but hide sensitive values)
	logConfig(config)

	return config, nil
}

// Get returns the current application configuration.
// This provides global access to the configuration after it has been loaded.
//
// Returns:
//   - A pointer to the current AppConfig
//
// Panics:
//   - If configuration hasn't been loaded yet via Load()
func Get() *AppConfig {
	if cfg == nil {
		log.Fatal().Msg("configuration not loaded")
	}
	return cfg
}

// setDefaults sets default values for any missing configuration settings.
// This allows the application to run with minimal explicit configuration.
//
// Parameters:
//   - config: The configuration to set defaults for
//
// setDefaults sets default values for any missing configuration settings.
// This allows the application to run with minimal explicit configuration.
//
// Parameters:
//   - config: The configuration to set defaults for
func setDefaults(config *AppConfig) {
	// App defaults
	if config.App.Environment == "" {
		config.App.Environment = constants.EnvDevelopment
	}

	if config.App.Version == "" {
		config.App.Version = "1.0.0"
	}

	if config.Server.Port == 0 {
		config.Server.Port = constants.DefaultServerPort
	}
	if config.Server.ReadTimeout == 0 {
		config.Server.ReadTimeout = constants.DefaultReadTimeout
	}
	if config.Server.WriteTimeout == 0 {
		config.Server.WriteTimeout = constants.DefaultWriteTimeout
	}
	if config.Server.ShutdownTimeout == 0 {
		config.Server.ShutdownTimeout = constants.DefaultShutdownTimeout
	}

	if config.Database.MaxConns == 0 {
		config.Database.MaxConns = constants.DefaultDBMaxConnections
	}
	if config.Database.MinConns == 0 {
		config.Database.MinConns = constants.DefaultDBMinConnections
	}

	// JWT defaults
	if config.JWT.Expiry == 0 {
		config.JWT.Expiry = constants.DefaultJWTExpiry
	}
	if config.JWT.RefreshExpiry == 0 {
		config.JWT.RefreshExpiry = constants.DefaultJWTRefreshExpiry
	}
	if config.JWT.Issuer == "" {
		config.JWT.Issuer = constants.DefaultJWTIssuer
	}

	// API Key defaults
	if config.APIKey.DefaultExpiry == 0 {
		config.APIKey.DefaultExpiry = constants.DefaultAPIKeyExpiry
	}

	// Logging defaults
	if config.Logging.Level == "" {
		config.Logging.Level = constants.DefaultLogLevel
	}
	if config.Logging.Format == "" {
		config.Logging.Format = constants.DefaultLogFormat
	}

	// CORS defaults
	if len(config.CORS.AllowedOrigins) == 0 {
		config.CORS.AllowedOrigins = []string{"*"}
	}

	// Password hash defaults - adjust based on environment for security/performance balance
	if config.PasswordHash.Memory == 0 {
		// Lower for development, higher for production
		if config.App.IsProduction() {
			config.PasswordHash.Memory = constants.DefaultPasswordHashMemory
		} else {
			config.PasswordHash.Memory = constants.DevPasswordHashMemory
		}
	}
	if config.PasswordHash.Iterations == 0 {
		if config.App.IsProduction() {
			config.PasswordHash.Iterations = constants.DefaultPasswordHashIterations
		} else {
			config.PasswordHash.Iterations = constants.DevPasswordHashIterations
		}
	}
	if config.PasswordHash.Parallelism == 0 {
		config.PasswordHash.Parallelism = constants.DefaultPasswordHashParallelism
	}
	if config.PasswordHash.SaltLength == 0 {
		config.PasswordHash.SaltLength = constants.DefaultPasswordHashSaltLength
	}
	if config.PasswordHash.KeyLength == 0 {
		config.PasswordHash.KeyLength = constants.DefaultPasswordHashKeyLength
	}

	// GDPR logging defaults
	if config.GDPRLogging.StandardLogRetentionDays == 0 {
		config.GDPRLogging.StandardLogRetentionDays = constants.StandardLogRetentionDays
	}
	if config.GDPRLogging.PersonalDataRetentionDays == 0 {
		config.GDPRLogging.PersonalDataRetentionDays = constants.PersonalDataRetentionDays
	}
	if config.GDPRLogging.SensitiveDataRetentionDays == 0 {
		config.GDPRLogging.SensitiveDataRetentionDays = constants.SensitiveDataRetentionDays
	}
	if config.GDPRLogging.StandardLogPath == "" {
		config.GDPRLogging.StandardLogPath = constants.DefaultStandardLogPath
	}
	if config.GDPRLogging.PersonalLogPath == "" {
		config.GDPRLogging.PersonalLogPath = constants.DefaultPersonalLogPath
	}
	if config.GDPRLogging.SensitiveLogPath == "" {
		config.GDPRLogging.SensitiveLogPath = constants.DefaultSensitiveLogPath
	}
	if config.GDPRLogging.LogSanitizationLevel == "" {
		config.GDPRLogging.LogSanitizationLevel = "medium"
	}

	// Security defaults - Rate Limiting
	if !config.App.IsProduction() {
		// Enable rate limiting by default in production
		config.Security.RateLimiting.Enabled = true
	}

	if config.Security.RateLimiting.DefaultRate == 0 {
		config.Security.RateLimiting.DefaultRate = 100 // 10 requests per second
	}

	if config.Security.RateLimiting.DefaultBurst == 0 {
		config.Security.RateLimiting.DefaultBurst = 50 // Burst of 30 requests
	}

	if config.Security.RateLimiting.AuthRate == 0 {
		config.Security.RateLimiting.AuthRate = 10 // 3 requests per second for auth
	}

	if config.Security.RateLimiting.AuthBurst == 0 {
		config.Security.RateLimiting.AuthBurst = 15 // Burst of 5 for auth
	}

	if config.Security.RateLimiting.APIRate == 0 {
		config.Security.RateLimiting.APIRate = 40 // 20 requests per second for API
	}

	if config.Security.RateLimiting.APIBurst == 0 {
		config.Security.RateLimiting.APIBurst = 50 // Burst of 50 for API
	}

	// Security defaults - IP Banning
	if !config.App.IsProduction() {
		// Enable IP banning by default in production
		config.Security.IPBanning.Enabled = true
	}

	if config.Security.IPBanning.CacheRefreshInterval == 0 {
		config.Security.IPBanning.CacheRefreshInterval = 5 * time.Minute
	}

	if !config.Security.IPBanning.AutoBanEnabled {
		// Auto-ban is enabled by default in production
		config.Security.IPBanning.AutoBanEnabled = config.App.IsProduction()
	}

	if config.Security.IPBanning.AutoBanThreshold == 0 {
		config.Security.IPBanning.AutoBanThreshold = 5 // Ban after 5 suspicious activities
	}

	if config.Security.IPBanning.AutoBanWindow == 0 {
		config.Security.IPBanning.AutoBanWindow = 10 * time.Minute // Within 5 minutes
	}

	if config.Security.IPBanning.AutoBanDuration == 0 {
		config.Security.IPBanning.AutoBanDuration = 3 * time.Hour // Ban for 3 hours
	}
}

// validateConfig validates that the configuration has all required values
// and that those values are valid for their intended purpose.
//
// Parameters:
//   - config: The configuration to validate
//
// Returns:
//   - An error if validation fails, nil if the configuration is valid
func validateConfig(config *AppConfig) error {
	// Validate environment - must be one of the predefined environments
	env := strings.ToLower(config.App.Environment)
	fmt.Printf("Debug - Environment value: '%s'\n", config.App.Environment)

	if env != constants.EnvDevelopment && env != constants.EnvTesting && env != constants.EnvProduction {
		// Instead of failing, use a default and warn
		fmt.Printf("Warning: Invalid environment '%s', defaulting to 'development'\n", config.App.Environment)
		config.App.Environment = constants.EnvDevelopment
	}

	// Database validation - connection details required
	if config.Database.User == "" {
		return fmt.Errorf("database user must be set")
	}

	// Validate log level - must be one of the predefined levels
	logLevel := strings.ToLower(config.Logging.Level)
	validLevels := []string{"debug", "info", "warn", "error", "fatal", "panic"}
	validLevel := false
	for _, level := range validLevels {
		if logLevel == level {
			validLevel = true
			break
		}
	}
	if !validLevel {
		return fmt.Errorf("invalid log level: %s", config.Logging.Level)
	}

	return nil
}

// logConfig logs the current configuration, masking sensitive values.
// This provides visibility into the active configuration while protecting
// sensitive information like passwords and secrets.
//
// Parameters:
//   - config: The configuration to log
func logConfig(config *AppConfig) {
	// Create a copy of the config to mask sensitive values
	logCfg := *config

	// Mask sensitive information to prevent accidental exposure in logs
	if logCfg.Database.Password != "" {
		logCfg.Database.Password = constants.LogRedactedValue
	}
	if logCfg.JWT.Secret != "" {
		logCfg.JWT.Secret = constants.LogRedactedValue
	}

	// Log key configuration values for operational visibility
	log.Info().
		Str("environment", logCfg.App.Environment).
		Str("version", logCfg.App.Version).
		Str("server", logCfg.Server.ServerAddress()).
		Str("db_host", logCfg.Database.Host).
		Int("db_port", logCfg.Database.Port).
		Str("db_name", logCfg.Database.Name).
		Str("log_level", logCfg.Logging.Level).
		Msg("Configuration loaded")
}
