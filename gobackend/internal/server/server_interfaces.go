package server

import (
	"context"
	"net/http"

	"github.com/go-chi/chi/v5"
)

// ServerTestInterface defines methods required for server testing
// Using a different name to avoid conflicts with routes_test.go
type ServerTestInterface interface {
	SetupRoutes()
	GetRouter() chi.Router
	Start() error
	Shutdown(ctx context.Context) error
	SetupMaintenanceTasks()
}

// ServerDBHealthChecker defines the interface for database health checks
type ServerDBHealthChecker interface {
	HealthCheck(ctx context.Context) error
	Close()
}

// ServerRouteHandler is a simple interface for HTTP handlers
type ServerRouteHandler interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
}
