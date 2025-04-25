package config

import (
	"fmt"
	"io/ioutil"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
	"gopkg.in/yaml.v3"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// AppConfig represents the entire application configuration
type AppConfig struct {
	App          AppSettings         `yaml:"app"`
	Database     DatabaseSettings    `yaml:"database"`
	Server       ServerSettings      `yaml:"server"`
	JWT          JWTSettings         `yaml:"jwt"`
	APIKey       APIKeySettings      `yaml:"api_key"`
	Logging      LoggingSettings     `yaml:"logging"`
	CORS         CORSSettings        `yaml:"cors"`
	PasswordHash HashSettings        `yaml:"password_hash"`
	GDPRLogging  GDPRLoggingSettings `yaml:"gdpr_logging"`
}

// GDPRLoggingSettings contains GDPR-compliant logging configuration
type GDPRLoggingSettings struct {
	PersonalDataRetentionDays  int    `yaml:"personal_data_retention_days" env:"GDPR_PERSONAL_RETENTION_DAYS"`
	SensitiveDataRetentionDays int    `yaml:"sensitive_data_retention_days" env:"GDPR_SENSITIVE_RETENTION_DAYS"`
	StandardLogRetentionDays   int    `yaml:"standard_log_retention_days" env:"GDPR_STANDARD_RETENTION_DAYS"`
	PersonalLogPath            string `yaml:"personal_log_path" env:"GDPR_PERSONAL_LOG_PATH"`
	SensitiveLogPath           string `yaml:"sensitive_log_path" env:"GDPR_SENSITIVE_LOG_PATH"`
	StandardLogPath            string `yaml:"standard_log_path" env:"GDPR_STANDARD_LOG_PATH"`
	LogSanitizationLevel       string `yaml:"log_sanitization_level" env:"GDPR_SANITIZATION_LEVEL"`
	EnableDataSubjectAPI       bool   `yaml:"enable_data_subject_api" env:"GDPR_ENABLE_SUBJECT_API"`
}

// AppSettings contains general application settings
type AppSettings struct {
	Environment string `yaml:"environment" env:"APP_ENV"`
	Name        string `yaml:"name" env:"APP_NAME"`
	Version     string `yaml:"version" env:"APP_VERSION"`
}

// DatabaseSettings contains database connection settings
type DatabaseSettings struct {
	Host     string `yaml:"host" env:"DB_HOST"`
	Port     int    `yaml:"port" env:"DB_PORT"`
	Name     string `yaml:"name" env:"DB_NAME"`
	User     string `yaml:"user" env:"DB_USER"`
	Password string `yaml:"password" env:"DB_PASSWORD"`
	MaxConns int    `yaml:"max_conns" env:"DB_MAX_CONNS"`
	MinConns int    `yaml:"min_conns" env:"DB_MIN_CONNS"`
}

// ServerSettings contains HTTP server settings
type ServerSettings struct {
	Host            string        `yaml:"host" env:"SERVER_HOST"`
	Port            int           `yaml:"port" env:"SERVER_PORT"`
	ReadTimeout     time.Duration `yaml:"read_timeout" env:"SERVER_READ_TIMEOUT"`
	WriteTimeout    time.Duration `yaml:"write_timeout" env:"SERVER_WRITE_TIMEOUT"`
	ShutdownTimeout time.Duration `yaml:"shutdown_timeout" env:"SERVER_SHUTDOWN_TIMEOUT"`
}

// JWTSettings contains JWT authentication settings
type JWTSettings struct {
	Secret        string        `yaml:"secret" env:"JWT_SECRET"`
	Expiry        time.Duration `yaml:"expiry" env:"JWT_EXPIRY"`
	RefreshExpiry time.Duration `yaml:"refresh_expiry" env:"JWT_REFRESH_EXPIRY"`
	Issuer        string        `yaml:"issuer" env:"JWT_ISSUER"`
}

// APIKeySettings contains API key settings
type APIKeySettings struct {
	DefaultExpiry time.Duration `yaml:"default_expiry" env:"API_KEY_EXPIRY"`
}

// LoggingSettings contains logging configuration
type LoggingSettings struct {
	Level      string `yaml:"level" env:"LOG_LEVEL"`
	Format     string `yaml:"format" env:"LOG_FORMAT"`
	RequestLog bool   `yaml:"request_log" env:"LOG_REQUESTS"`
}

// CORSSettings contains CORS configuration
type CORSSettings struct {
	AllowedOrigins   []string `yaml:"allowed_origins" env:"ALLOWED_ORIGINS"`
	AllowCredentials bool     `yaml:"allow_credentials" env:"CORS_ALLOW_CREDENTIALS"`
}

// HashSettings contains password hashing settings
type HashSettings struct {
	Memory      uint32 `yaml:"memory" env:"HASH_MEMORY"`
	Iterations  uint32 `yaml:"iterations" env:"HASH_ITERATIONS"`
	Parallelism uint8  `yaml:"parallelism" env:"HASH_PARALLELISM"`
	SaltLength  uint32 `yaml:"salt_length" env:"HASH_SALT_LENGTH"`
	KeyLength   uint32 `yaml:"key_length" env:"HASH_KEY_LENGTH"`
}

// ConnectionString returns the database connection string
func (dbs *DatabaseSettings) ConnectionString() string {
	// MariaDB/MySQL connection string format: username:password@tcp(host:port)/dbname
	password := dbs.Password
	if password != "" {
		password = ":" + password
	}

	return fmt.Sprintf(
		"%s%s@tcp(%s:%d)/%s?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
		dbs.User, password, dbs.Host, dbs.Port, dbs.Name,
	)
}

// ServerAddress returns the complete server address
func (ss *ServerSettings) ServerAddress() string {
	return fmt.Sprintf("%s:%d", ss.Host, ss.Port)
}

// IsDevelopment checks if the application is running in development mode
func (as *AppSettings) IsDevelopment() bool {
	return strings.ToLower(as.Environment) == constants.EnvDevelopment
}

// IsProduction checks if the application is running in production mode
func (as *AppSettings) IsProduction() bool {
	return strings.ToLower(as.Environment) == constants.EnvProduction
}

// IsTesting checks if the application is running in testing mode
func (as *AppSettings) IsTesting() bool {
	return strings.ToLower(as.Environment) == constants.EnvTesting
}

var (
	// cfg holds the current application configuration
	cfg *AppConfig
)

// Load loads the configuration from a config file and environment variables
func Load(configPath string) (*AppConfig, error) {
	config := &AppConfig{}

	// Load configuration from file if it exists
	if _, err := os.Stat(configPath); err == nil {
		data, err := ioutil.ReadFile(configPath)
		if err != nil {
			return nil, fmt.Errorf("error reading config file: %w", err)
		}

		err = yaml.Unmarshal(data, config)
		if err != nil {
			return nil, fmt.Errorf("error parsing config file: %w", err)
		}
	}

	// Override with environment variables
	if err := LoadEnv(config); err != nil {
		return nil, fmt.Errorf("error loading environment variables: %w", err)
	}

	// Set defaults for missing values
	setDefaults(config)

	// Validate the configuration
	if err := validateConfig(config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	// Save the configuration globally
	cfg = config

	// Log the configuration (but hide sensitive values)
	logConfig(config)

	return config, nil
}

// Get returns the current application configuration
func Get() *AppConfig {
	if cfg == nil {
		log.Fatal().Msg("configuration not loaded")
	}
	return cfg
}

// setDefaults sets default values for any missing configuration
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

	// Password hash defaults
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
}

// validateConfig validates that the configuration has all required values
func validateConfig(config *AppConfig) error {
	// Validate environment
	env := strings.ToLower(config.App.Environment)
	fmt.Printf("Debug - Environment value: '%s'\n", config.App.Environment)

	if env != constants.EnvDevelopment && env != constants.EnvTesting && env != constants.EnvProduction {
		// Instead of failing, use a default and warn
		fmt.Printf("Warning: Invalid environment '%s', defaulting to 'development'\n", config.App.Environment)
		config.App.Environment = constants.EnvDevelopment
	}

	// In production, ensure we have a proper JWT secret
	if config.App.IsProduction() && (config.JWT.Secret == "" || config.JWT.Secret == "changeme") {
		return fmt.Errorf("JWT secret must be set in production")
	}

	// Database validation - connection details required
	if config.Database.User == "" {
		return fmt.Errorf("database user must be set")
	}

	// Validate log level
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

// logConfig logs the current configuration, masking sensitive values
func logConfig(config *AppConfig) {
	// Create a copy of the config to mask sensitive values
	logCfg := *config

	// Mask sensitive information
	if logCfg.Database.Password != "" {
		logCfg.Database.Password = constants.LogRedactedValue
	}
	if logCfg.JWT.Secret != "" {
		logCfg.JWT.Secret = constants.LogRedactedValue
	}

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
