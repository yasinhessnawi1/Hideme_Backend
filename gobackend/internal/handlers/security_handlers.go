// Package handlers provides HTTP request handlers.
package handlers

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SecurityServiceInterface defines the interface for security service operations
// This is used for testing purposes
type SecurityServiceInterface interface {
	ListBans(ctx context.Context) ([]*models.IPBan, error)
	BanIP(ctx context.Context, ipAddress string, reason string, duration time.Duration, bannedBy string) (*models.IPBan, error)
	UnbanIP(ctx context.Context, banID int64) error
	IsBanned(ipAddress string) bool
	IsRateLimited(ipAddress string, category string) bool
}

// SecurityHandler manages security-related API endpoints.
type SecurityHandler struct {
	securityService *service.SecurityService
}

// NewSecurityHandler creates a new SecurityHandler with the specified services.
//
// Parameters:
//   - securityService: Service for security operations
//
// Returns:
//   - A properly initialized SecurityHandler
func NewSecurityHandler(securityService *service.SecurityService) *SecurityHandler {
	return &SecurityHandler{
		securityService: securityService,
	}
}

// ListBannedIPs returns all currently banned IP addresses.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/admin/security/bans
//
// Requires:
//   - Authentication: Admin role
//
// Responses:
//   - 200 OK: List of banned IPs
//   - 401 Unauthorized: User not authenticated
//   - 403 Forbidden: User not authorized (not admin)
//   - 500 Internal Server Error: Server-side error
//
// @Summary List banned IPs
// @Description Returns a list of all currently banned IP addresses
// @Tags Admin/Security
// @Produce json
// @Security BearerAuth
// @Success 200 {object} utils.Response{data=[]models.IPBan} "List of banned IPs"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 403 {object} utils.Response{error=string} "User not authorized"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /admin/security/bans [get]
func (h *SecurityHandler) ListBannedIPs(w http.ResponseWriter, r *http.Request) {
	// Get list of banned IPs
	bans, err := h.securityService.ListBans(r.Context())
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the bans
	utils.JSON(w, http.StatusOK, bans)
}

// BanIP adds an IP address to the ban list.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/admin/security/bans
//
// Requires:
//   - Authentication: Admin role
//
// Request Body:
//   - JSON object with "ip_address", "reason", and optional "duration" fields
//
// Responses:
//   - 201 Created: IP successfully banned
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 403 Forbidden: User not authorized (not admin)
//   - 500 Internal Server Error: Server-side error
//
// @Summary Ban an IP address
// @Description Adds an IP address to the ban list
// @Tags Admin/Security
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param ban body object true "Ban request with ip_address, reason, and optional duration fields"
// @Success 201 {object} utils.Response{data=models.IPBan} "IP successfully banned"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 403 {object} utils.Response{error=string} "User not authorized"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /admin/security/bans [post]
func (h *SecurityHandler) BanIP(w http.ResponseWriter, r *http.Request) {
	// Get the admin username for tracking who created the ban
	username, _ := auth.GetUsername(r)

	// Decode and validate the request body
	var req struct {
		IPAddress string        `json:"ip_address" validate:"required,ip|cidr"`
		Reason    string        `json:"reason" validate:"required"`
		Duration  time.Duration `json:"duration"` // In seconds, 0 for permanent
	}

	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Ban the IP
	ban, err := h.securityService.BanIP(r.Context(), req.IPAddress, req.Reason, req.Duration, username)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the created ban
	utils.JSON(w, http.StatusCreated, ban)
}

// UnbanIP removes an IP address from the ban list.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/admin/security/bans/{id}
//
// URL Parameters:
//   - id: The ID of the ban to remove
//
// Requires:
//   - Authentication: Admin role
//
// Responses:
//   - 200 OK: IP successfully unbanned
//   - 400 Bad Request: Invalid ban ID
//   - 401 Unauthorized: User not authenticated
//   - 403 Forbidden: User not authorized (not admin)
//   - 404 Not Found: Ban not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Unban an IP address
// @Description Removes an IP address from the ban list
// @Tags Admin/Security
// @Produce json
// @Security BearerAuth
// @Param id path int true "Ban ID"
// @Success 200 {object} utils.Response{data=map[string]string} "IP successfully unbanned"
// @Failure 400 {object} utils.Response{error=string} "Invalid ban ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 403 {object} utils.Response{error=string} "User not authorized"
// @Failure 404 {object} utils.Response{error=string} "Ban not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /admin/security/bans/{id} [delete]
func (h *SecurityHandler) UnbanIP(w http.ResponseWriter, r *http.Request) {
	// Get the ban ID from the URL
	banIDStr := chi.URLParam(r, "id")
	banID, err := strconv.ParseInt(banIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid ban ID", nil)
		return
	}

	// Unban the IP
	if err := h.securityService.UnbanIP(r.Context(), banID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, http.StatusOK, map[string]string{
		"message": "IP address successfully unbanned",
	})
}
