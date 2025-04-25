// Package server provides HTTP server implementation for the HideMe application.
// This file defines interfaces that abstract the server's functionality for testing
// and modularity purposes. By defining these interfaces, we enable mock implementations
// for testing and facilitate a more modular and maintainable codebase.
package server

import (
	"context"
	"net/http"

	"github.com/go-chi/chi/v5"
)

// ServerTestInterface defines methods required for server testing.
// This interface abstracts the server's core functionality to facilitate
// unit testing with mock implementations. It includes methods for route setup,
// router access, server lifecycle management, and maintenance tasks.
//
// Using a different name from Server to avoid conflicts with routes_test.go
// and to clearly indicate its testing purpose.
type ServerTestInterface interface {
	// SetupRoutes configures the HTTP routes for the server
	SetupRoutes()

	// GetRouter returns the configured router for request handling
	GetRouter() chi.Router

	// Start begins listening for HTTP requests
	Start() error

	// Shutdown gracefully stops the server
	Shutdown(ctx context.Context) error

	// SetupMaintenanceTasks initializes background maintenance operations
	SetupMaintenanceTasks()
}

// ServerDBHealthChecker defines the interface for database health checks.
// This interface abstracts database connectivity testing to allow for
// dependency injection and simpler testing of health check endpoints.
type ServerDBHealthChecker interface {
	// HealthCheck verifies the database connection is working properly
	//
	// Parameters:
	//   - ctx: Context for the health check operation
	//
	// Returns:
	//   - An error if the database is unreachable or unhealthy
	HealthCheck(ctx context.Context) error

	// Close terminates the database connection
	Close()
}

// ServerRouteHandler is a simple interface for HTTP handlers.
// This interface provides a common contract for all HTTP handlers,
// enabling consistent handling and testing of route handlers.
type ServerRouteHandler interface {
	// ServeHTTP handles an HTTP request
	//
	// Parameters:
	//   - w: The HTTP response writer
	//   - r: The HTTP request
	ServeHTTP(w http.ResponseWriter, r *http.Request)
}
