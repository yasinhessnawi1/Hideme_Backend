// Package middleware provides HTTP middleware components.
package middleware

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// RateLimit is middleware that limits the rate of requests from clients.
// It uses the SecurityService to check if a client has exceeded their rate limit.
//
// Parameters:
//   - securityService: The security service that implements rate limiting
//   - category: The endpoint category to apply limits for (e.g., "auth", "api")
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func RateLimit(securityService *service.SecurityService, category string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get the client IP address, handling proxies
			clientIP := getClientIP(r)

			// Skip rate limiting for health checks, static assets, etc.
			if isExemptedPath(r.URL.Path) {
				next.ServeHTTP(w, r)
				return
			}

			// Check if client is rate limited
			if securityService.IsRateLimited(clientIP, category) {
				log.Warn().
					Str("client_ip", clientIP).
					Str("path", r.URL.Path).
					Str("method", r.Method).
					Str("category", category).
					Msg("Rate limit exceeded")

				// Return 429 Too Many Requests
				w.Header().Set("Retry-After", "60")
				utils.Error(w, http.StatusTooManyRequests, "too_many_requests", "Rate limit exceeded. Please try again later.", nil)
				return
			}

			// Request is allowed, continue to next handler
			next.ServeHTTP(w, r)
		})
	}
}

// IPBanCheck is middleware that blocks requests from banned IP addresses.
// It uses the SecurityService to check if an IP is banned.
//
// Parameters:
//   - securityService: The security service that manages IP bans
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func IPBanCheck(securityService *service.SecurityService) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get the client IP address, handling proxies
			clientIP := getClientIP(r)

			// Skip ban check for exempted paths
			if isExemptedPath(r.URL.Path) {
				next.ServeHTTP(w, r)
				return
			}

			// Check if IP is banned
			if securityService.IsBanned(clientIP) {
				log.Warn().
					Str("client_ip", clientIP).
					Str("path", r.URL.Path).
					Str("method", r.Method).
					Msg("Request from banned IP address")

				// Return 403 Forbidden
				utils.Forbidden(w, "Access denied")
				return
			}

			// IP not banned, continue to next handler
			next.ServeHTTP(w, r)
		})
	}
}

// AutoBan is middleware that automatically bans IPs that show malicious behavior.
// It monitors for repeated suspicious activities and bans offenders.
//
// Parameters:
//   - securityService: The security service that manages IP bans
//   - threshold: Number of suspicious activities before banning
//   - window: Time window to count suspicious activities
//   - banDuration: How long to ban the IP (0 for permanent)
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func AutoBan(securityService *service.SecurityService, threshold int, window, banDuration time.Duration) func(http.Handler) http.Handler {
	// Track suspicious activities per IP
	type activityRecord struct {
		count     int
		firstSeen time.Time
		lastSeen  time.Time
	}

	activities := make(map[string]*activityRecord)
	var activityMutex = &sync.RWMutex{}

	// Cleanup old records periodically
	go func() {
		ticker := time.NewTicker(window / 2)
		defer ticker.Stop()

		for range ticker.C {
			now := time.Now()
			activityMutex.Lock()
			for ip, record := range activities {
				if now.Sub(record.lastSeen) > window {
					delete(activities, ip)
				}
			}
			activityMutex.Unlock()
		}
	}()

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Function to record suspicious activity
			recordSuspicious := func(reason string) {
				clientIP := getClientIP(r)
				now := time.Now()

				activityMutex.Lock()
				defer activityMutex.Unlock()

				record, exists := activities[clientIP]
				if !exists {
					record = &activityRecord{
						count:     0,
						firstSeen: now,
						lastSeen:  now,
					}
					activities[clientIP] = record
				}

				// Update the record
				record.count++
				record.lastSeen = now

				// Check if we should ban this IP
				if record.count >= threshold && now.Sub(record.firstSeen) <= window {
					// Create context for ban operation
					ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
					defer cancel()

					banReason := fmt.Sprintf("Automatic ban: %s (%d violations in %s)",
						reason, record.count, window)

					// Ban the IP
					_, err := securityService.BanIP(ctx, clientIP, banReason, banDuration, "system")
					if err != nil {
						log.Error().Err(err).
							Str("client_ip", clientIP).
							Str("reason", reason).
							Msg("Failed to auto-ban IP")
					} else {
						log.Warn().
							Str("client_ip", clientIP).
							Str("reason", reason).
							Int("violations", record.count).
							Dur("window", window).
							Dur("ban_duration", banDuration).
							Msg("IP automatically banned")

						// Return forbidden for this request too
						utils.Forbidden(w, "Access denied due to suspicious activity")
					}

					// Clear the record after banning
					delete(activities, clientIP)
					return
				}

				// Continue with the request
				next.ServeHTTP(w, r)
			}

			// Check for suspicious patterns in the request
			if isSuspiciousRequest(r) {
				recordSuspicious("Suspicious request pattern")
				return
			}

			// Non-suspicious request, continue to next handler
			next.ServeHTTP(w, r)
		})
	}
}

// getClientIP extracts the client IP address from the request,
// taking into account common proxy headers.
func getClientIP(r *http.Request) string {
	// Check for X-Forwarded-For header
	xForwardedFor := r.Header.Get("X-Forwarded-For")
	if xForwardedFor != "" {
		// Use the leftmost IP in the list (client IP)
		ips := strings.Split(xForwardedFor, ",")
		ip := strings.TrimSpace(ips[0])
		return ip
	}

	// Check for X-Real-IP header
	xRealIP := r.Header.Get("X-Real-IP")
	if xRealIP != "" {
		return xRealIP
	}

	// Fall back to RemoteAddr
	ip, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		// If there's no port in the address, use it as is
		return r.RemoteAddr
	}
	return ip
}

// isExemptedPath returns true if the path should be exempted from
// rate limiting and IP banning (e.g., health checks, static assets).
func isExemptedPath(path string) bool {
	exemptPrefixes := []string{
		"/health",
		"/version",
		"/static/",
		"/public/",
		"/favicon.ico",
	}

	for _, prefix := range exemptPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}

	return false
}

// isSuspiciousRequest checks for patterns that might indicate malicious activity.
// This includes SQL injection attempts, path traversal, etc.
func isSuspiciousRequest(r *http.Request) bool {
	// Check path for suspicious patterns
	path := r.URL.Path
	suspiciousPathPatterns := []string{
		"../",
		"/..",
		"/.git",
		"/wp-admin",
		"/wp-login",
		"/phpmyadmin",
		"/admin.php",
	}

	for _, pattern := range suspiciousPathPatterns {
		if strings.Contains(path, pattern) {
			return true
		}
	}

	// Check query string for suspicious patterns
	query := r.URL.RawQuery
	suspiciousQueryPatterns := []string{
		"exec(",
		"eval(",
		"SELECT",
		"UNION",
		"INSERT",
		"DELETE",
		"UPDATE",
		"DROP",
		"1=1",
		"script",
		"alert(",
		"onload=",
		"onerror=",
	}

	for _, pattern := range suspiciousQueryPatterns {
		if strings.Contains(strings.ToUpper(query), strings.ToUpper(pattern)) {
			return true
		}
	}

	// More advanced checks could be added here

	return false
}
