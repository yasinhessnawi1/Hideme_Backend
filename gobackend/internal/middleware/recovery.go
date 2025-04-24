package middleware

import (
	"fmt"
	"net/http"
	"runtime/debug"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/gdprlog"
)

// Recovery is a middleware that recovers from panics and returns a 500 Internal Server Error
func Recovery() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if err := recover(); err != nil {
					// Capture the stack trace
					stack := debug.Stack()

					// Get the request ID for correlation
					requestID, _ := auth.GetRequestID(r)

					// Sanitize the stack trace for GDPR compliance
					sanitizedStack := sanitizeStackTrace(string(stack))

					// Use GDPR-compliant logging for the panic
					if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
						fields := map[string]interface{}{
							"request_id":  requestID,
							"method":      r.Method,
							"path":        r.URL.Path,
							"remote_addr": r.RemoteAddr,
							"panic":       fmt.Sprintf("%v", err),
							"stack":       sanitizedStack,
						}

						// Log as sensitive since stack traces might contain sensitive information
						gdprLogger.Error("Panic recovered in request handler", nil, fields)
					} else {
						// Fallback to standard logger if GDPR logger isn't available
						log.Error().
							Str("request_id", requestID).
							Interface("panic", err).
							Str("stack", sanitizedStack).
							Str("method", r.Method).
							Str("path", r.URL.Path).
							Str("remote_addr", r.RemoteAddr).
							Msg("Panic recovered in request handler")
					}

					// Return a 500 Internal Server Error
					utils.Error(
						w,
						http.StatusInternalServerError,
						"internal_error",
						"An unexpected error occurred while processing your request",
						nil,
					)
				}
			}()

			next.ServeHTTP(w, r)
		})
	}
}

// sanitizeStackTrace attempts to remove potentially sensitive information from stack traces
// This is a basic implementation that could be enhanced based on specific needs
func sanitizeStackTrace(stack string) string {
	// For now, return the stack as is - in a real implementation,
	// you might want to parse and filter out sensitive patterns like tokens, passwords, etc.
	return stack
}

// PanicOnError is a helper function to trigger a panic for critical errors
// This should only be used for errors that should never happen in normal operation
func PanicOnError(err error, message string) {
	if err != nil {
		// Log the error before panicking
		if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
			gdprLogger.Error("Critical error causing panic", err, map[string]interface{}{
				"message":  message,
				"category": gdprlog.SensitiveLog,
			})
		}

		panic(fmt.Sprintf("%s: %v", message, err))
	}
}

// LogAndContinueOnError logs an error but allows execution to continue
// This is useful for non-critical errors that should be logged but not cause a panic
func LogAndContinueOnError(err error, message string) {
	if err != nil {
		// Use GDPR-compliant logging
		if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
			gdprLogger.Error(message, err, nil)
		} else {
			// Fallback to standard logging
			log.Error().Err(err).Msg(message)
		}
	}
}
