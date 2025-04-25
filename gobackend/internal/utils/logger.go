package utils

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/gdprlog"
)

// Global GDPR logger instance
var gdprLogger *gdprlog.GDPRLogger

// InitLogger initializes the application logger with the given configuration
func InitLogger(cfg *config.AppConfig) {
	// Set global log level
	level, err := zerolog.ParseLevel(strings.ToLower(cfg.Logging.Level))
	if err != nil {
		// Default to info level if invalid
		level = zerolog.InfoLevel
	}
	zerolog.SetGlobalLevel(level)

	// Initialize GDPR Logger first
	var gdprLogErr error
	gdprLogger, gdprLogErr = gdprlog.NewGDPRLogger(&cfg.GDPRLogging)
	if gdprLogErr != nil {
		// Fall back to standard logging if GDPR logger fails
		fmt.Fprintf(os.Stderr, "Failed to initialize GDPR logger: %v\n", gdprLogErr)
		setupStandardLogger(cfg)
	} else {
		// Set up log rotation for GDPR logs
		err = gdprLogger.SetupLogRotation()
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to set up GDPR log rotation: %v\n", err)
		}

		// Override the global logger to maintain compatibility
		log.Logger = createGDPRCompatibleLogger(cfg)
	}

	log.Info().Msg("Logger initialized")
}

// GetGDPRLogger returns the global GDPR logger instance
func GetGDPRLogger() *gdprlog.GDPRLogger {
	return gdprLogger
}

// SetGDPRLogger sets the global GDPR logger instance
func SetGDPRLogger(logger *gdprlog.GDPRLogger) {
	gdprLogger = logger
}

// setupStandardLogger configures the standard zerolog logger (fallback)
func setupStandardLogger(cfg *config.AppConfig) {
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
}

// createGDPRCompatibleLogger creates a zerolog.Logger that forwards to GDPR logger
func createGDPRCompatibleLogger(cfg *config.AppConfig) zerolog.Logger {
	return zerolog.New(gdprLogHook{}).
		With().
		Timestamp().
		Str("app", cfg.App.Name).
		Str("version", cfg.App.Version).
		Str("env", cfg.App.Environment).
		Logger()
}

// gdprLogHook is a writer that forwards logs to GDPR logger
type gdprLogHook struct{}

// Write implements io.Writer to handle log entries
func (h gdprLogHook) Write(p []byte) (n int, err error) {
	// Parse the JSON log entry
	var logEntry map[string]interface{}
	err = json.Unmarshal(p, &logEntry)
	if err != nil {
		// If we can't parse the JSON, just log the error and let logging continue
		if gdprLogger != nil {
			gdprLogger.Error("Failed to parse log entry", err, nil)
		}
		return len(p), nil // Don't return error to prevent breaking the logger
	}

	// Extract level and message
	level, _ := logEntry["level"].(string)
	message, _ := logEntry["message"].(string)
	delete(logEntry, "level")
	delete(logEntry, "message")

	// Extract time if present
	if _, ok := logEntry["time"].(string); ok {
		delete(logEntry, "time")
	}

	// Forward to appropriate GDPR logger method based on level
	switch level {
	case "debug":
		gdprLogger.Debug(message, logEntry)
	case "info":
		gdprLogger.Info(message, logEntry)
	case "warn":
		gdprLogger.Warn(message, logEntry)
	case "error":
		var logErr error
		if errMsg, ok := logEntry["error"].(string); ok {
			logErr = errors.New(errMsg)
			delete(logEntry, "error")
		}
		gdprLogger.Error(message, logErr, logEntry)
	case "fatal":
		gdprLogger.Fatal(message, logEntry)
	}

	return len(p), nil
}

// RequestLogger creates a logger with request-specific context
func RequestLogger(requestID, userID, method, path string) zerolog.Logger {
	logger := log.With().
		Str(constants.RequestIDContextKey, requestID).
		Str("method", method).
		Str("path", path)

	if userID != "" {
		logger = logger.Str(constants.UserIDContextKey, userID)
	}

	return logger.Logger()
}

// LogHTTPRequest logs an HTTP request with request details
func LogHTTPRequest(requestID, method, path, remoteAddr, userAgent string, statusCode int, latency time.Duration) {
	// Create fields for GDPR logger
	fields := map[string]interface{}{
		constants.RequestIDContextKey: requestID,
		"method":                      method,
		"path":                        path,
		"remote_addr":                 remoteAddr,
		"user_agent":                  userAgent,
		"status":                      statusCode,
		"latency":                     latency,
	}

	// Only log some paths at debug level to reduce noise
	if path == constants.HealthPath || path == "/metrics" {
		if zerolog.GlobalLevel() != zerolog.DebugLevel {
			return // Skip logging entirely for high-volume endpoints in non-debug mode
		}
		if gdprLogger != nil {
			gdprLogger.Debug("HTTP Request", fields)
			return
		}
	}

	// Determine log level and log either with GDPR logger or zerolog
	if gdprLogger != nil {
		// Elevate error responses to warning/error level
		if statusCode >= 400 && statusCode < 500 {
			gdprLogger.Warn("HTTP Request", fields)
		} else if statusCode >= 500 {
			gdprLogger.Error("HTTP Request", nil, fields)
		} else if strings.HasPrefix(path, constants.APIBasePath) {
			// Log API requests at info level
			gdprLogger.Info("HTTP Request", fields)
		} else {
			gdprLogger.Debug("HTTP Request", fields)
		}
	} else {
		// Original zerolog implementation
		event := log.Debug()

		// Elevate error responses to warning/error level
		if statusCode >= 400 && statusCode < 500 {
			event = log.Warn()
		} else if statusCode >= 500 {
			event = log.Error()
		} else if strings.HasPrefix(path, constants.APIBasePath) {
			// Log API requests at info level
			event = log.Info()
		}

		// Include request details
		event.
			Str(constants.RequestIDContextKey, requestID).
			Str("method", method).
			Str("path", path).
			Str("remote_addr", remoteAddr).
			Str("user_agent", userAgent).
			Int("status", statusCode).
			Dur("latency", latency).
			Msg("HTTP Request")
	}
}

// LogError logs an error with context information
func LogError(err error, context map[string]interface{}) {
	if gdprLogger != nil {
		gdprLogger.Error("Error occurred", err, context)
	} else {
		// Fallback to zerolog
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
}

// LogPanic logs a recovered panic value
func LogPanic(recovered interface{}, stack []byte) {
	if gdprLogger != nil {
		fields := map[string]interface{}{
			"panic": recovered,
			"stack": string(stack),
		}
		gdprLogger.Error("Panic recovered", nil, fields)
	} else {
		log.Error().
			Interface("panic", recovered).
			Str("stack", string(stack)).
			Msg("Panic recovered")
	}
}

// LogDBQuery logs a database query for debugging
func LogDBQuery(query string, args []interface{}, duration time.Duration, err error) {
	// Mask sensitive data in the arguments (e.g., password)
	safeArgs := make([]interface{}, len(args))
	for i, arg := range args {
		// Check if the argument might contain sensitive data
		if s, ok := arg.(string); ok {
			if strings.Contains(strings.ToLower(query), constants.ColumnPasswordHash) ||
				strings.Contains(strings.ToLower(query), "secret") ||
				strings.Contains(strings.ToLower(query), "token") {
				safeArgs[i] = constants.LogRedactedValue
			} else {
				safeArgs[i] = s
			}
		} else {
			safeArgs[i] = arg
		}
	}

	// Create fields for GDPR logger
	fields := map[string]interface{}{
		"query":    query,
		"args":     safeArgs,
		"duration": duration,
	}

	if gdprLogger != nil {
		if err != nil {
			gdprLogger.Error("Database query executed", err, fields)
		} else {
			gdprLogger.Debug("Database query executed", fields)
		}
	} else {
		event := log.Debug()

		if err != nil {
			event = log.Error().Err(err)
		}

		event.
			Str("query", query).
			Interface("args", safeArgs).
			Dur("duration", duration).
			Msg("Database query executed")
	}
}

// LogAuth logs authentication events
func LogAuth(event string, userID, username string, success bool, reason string) {
	fields := map[string]interface{}{
		"event":                      event,
		constants.UserIDContextKey:   userID,
		constants.UsernameContextKey: username,
		"success":                    success,
	}

	if reason != "" {
		fields["reason"] = reason
	}

	if gdprLogger != nil {
		if success {
			gdprLogger.Info(constants.LogCategoryAuth, fields)
		} else {
			gdprLogger.Warn(constants.LogCategoryAuth, fields)
		}
	} else {
		logEvent := log.Info()
		if !success {
			logEvent = log.Warn()
		}

		logEvent.
			Str("event", event).
			Str(constants.UserIDContextKey, userID).
			Str(constants.UsernameContextKey, username).
			Bool("success", success)

		if reason != "" {
			logEvent = logEvent.Str("reason", reason)
		}

		logEvent.Msg(constants.LogEventLogin)
	}
}

// LogAPIKey logs API key events
func LogAPIKey(event, keyID, userID string) {
	fields := map[string]interface{}{
		"event":                    event,
		constants.ParamKeyID:       keyID,
		constants.UserIDContextKey: userID,
	}

	if gdprLogger != nil {
		gdprLogger.Info(constants.LogEventAPIKey, fields)
	} else {
		log.Info().
			Str("event", event).
			Str(constants.ParamKeyID, keyID).
			Str(constants.UserIDContextKey, userID).
			Msg(constants.LogEventAPIKey)
	}
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
