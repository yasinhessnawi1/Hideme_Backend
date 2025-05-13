package middleware_test

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/middleware"
)

func TestRecovery(t *testing.T) {
	tests := []struct {
		name           string
		handler        http.Handler
		expectedStatus int
		expectedBody   string
	}{
		{
			name: "No panic occurs",
			handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
				if _, err := w.Write([]byte("Success")); err != nil {
					t.Fatalf("failed to write response: %v", err)
				}
			}),
			expectedStatus: http.StatusOK,
			expectedBody:   "Success",
		},
		{
			name: "Panic with error",
			handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				panic(errors.New("test error"))
			}),
			expectedStatus: http.StatusInternalServerError,
			expectedBody:   `{"success":false,"error":{"code":"internal_error","message":"An internal server error occurred"}}`, // Updated expected message
		},
		{
			name: "Panic with string",
			handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				panic("test panic")
			}),
			expectedStatus: http.StatusInternalServerError,
			expectedBody:   `{"success":false,"error":{"code":"internal_error","message":"An internal server error occurred"}}`, // Updated expected message
		},
	}

	// Set up logger to capture logs
	var logBuf bytes.Buffer
	log.Logger = zerolog.New(&logBuf)

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Clear log buffer
			logBuf.Reset()

			// Create the recovery middleware
			recoveryMiddleware := middleware.Recovery()(tt.handler)

			// Create a test request
			req, err := http.NewRequest("GET", "/test", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Add request ID to context
			ctx := context.WithValue(req.Context(), auth.RequestIDContextKey, "test-request-id")
			req = req.WithContext(ctx)

			// Create response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			recoveryMiddleware.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check response body
			if body := rr.Body.String(); body != tt.expectedBody {
				t.Errorf("Handler returned unexpected body: got %v want %v", body, tt.expectedBody)
			}

			// Check logs if panic was expected
			if tt.name != "No panic occurs" {
				logs := logBuf.String()
				if !strings.Contains(logs, "Panic recovered in request handler") {
					t.Errorf("Expected panic log message not found in logs: %s", logs)
				}
				if !strings.Contains(logs, "request_id") || !strings.Contains(logs, "test-request-id") {
					t.Errorf("Request ID not present in logs: %s", logs)
				}
			}
		})
	}
}

func TestPanicOnError(t *testing.T) {
	tests := []struct {
		name          string
		err           error
		message       string
		shouldPanic   bool
		expectedPanic string
	}{
		{
			name:        "No error",
			err:         nil,
			message:     "This should not panic",
			shouldPanic: false,
		},
		{
			name:          "With error",
			err:           errors.New("test error"),
			message:       "Test panic message",
			shouldPanic:   true,
			expectedPanic: "Test panic message: test error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			defer func() {
				r := recover()
				if tt.shouldPanic {
					if r == nil {
						t.Errorf("Expected panic but none occurred")
					} else if r != tt.expectedPanic {
						t.Errorf("Panic message = %v, want %v", r, tt.expectedPanic)
					}
				} else if r != nil {
					t.Errorf("Unexpected panic: %v", r)
				}
			}()

			middleware.PanicOnError(tt.err, tt.message)
		})
	}
}

func TestLogAndContinueOnError(t *testing.T) {
	tests := []struct {
		name      string
		err       error
		message   string
		expectLog bool
	}{
		{
			name:      "No error",
			err:       nil,
			message:   "This should not log",
			expectLog: false,
		},
		{
			name:      "With error",
			err:       errors.New("test error"),
			message:   "Test log message",
			expectLog: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Set up logger to capture logs
			var logBuf bytes.Buffer
			originalLogger := log.Logger
			log.Logger = zerolog.New(&logBuf)
			defer func() {
				log.Logger = originalLogger
			}()

			middleware.LogAndContinueOnError(tt.err, tt.message)

			logs := logBuf.String()
			if tt.expectLog {
				if !strings.Contains(logs, tt.message) {
					t.Errorf("Expected log message not found in logs: %s", logs)
				}
				if !strings.Contains(logs, tt.err.Error()) {
					t.Errorf("Expected error not found in logs: %s", logs)
				}
			} else {
				if logs != "" {
					t.Errorf("Unexpected log output: %s", logs)
				}
			}
		})
	}
}
