package constants

import "time"

// Server Timeouts
const (
	DefaultReadTimeout     = 5 * time.Second
	DefaultWriteTimeout    = 10 * time.Second
	DefaultShutdownTimeout = 30 * time.Second
	DefaultIdleTimeout     = 120 * time.Second
)

// Database Timeouts
const (
	DBConnectionTimeout   = 30 * time.Second
	DBQueryTimeout        = 15 * time.Second
	DBHealthCheckTimeout  = 5 * time.Second
	DBConnMaxLifetime     = 1 * time.Hour
	DBConnMaxIdleTime     = 30 * time.Minute
	DBMaintenanceInterval = 1 * time.Hour
)

// Authentication Timeouts
const (
	DefaultJWTExpiry        = 15 * time.Minute
	DefaultJWTRefreshExpiry = 7 * 24 * time.Hour  // 7 days
	DefaultAPIKeyExpiry     = 90 * 24 * time.Hour // 90 days
	APIKeyDuration30Days    = 30 * 24 * time.Hour
	APIKeyDuration90Days    = 90 * 24 * time.Hour
	APIKeyDuration180Days   = 180 * 24 * time.Hour
	APIKeyDuration365Days   = 365 * 24 * time.Hour
)

// Operation Durations
const (
	CookieMaxAge30Days = 30 * 24 * 60 * 60 // in seconds
	CACHEControlMaxAge = 300               // in seconds
)
