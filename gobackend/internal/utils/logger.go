package utils

import (
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// InitLogger initializes the application logger with the given configuration
func InitLogger(cfg *config.AppConfig) {
	// Set global log level
	level, err := zerolog.ParseLevel(strings.ToLower(cfg.Logging.Level))
	if err != nil {
		// Default to info level if invalid
		level = zerolog.InfoLevel
	}
	zerolog.SetGlobalLevel(level)

	// Configure logger output format
	var output io.Writer = os.Stdout
	if strings.ToLower(cfg.Logging.Format) == "console" && !cfg.App.IsProduction() {
		output = zerolog.ConsoleWriter{
			Out:        os.Stdout,
			TimeFormat: time.RFC3339,
			NoColor:    false, // Enable colors for development
		}
	}

	// Set global logger
	log.Logger = zerolog.New(output).
		With().
		Timestamp().
		Str("app", cfg.App.Name).
		Str("version", cfg.App.Version).
		Str("env", cfg.App.Environment).
		Logger()

	log.Info().Msg("Logger initialized")
}

// RequestLogger creates a logger with request-specific context
func RequestLogger(requestID, userID, method, path string) zerolog.Logger {
	logger := log.With().
		Str("request_id", requestID).
		Str("method", method).
		Str("path", path)

	if userID != "" {
		logger = logger.Str("user_id", userID)
	}

	return logger.Logger()
}

/*
// ContextLogger creates a logger with the given context values
func ContextLogger(context map[string]interface{}) zerolog.Logger {
	contextEvent := log.With()
	for key, value := range context {
		switch v := value.(type) {
		case string:
			contextEvent = contextEvent.Str(key, v)
		case int:
			contextEvent = contextEvent.Int(key, v)
		case int64:
			contextEvent = contextEvent.Int64(key, v)
		case float64:
			contextEvent = contextEvent.Float64(key, v)
		case bool:
			contextEvent = contextEvent.Bool(key, v)
		case error:
			contextEvent = contextEvent.Err(v)
		default:
			contextEvent = contextEvent.Interface(key, v)
		}
	}
	return contextEvent.Logger()
}

*/

// LogHTTPRequest logs an HTTP request with request details
func LogHTTPRequest(requestID, method, path, remoteAddr, userAgent string, statusCode int, latency time.Duration) {
	// Only log some paths at debug level to reduce noise
	event := log.Debug()

	// Health check and other high-volume endpoints can be demoted to debug level
	if path == "/health" || path == "/metrics" {
		if zerolog.GlobalLevel() != zerolog.DebugLevel {
			return // Skip logging entirely for high-volume endpoints in non-debug mode
		}
	}

	// Elevate error responses to warning/error level
	if statusCode >= 400 && statusCode < 500 {
		event = log.Warn()
	} else if statusCode >= 500 {
		event = log.Error()
	} else if strings.HasPrefix(path, "/api") {
		// Log API requests at info level
		event = log.Info()
	}

	// Include request details
	event.
		Str("request_id", requestID).
		Str("method", method).
		Str("path", path).
		Str("remote_addr", remoteAddr).
		Str("user_agent", userAgent).
		Int("status", statusCode).
		Dur("latency", latency).
		Msg("HTTP Request")
}

// LogError logs an error with context information
func LogError(err error, context map[string]interface{}) {
	event := log.Error().Err(err)

	// Add context information
	for key, value := range context {
		switch v := value.(type) {
		case string:
			event = event.Str(key, v)
		case int:
			event = event.Int(key, v)
		case int64:
			event = event.Int64(key, v)
		case float64:
			event = event.Float64(key, v)
		case bool:
			event = event.Bool(key, v)
		default:
			event = event.Interface(key, v)
		}
	}

	event.Msg("Error occurred")
}

// LogPanic logs a recovered panic value
func LogPanic(recovered interface{}, stack []byte) {
	log.Error().
		Interface("panic", recovered).
		Str("stack", string(stack)).
		Msg("Panic recovered")
}

// LogDBQuery logs a database query for debugging
func LogDBQuery(query string, args []interface{}, duration time.Duration, err error) {
	event := log.Debug()

	if err != nil {
		event = log.Error().Err(err)
	}

	// Mask sensitive data in the arguments (e.g., password)
	safeArgs := make([]interface{}, len(args))
	for i, arg := range args {
		// Check if the argument might contain sensitive data
		if s, ok := arg.(string); ok {
			if strings.Contains(strings.ToLower(query), "password") ||
				strings.Contains(strings.ToLower(query), "secret") ||
				strings.Contains(strings.ToLower(query), "token") {
				safeArgs[i] = "[REDACTED]"
			} else {
				safeArgs[i] = s
			}
		} else {
			safeArgs[i] = arg
		}
	}

	event.
		Str("query", query).
		Interface("args", safeArgs).
		Dur("duration", duration).
		Msg("Database query executed")
}

// LogAuth logs authentication events
func LogAuth(event string, userID, username string, success bool, reason string) {
	logEvent := log.Info()
	if !success {
		logEvent = log.Warn()
	}

	logEvent.
		Str("event", event).
		Str("user_id", userID).
		Str("username", username).
		Bool("success", success)

	if reason != "" {
		logEvent = logEvent.Str("reason", reason)
	}

	logEvent.Msg("Authentication event")
}

// LogAPIKey logs API key events
func LogAPIKey(event, keyID, userID string) {
	log.Info().
		Str("event", event).
		Str("key_id", keyID).
		Str("user_id", userID).
		Msg("API key event")
}

// GetLogLevel returns the current global log level as a string
func GetLogLevel() string {
	return zerolog.GlobalLevel().String()
}

// SetLogLevel updates the global log level
func SetLogLevel(level string) error {
	parsedLevel, err := zerolog.ParseLevel(strings.ToLower(level))
	if err != nil {
		return fmt.Errorf("invalid log level: %s", level)
	}

	zerolog.SetGlobalLevel(parsedLevel)
	log.Info().Str("level", parsedLevel.String()).Msg("Log level changed")

	return nil
}
