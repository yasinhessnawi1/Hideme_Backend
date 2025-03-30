package config

import (
	"fmt"
	"io/ioutil"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
	"gopkg.in/yaml.v3"
)

// Environment types
const (
	EnvDevelopment = "development"
	EnvTesting     = "testing"
	EnvProduction  = "production"
)

// AppConfig represents the entire application configuration
type AppConfig struct {
	App          AppSettings      `yaml:"app"`
	Database     DatabaseSettings `yaml:"database"`
	Server       ServerSettings   `yaml:"server"`
	JWT          JWTSettings      `yaml:"jwt"`
	APIKey       APIKeySettings   `yaml:"api_key"`
	Logging      LoggingSettings  `yaml:"logging"`
	CORS         CORSSettings     `yaml:"cors"`
	PasswordHash HashSettings     `yaml:"password_hash"`
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
	return strings.ToLower(as.Environment) == EnvDevelopment
}

// IsProduction checks if the application is running in production mode
func (as *AppSettings) IsProduction() bool {
	return strings.ToLower(as.Environment) == EnvProduction
}

// IsTesting checks if the application is running in testing mode
func (as *AppSettings) IsTesting() bool {
	return strings.ToLower(as.Environment) == EnvTesting
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
		config.App.Environment = EnvDevelopment
	}
	if config.App.Name == "" {
		config.App.Name = "HideMe"
	}
	if config.App.Version == "" {
		config.App.Version = "1.0.0"
	}

	// Server defaults
	if config.Server.Host == "" {
		config.Server.Host = "127.0.0.1"
	}
	if config.Server.Port == 0 {
		config.Server.Port = 8080 // Changed from 3306 to 8080 for web server
	}
	if config.Server.ReadTimeout == 0 {
		config.Server.ReadTimeout = 5 * time.Second
	}
	if config.Server.WriteTimeout == 0 {
		config.Server.WriteTimeout = 10 * time.Second
	}
	if config.Server.ShutdownTimeout == 0 {
		config.Server.ShutdownTimeout = 30 * time.Second
	}

	// Database defaults
	if config.Database.Host == "" {
		config.Database.Host = "localhost"
	}
	if config.Database.Port == 0 {
		config.Database.Port = 3306 // changed from 3306 to 3000
	}
	if config.Database.Name == "" {
		config.Database.Name = "hideme"
	}
	// Add default database user and password
	if config.Database.User == "" {
		config.Database.User = "root" // Default MySQL user
	}
	if config.Database.Password == "" {
		config.Database.Password = "" // Default password (change if needed)
	}
	if config.Database.MaxConns == 0 {
		config.Database.MaxConns = 20
	}
	if config.Database.MinConns == 0 {
		config.Database.MinConns = 5
	}

	// JWT defaults
	if config.JWT.Expiry == 0 {
		config.JWT.Expiry = 15 * time.Minute
	}
	if config.JWT.RefreshExpiry == 0 {
		config.JWT.RefreshExpiry = 7 * 24 * time.Hour
	}
	if config.JWT.Issuer == "" {
		config.JWT.Issuer = "hideme-api"
	}

	// API Key defaults
	if config.APIKey.DefaultExpiry == 0 {
		config.APIKey.DefaultExpiry = 90 * 24 * time.Hour // 90 days
	}

	// Logging defaults
	if config.Logging.Level == "" {
		config.Logging.Level = "info"
	}
	if config.Logging.Format == "" {
		config.Logging.Format = "json"
	}

	// CORS defaults
	if len(config.CORS.AllowedOrigins) == 0 {
		config.CORS.AllowedOrigins = []string{"*"}
	}

	// Password hash defaults
	if config.PasswordHash.Memory == 0 {
		// Lower for development, higher for production
		if config.App.IsProduction() {
			config.PasswordHash.Memory = 64 * 1024
		} else {
			config.PasswordHash.Memory = 16 * 1024
		}
	}
	if config.PasswordHash.Iterations == 0 {
		if config.App.IsProduction() {
			config.PasswordHash.Iterations = 3
		} else {
			config.PasswordHash.Iterations = 1
		}
	}
	if config.PasswordHash.Parallelism == 0 {
		config.PasswordHash.Parallelism = 2
	}
	if config.PasswordHash.SaltLength == 0 {
		config.PasswordHash.SaltLength = 16
	}
	if config.PasswordHash.KeyLength == 0 {
		config.PasswordHash.KeyLength = 32
	}
}

// validateConfig validates that the configuration has all required values
func validateConfig(config *AppConfig) error {
	// Validate environment
	env := strings.ToLower(config.App.Environment)
	fmt.Printf("Debug - Environment value: '%s'\n", config.App.Environment)

	if env != EnvDevelopment && env != EnvTesting && env != EnvProduction {
		// Instead of failing, use a default and warn
		fmt.Printf("Warning: Invalid environment '%s', defaulting to 'development'\n", config.App.Environment)
		config.App.Environment = EnvDevelopment
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
		logCfg.Database.Password = "********"
	}
	if logCfg.JWT.Secret != "" {
		logCfg.JWT.Secret = "********"
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
