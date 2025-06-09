// Package constants provides shared constant values used throughout the application.
//
// The timeouts.go file defines timeout durations for various components of the application.
// These timeouts are carefully chosen to balance responsiveness, resource utilization,
// and security. Modifying these values may impact application performance, reliability,
// and security posture.
package constants

import "time"

// Server Timeouts define duration limits for various HTTP server operations.
// These values affect how the HTTP server handles connections and requests.
const (
	// DefaultReadTimeout is the maximum duration for reading the entire request,
	// including the body. A shorter timeout reduces the risk of slow-client attacks.
	DefaultReadTimeout = 5 * time.Second

	// DefaultWriteTimeout is the maximum duration before timing out writes of the response.
	// This includes processing time, so it should be larger than ReadTimeout.
	DefaultWriteTimeout = 10 * time.Second

	// DefaultShutdownTimeout is the maximum duration to wait for the server to
	// gracefully shutdown, allowing in-flight requests to complete.
	DefaultShutdownTimeout = 30 * time.Second

	// DefaultIdleTimeout is the maximum amount of time to wait for the
	// next request when keep-alives are enabled.
	DefaultIdleTimeout = 120 * time.Second
)

// Database Timeouts define durations related to database operations and connection management.
// These values affect database performance, resource utilization, and reliability.
const (
	// DBConnectionTimeout is the maximum time to wait when establishing
	// a new database connection.
	DBConnectionTimeout = 30 * time.Second

	// DBHealthCheckTimeout is the maximum time to wait for a database
	// health check to complete.
	DBHealthCheckTimeout = 5 * time.Second

	// DBConnMaxLifetime is the maximum amount of time a connection may be reused.
	// After this time, the connection will be closed and replaced.
	DBConnMaxLifetime = 1 * time.Hour

	// DBConnMaxIdleTime is the maximum amount of time a connection may be idle.
	// Expired connections may be closed lazily before reuse.
	DBConnMaxIdleTime = 30 * time.Minute

	// DBMaintenanceInterval is how often database maintenance tasks are performed,
	// such as pruning expired sessions or cleaning up temporary data.
	DBMaintenanceInterval = 1 * time.Hour
)

// Authentication Timeouts define durations related to authentication tokens and sessions.
// These values affect security, user experience, and session management.
const (
	// DefaultJWTExpiry is the default lifetime of a JWT access token.
	// Short-lived tokens reduce the risk of token misuse if compromised.
	DefaultJWTExpiry = 15 * time.Minute

	// DefaultJWTRefreshExpiry is the default lifetime of a JWT refresh token.
	// Long-lived refresh tokens allow users to remain authenticated without frequent logins.
	DefaultJWTRefreshExpiry = 7 * 24 * time.Hour // 7 days

	// DefaultAPIKeyExpiry is the default lifetime of an API key.
	// API keys have a longer lifetime as they are typically used for service-to-service
	// authentication where frequent rotation is more disruptive.
	DefaultAPIKeyExpiry = 30 * 24 * time.Hour // 90 days

	// APIKeyDuration30Days defines a 30-day API key validity period.
	APIKeyDuration30Days = 30 * 24 * time.Hour

	// APIKeyDuration90Days defines a 90-day API key validity period.
	APIKeyDuration90Days = 90 * 24 * time.Hour

	// APIKeyDuration180Days defines a 180-day API key validity period.
	APIKeyDuration180Days = 180 * 24 * time.Hour

	// APIKeyDuration365Days defines a 365-day API key validity period.
	APIKeyDuration365Days = 365 * 24 * time.Hour

	// APIKeyDuration15Minutes defines a 15-minute API key validity period (for debugging).
	APIKeyDuration15Minutes = 15 * time.Minute

	// APIKeyDuration30Minutes defines a 30-minute API key validity period (for debugging).
	APIKeyDuration30Minutes = 30 * time.Minute
)
