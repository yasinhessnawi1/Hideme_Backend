// Package service provides business logic implementations.
package service

import (
	"context"
	"net"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/ratelimit"
)

// SecurityService handles security-related operations like rate limiting and IP banning.
type SecurityService struct {
	ipBanRepo        repository.IPBanRepository
	rateLimiterStore *ratelimit.Store
	banCache         map[string]bool
	cidrs            []*net.IPNet
	banMutex         sync.RWMutex
	refreshInterval  time.Duration
}

// NewSecurityService creates a new SecurityService.
//
// Parameters:
//   - ipBanRepo: Repository for IP ban storage
//   - refreshInterval: How often to refresh the ban cache from the database
//
// Returns:
//   - A configured SecurityService
func NewSecurityService(ipBanRepo repository.IPBanRepository, refreshInterval time.Duration) *SecurityService {
	// Create default rate limiter store with 100 requests/sec burst of 30
	limiterStore := ratelimit.NewStore(ratelimit.Rate{
		RequestsPerSecond: 100,
		Burst:             50,
	}, 10*time.Minute)

	// Configure different limits for different endpoint categories
	// More strict limits for authentication endpoints to prevent brute force
	limiterStore.SetRate("auth", ratelimit.Rate{
		RequestsPerSecond: 30,
		Burst:             50,
	})

	// More generous limits for API endpoints
	limiterStore.SetRate("api", ratelimit.Rate{
		RequestsPerSecond: 80,
		Burst:             50,
	})

	service := &SecurityService{
		ipBanRepo:        ipBanRepo,
		rateLimiterStore: limiterStore,
		banCache:         make(map[string]bool),
		cidrs:            make([]*net.IPNet, 0),
		refreshInterval:  refreshInterval,
	}

	// Initialize ban cache
	go service.refreshBanCache()
	go service.startRefreshTimer()

	return service
}

// IsRateLimited checks if a client has exceeded their rate limit.
//
// Parameters:
//   - clientID: Identifier for the client (typically IP address)
//   - category: The endpoint category ("auth", "api", etc.)
//
// Returns:
//   - true if the client is rate limited, false otherwise
func (s *SecurityService) IsRateLimited(clientID, category string) bool {
	limiter := s.rateLimiterStore.GetLimiter(clientID, category)
	return !limiter.Allow()
}

// IsBanned checks if an IP address is banned.
//
// Parameters:
//   - ip: The IP address to check
//
// Returns:
//   - true if the IP is banned, false otherwise
func (s *SecurityService) IsBanned(ip string) bool {
	// First check the direct ban cache (faster)
	s.banMutex.RLock()
	banned, exists := s.banCache[ip]
	s.banMutex.RUnlock()

	if exists && banned {
		return true
	}

	// Then check CIDR ranges if needed
	parsedIP := net.ParseIP(ip)
	if parsedIP != nil {
		s.banMutex.RLock()
		defer s.banMutex.RUnlock()

		for _, cidr := range s.cidrs {
			if cidr.Contains(parsedIP) {
				return true
			}
		}
	}

	return false
}

// BanIP adds an IP address to the ban list.
//
// Parameters:
//   - ctx: Context for the operation
//   - ip: The IP address or CIDR range to ban
//   - reason: The reason for the ban
//   - duration: How long the ban should last (0 for permanent)
//   - bannedBy: Who or what imposed the ban
//
// Returns:
//   - The created ban record
//   - Error if the operation fails
func (s *SecurityService) BanIP(ctx context.Context, ip, reason string, duration time.Duration, bannedBy string) (*models.IPBan, error) {
	var expiresAt *time.Time

	if duration > 0 {
		expiry := time.Now().Add(duration)
		expiresAt = &expiry
	}

	ban := models.NewIPBan(ip, reason, expiresAt, bannedBy)

	// Save to database
	ban, err := s.ipBanRepo.Create(ctx, ban)
	if err != nil {
		return nil, err
	}

	// Update cache
	s.addToCache(ban)

	return ban, nil
}

// UnbanIP removes an IP address from the ban list.
//
// Parameters:
//   - ctx: Context for the operation
//   - id: The ID of the ban to remove
//
// Returns:
//   - Error if the operation fails
func (s *SecurityService) UnbanIP(ctx context.Context, id int64) error {
	// First get the ban details so we can update the cache
	bans, err := s.ipBanRepo.GetAll(ctx)
	if err != nil {
		return err
	}

	var ipToRemove string
	for _, ban := range bans {
		if ban.ID == id {
			ipToRemove = ban.IPAddress
			break
		}
	}

	// Delete from database
	if err := s.ipBanRepo.Delete(ctx, id); err != nil {
		return err
	}

	// Update cache if we found the IP
	if ipToRemove != "" {
		s.banMutex.Lock()
		delete(s.banCache, ipToRemove)
		// Update CIDR cache too
		var newCIDRs []*net.IPNet
		for _, cidr := range s.cidrs {
			_, network, err := net.ParseCIDR(ipToRemove)
			if err != nil || network.String() != cidr.String() {
				newCIDRs = append(newCIDRs, cidr)
			}
		}
		s.cidrs = newCIDRs
		s.banMutex.Unlock()
	}

	// Full refresh to ensure consistency
	go s.refreshBanCache()

	return nil
}

// ListBans returns all active IP bans.
//
// Parameters:
//   - ctx: Context for the operation
//
// Returns:
//   - A slice of all active IP bans
//   - Error if the operation fails
func (s *SecurityService) ListBans(ctx context.Context) ([]*models.IPBan, error) {
	return s.ipBanRepo.GetAll(ctx)
}

// CleanupExpiredBans removes expired bans from the database.
//
// Parameters:
//   - ctx: Context for the operation
//
// Returns:
//   - The number of bans removed
//   - Error if the operation fails
func (s *SecurityService) CleanupExpiredBans(ctx context.Context) (int64, error) {
	count, err := s.ipBanRepo.DeleteExpired(ctx)
	if err != nil {
		return 0, err
	}

	// Refresh the ban cache if any bans were removed
	if count > 0 {
		go s.refreshBanCache()
	}

	return count, nil
}

// refreshBanCache updates the in-memory cache of banned IPs from the database.
// This is called periodically and after ban list changes.
func (s *SecurityService) refreshBanCache() {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	bans, err := s.ipBanRepo.GetAll(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to refresh IP ban cache")
		return
	}

	newCache := make(map[string]bool)
	newCIDRs := make([]*net.IPNet, 0)

	for _, ban := range bans {
		// Skip expired bans
		if ban.IsExpired() {
			continue
		}

		// Handle CIDR notation
		if _, network, err := net.ParseCIDR(ban.IPAddress); err == nil {
			newCIDRs = append(newCIDRs, network)
		} else {
			// Regular IP address
			newCache[ban.IPAddress] = true
		}
	}

	// Update the cache atomically
	s.banMutex.Lock()
	s.banCache = newCache
	s.cidrs = newCIDRs
	s.banMutex.Unlock()

	log.Debug().
		Int("direct_bans", len(newCache)).
		Int("cidr_bans", len(newCIDRs)).
		Msg("Refreshed IP ban cache")
}

// addToCache adds a ban to the in-memory cache.
func (s *SecurityService) addToCache(ban *models.IPBan) {
	// Skip if already expired
	if ban.IsExpired() {
		return
	}

	// Handle CIDR notation
	if _, network, err := net.ParseCIDR(ban.IPAddress); err == nil {
		s.banMutex.Lock()
		s.cidrs = append(s.cidrs, network)
		s.banMutex.Unlock()
	} else {
		// Regular IP address
		s.banMutex.Lock()
		s.banCache[ban.IPAddress] = true
		s.banMutex.Unlock()
	}
}

// startRefreshTimer periodically refreshes the ban cache.
func (s *SecurityService) startRefreshTimer() {
	ticker := time.NewTicker(s.refreshInterval)
	defer ticker.Stop()

	for range ticker.C {
		s.refreshBanCache()
	}
}
