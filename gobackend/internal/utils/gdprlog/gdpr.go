// Package gdprlog provides GDPR-compliant logging functionalities.
//
// This package implements a GDPR-compliant logging system that categorizes logs based on
// their data content, routes them to appropriate storage locations with proper permissions,
// and provides utilities for data subject access requests. The system ensures logs containing
// personal or sensitive data are handled according to data protection regulations.
//
// The logging system wraps the zerolog package, extending it with GDPR-specific features
// such as log categorization, sanitization, and retention policies. This enables applications
// to maintain comprehensive logging while ensuring compliance with data protection requirements.
package gdprlog

import (
	"context"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// LogCategory represents the GDPR classification of a log.
// Logs are categorized based on the types of data they contain, with different
// handling requirements for each category.
type LogCategory int

const (
	// StandardLog contains no personal data and has minimal restrictions.
	StandardLog LogCategory = iota
	// PersonalLog contains personal data (like usernames, IDs) and requires protection.
	PersonalLog
	// SensitiveLog contains sensitive personal data (passwords, auth tokens) and requires
	// the highest level of protection.
	SensitiveLog
)

// GDPRLogger wraps zerolog loggers with GDPR compliance features.
// It maintains separate loggers for different categories of data and provides
// methods to detect, sanitize, and appropriately log data based on its sensitivity.
type GDPRLogger struct {
	standardLogger  zerolog.Logger
	personalLogger  zerolog.Logger
	sensitiveLogger zerolog.Logger
	config          *config.GDPRLoggingSettings
}

// NewGDPRLogger creates a new GDPR-compliant logger.
// It sets up appropriate log directories with proper permissions and initializes
// the different category loggers.
//
// Parameters:
//   - cfg: Configuration settings for the GDPR logging system
//
// Returns:
//   - *GDPRLogger: A configured GDPR-compliant logger
//   - error: An error if logger creation fails, nil otherwise
func NewGDPRLogger(cfg *config.GDPRLoggingSettings) (*GDPRLogger, error) {
	// Ensure log directories exist
	for _, dir := range []string{
		cfg.StandardLogPath,
		cfg.PersonalLogPath,
		cfg.SensitiveLogPath,
	} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("failed to create log directory %s: %w", dir, err)
		}
	}

	// Create log writers with appropriate permissions
	// Standard logger - both console and file
	standardWriter, err := createLogWriter(filepath.Join(cfg.StandardLogPath, "standard.log"), 0644)
	if err != nil {
		return nil, err
	}

	// Personal logger - file only with restricted permissions
	personalWriter, err := createLogWriter(filepath.Join(cfg.PersonalLogPath, "personal.log"), 0600)
	if err != nil {
		return nil, err
	}

	// Sensitive logger - file only with restricted permissions
	sensitiveWriter, err := createLogWriter(filepath.Join(cfg.SensitiveLogPath, "sensitive.log"), 0600)
	if err != nil {
		return nil, err
	}

	// Create zerolog loggers
	consoleWriter := zerolog.ConsoleWriter{
		Out:        os.Stdout,
		TimeFormat: time.RFC3339,
		NoColor:    os.Getenv("NO_COLOR") != "",
	}

	// Standard logger gets console output in development
	var standardOutput io.Writer
	if os.Getenv("APP_ENV") != "production" {
		standardOutput = zerolog.MultiLevelWriter(consoleWriter, standardWriter)
	} else {
		standardOutput = standardWriter
	}

	return &GDPRLogger{
		standardLogger:  zerolog.New(standardOutput).With().Timestamp().Logger(),
		personalLogger:  zerolog.New(personalWriter).With().Timestamp().Logger(),
		sensitiveLogger: zerolog.New(sensitiveWriter).With().Timestamp().Logger(),
		config:          cfg,
	}, nil
}

// createLogWriter creates a file writer for logs with proper permissions.
// It ensures log files are created with appropriate access restrictions based on the
// sensitivity of the data they will contain.
//
// Parameters:
//   - path: The file path where the log will be written
//   - perm: File permissions to be set on the log file
//
// Returns:
//   - io.Writer: A writer for the log file
//   - error: An error if writer creation fails, nil otherwise
func createLogWriter(path string, perm os.FileMode) (io.Writer, error) {
	return os.OpenFile(
		path,
		os.O_CREATE|os.O_WRONLY|os.O_APPEND,
		perm,
	)
}

// DetermineLogCategory analyzes log data to determine its GDPR category.
// It examines the fields in a log entry to categorize it as standard, personal, or sensitive.
//
// Parameters:
//   - fields: Map of key-value pairs that make up the log fields
//
// Returns:
//   - LogCategory: The determined category (StandardLog, PersonalLog, or SensitiveLog)
func (gl *GDPRLogger) DetermineLogCategory(fields map[string]interface{}) LogCategory {
	// Check for sensitive data first
	for key, value := range fields {
		if IsSensitiveField(key, value) {
			return SensitiveLog
		}
	}

	// Then check for personal data
	for key, value := range fields {
		if IsPersonalField(key, value) {
			return PersonalLog
		}
	}

	// Default to standard log if no personal/sensitive data detected
	return StandardLog
}

// SanitizeLogFields removes or masks sensitive data based on configuration.
// It applies different levels of sanitization based on the configuration setting,
// with higher levels providing greater anonymization of personal and sensitive data.
//
// Parameters:
//   - fields: Map of key-value pairs that make up the log fields
//
// Returns:
//   - map[string]interface{}: A new map with sanitized values
func (gl *GDPRLogger) SanitizeLogFields(fields map[string]interface{}) map[string]interface{} {
	sanitizationLevel := strings.ToLower(gl.config.LogSanitizationLevel)
	if sanitizationLevel == "none" {
		return fields
	}

	// Make a copy to avoid modifying the original
	sanitizedFields := make(map[string]interface{})
	for k, v := range fields {
		sanitizedFields[k] = v
	}

	// Always sanitize sensitive fields regardless of level
	for k, v := range sanitizedFields {
		if IsSensitiveField(k, v) {
			sanitizedFields[k] = "[REDACTED]"
		}
	}

	// Handle personal data based on sanitization level
	if sanitizationLevel == "low" || sanitizationLevel == "medium" || sanitizationLevel == "high" {
		for k, v := range sanitizedFields {
			if IsPersonalField(k, v) {
				// Different handling based on sanitization level
				switch sanitizationLevel {
				case "low":
					// Minimal sanitization - only mask certain values like email
					if IsEmailField(k, v) {
						sanitizedFields[k] = MaskEmail(fmt.Sprintf("%v", v))
					}
				case "medium":
					// Standard sanitization - mask most personal data
					sanitizedFields[k] = MaskPersonalData(k, v)
				case "high":
					// Maximum sanitization - completely redact personal data
					sanitizedFields[k] = "[PERSONAL_DATA]"
				}
			}
		}
	}

	return sanitizedFields
}

// MaskPersonalData applies appropriate masking based on the field type and name.
// It uses different masking strategies based on the data type and field name
// to preserve useful information while protecting personal data.
//
// Parameters:
//   - fieldName: The name of the field being masked
//   - value: The value to mask, which can be of various types
//
// Returns:
//   - interface{}: The masked value, with type preserved where possible
func MaskPersonalData(fieldName string, value interface{}) interface{} {
	// Always completely mask user_id field regardless of type
	if strings.ToLower(fieldName) == "user_id" {
		return "***"
	}

	// Handle different data types
	switch v := value.(type) {
	case string:
		if IsEmailField(fieldName, value) {
			return MaskEmail(v)
		} else if len(v) > 2 {
			// Show first and last character, mask the rest
			return string(v[0]) + strings.Repeat("*", len(v)-2) + string(v[len(v)-1])
		}
		return "**"

	case int64:
		if strings.Contains(strings.ToLower(fieldName), "id") {
			// Always mask IDs with fixed pattern to avoid leaking information
			return "***"
		}
		// For non-ID numbers, show order of magnitude only
		return fmt.Sprintf("~%d", int64(math.Pow10(int(math.Log10(float64(v))))))

	case int:
		if strings.Contains(strings.ToLower(fieldName), "id") {
			// Always mask IDs with fixed pattern
			return "***"
		}
		// For non-ID numbers, show order of magnitude only
		if v > 0 {
			return fmt.Sprintf("~%d", int(math.Pow10(int(math.Log10(float64(v))))))
		}
		return 0

	case float64:
		if strings.Contains(strings.ToLower(fieldName), "id") {
			// Always mask IDs completely
			return "***"
		}
		// For other float values, show only approximate value
		return fmt.Sprintf("~%.1f", v)

	case float32:
		if strings.Contains(strings.ToLower(fieldName), "id") {
			return "***"
		}
		return fmt.Sprintf("~%.1f", v)

	case bool:
		// Boolean values are generally not sensitive
		return v

	case time.Time:
		// For timestamps, show only the date part
		return v.Format("2006-01-02")
	}

	// Default handling for other types - avoid leaking type information
	return "***"
}

// MaskEmail masks an email address, showing only the first 2 and last 2 characters of the username.
// This preserves some identifiability for debugging while protecting the full email address.
//
// Parameters:
//   - email: The email address to mask
//
// Returns:
//   - string: The masked email address
func MaskEmail(email string) string {
	parts := strings.Split(email, "@")
	if len(parts) != 2 {
		return "***@***"
	}

	username := parts[0]
	domain := parts[1]

	if len(username) <= 4 {
		// For short usernames, show only first character
		return username[0:1] + "***@" + domain
	}

	// Show first 2 and last 2 characters of username
	return username[0:2] + strings.Repeat("*", len(username)-4) + username[len(username)-2:] + "@" + domain
}

// Log creates a log event with GDPR compliance.
// It determines the appropriate log category, routes the log to the correct logger,
// and applies sanitization to ensure sensitive data is properly protected.
//
// Parameters:
//   - level: The zerolog level for the log (debug, info, warn, etc.)
//   - msg: The log message
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Log(level zerolog.Level, msg string, fields map[string]interface{}) {
	// Skip if below global log level
	if level < zerolog.GlobalLevel() {
		return
	}

	// Determine log category
	category := gl.DetermineLogCategory(fields)

	// Select logger based on category and sanitize as needed
	switch category {
	case SensitiveLog:
		// Store full info in sensitive log
		event := gl.sensitiveLogger.WithLevel(level)
		for k, v := range fields {
			event = addField(event, k, v)
		}
		event.Msg(msg)

		// Log sanitized version to standard log
		sanitizedFields := gl.SanitizeLogFields(fields)
		standardEvent := gl.standardLogger.WithLevel(level)
		for k, v := range sanitizedFields {
			standardEvent = addField(standardEvent, k, v)
		}
		standardEvent.Msg(msg + " [Sensitive data redacted]")

	case PersonalLog:
		// Store in personal log
		event := gl.personalLogger.WithLevel(level)
		for k, v := range fields {
			event = addField(event, k, v)
		}
		event.Msg(msg)

		// Log sanitized version to standard log
		sanitizedFields := gl.SanitizeLogFields(fields)
		standardEvent := gl.standardLogger.WithLevel(level)
		for k, v := range sanitizedFields {
			standardEvent = addField(standardEvent, k, v)
		}
		standardEvent.Msg(msg)

	default:
		// Standard log - everything goes to standard logger
		event := gl.standardLogger.WithLevel(level)
		for k, v := range fields {
			event = addField(event, k, v)
		}
		event.Msg(msg)
	}
}

// addField adds a field to a zerolog event with the appropriate type.
// It ensures fields are added with their correct type to maintain proper serialization.
//
// Parameters:
//   - event: The zerolog event to add the field to
//   - key: The field name
//   - value: The field value, which can be of various types
//
// Returns:
//   - *zerolog.Event: The updated zerolog event with the field added
func addField(event *zerolog.Event, key string, value interface{}) *zerolog.Event {
	switch v := value.(type) {
	case string:
		return event.Str(key, v)
	case int:
		return event.Int(key, v)
	case int64:
		return event.Int64(key, v)
	case float64:
		return event.Float64(key, v)
	case bool:
		return event.Bool(key, v)
	case time.Time:
		return event.Time(key, v)
	case time.Duration:
		return event.Dur(key, v)
	case []string:
		return event.Strs(key, v)
	case error:
		return event.AnErr(key, v)
	default:
		return event.Interface(key, v)
	}
}

// Debug logs at debug level with GDPR compliance.
//
// Parameters:
//   - msg: The log message
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Debug(msg string, fields map[string]interface{}) {
	gl.Log(zerolog.DebugLevel, msg, fields)
}

// Info logs at info level with GDPR compliance.
//
// Parameters:
//   - msg: The log message
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Info(msg string, fields map[string]interface{}) {
	gl.Log(zerolog.InfoLevel, msg, fields)
}

// Warn logs at warn level with GDPR compliance.
//
// Parameters:
//   - msg: The log message
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Warn(msg string, fields map[string]interface{}) {
	gl.Log(zerolog.WarnLevel, msg, fields)
}

// Error logs at error level with GDPR compliance.
// It automatically adds the error to the log fields if provided.
//
// Parameters:
//   - msg: The log message
//   - err: The error that occurred, can be nil
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Error(msg string, err error, fields map[string]interface{}) {
	if fields == nil {
		fields = make(map[string]interface{})
	}

	// Add error to fields if provided
	if err != nil {
		fields["error"] = err.Error()
	}

	gl.Log(zerolog.ErrorLevel, msg, fields)
}

// Fatal logs at fatal level with GDPR compliance and then exits.
// This function does not return as it calls os.Exit(1) after logging.
//
// Parameters:
//   - msg: The log message
//   - fields: Map of key-value pairs that make up the log fields
func (gl *GDPRLogger) Fatal(msg string, fields map[string]interface{}) {
	gl.Log(zerolog.FatalLevel, msg, fields)
	os.Exit(1)
}

// WithContext returns a new GDPRLogger with context values added to the logging context.
// This is useful for carrying request-specific information through the logging chain.
//
// Parameters:
//   - ctx: The context containing values to add to the logging context
//
// Returns:
//   - *GDPRLogger: A new logger with context values added
func (gl *GDPRLogger) WithContext(ctx context.Context) *GDPRLogger {
	// Extract values from context that might be useful for logging
	contextFields := make(map[string]interface{})

	// Example: extract request ID if present
	if requestID, ok := ctx.Value("request_id").(string); ok {
		contextFields["request_id"] = requestID
	}

	// Create loggers with context fields
	newLogger := &GDPRLogger{
		standardLogger:  gl.standardLogger.With().Fields(contextFields).Logger(),
		personalLogger:  gl.personalLogger.With().Fields(contextFields).Logger(),
		sensitiveLogger: gl.sensitiveLogger.With().Fields(contextFields).Logger(),
		config:          gl.config,
	}

	return newLogger
}
