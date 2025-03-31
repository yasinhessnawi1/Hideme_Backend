package middleware

import (
	"fmt"
	"net/http"
	"runtime/debug"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
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

					// Log the panic
					log.Error().
						Str("request_id", requestID).
						Interface("panic", err).
						Str("stack", string(stack)).
						Str("method", r.Method).
						Str("path", r.URL.Path).
						Str("remote_addr", r.RemoteAddr).
						Msg("Panic recovered in request handler")

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

// PanicOnError is a helper function to trigger a panic for critical errors
// This should only be used for errors that should never happen in normal operation
func PanicOnError(err error, message string) {
	if err != nil {
		panic(fmt.Sprintf("%s: %v", message, err))
	}
}

// LogAndContinueOnError logs an error but allows execution to continue
// This is useful for non-critical errors that should be logged but not cause a panic
func LogAndContinueOnError(err error, message string) {
	if err != nil {
		log.Error().Err(err).Msg(message)
	}
}
