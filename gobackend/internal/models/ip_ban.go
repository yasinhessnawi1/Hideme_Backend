// Package models provides data structures representing entities in the application.
package models

import (
	"net"
	"time"
)

// IPBan represents a banned IP address or CIDR range.
type IPBan struct {
	// ID is the unique identifier for the ban record
	ID int64 `json:"id" db:"ban_id"`

	// IPAddress is the banned IP address or CIDR range
	IPAddress string `json:"ip_address" db:"ip_address"`

	// Reason provides context for why the IP was banned
	Reason string `json:"reason" db:"reason"`

	// ExpiresAt defines when the ban expires (nil for permanent bans)
	ExpiresAt *time.Time `json:"expires_at,omitempty" db:"expires_at"`

	// CreatedAt is when the ban was created
	CreatedAt time.Time `json:"created_at" db:"created_at"`

	// CreatedBy is the user or system that created the ban
	CreatedBy string `json:"created_by" db:"created_by"`
}

// NewIPBan creates a new IP ban record.
//
// Parameters:
//   - ipAddress: The IP address or CIDR range to ban
//   - reason: The reason for the ban
//   - expiresAt: The expiration time for the ban (nil for permanent)
//   - createdBy: Who or what created the ban
//
// Returns:
//   - A new IPBan record
func NewIPBan(ipAddress, reason string, expiresAt *time.Time, createdBy string) *IPBan {
	return &IPBan{
		IPAddress: ipAddress,
		Reason:    reason,
		ExpiresAt: expiresAt,
		CreatedAt: time.Now(),
		CreatedBy: createdBy,
	}
}

// IsExpired checks if the ban has expired.
//
// Returns:
//   - true if the ban has expired, false otherwise
func (b *IPBan) IsExpired() bool {
	return b.ExpiresAt != nil && time.Now().After(*b.ExpiresAt)
}

// MatchesIP checks if the provided IP matches this ban record.
// This supports both direct IP matches and CIDR range matches.
//
// Parameters:
//   - ip: The IP address to check
//
// Returns:
//   - true if the IP matches the ban, false otherwise
func (b *IPBan) MatchesIP(ip string) bool {
	// Check for exact match
	if b.IPAddress == ip {
		return true
	}

	// Check if this is a CIDR notation
	_, ipNet, err := net.ParseCIDR(b.IPAddress)
	if err != nil {
		return false
	}

	// Parse the input IP
	parsedIP := net.ParseIP(ip)
	if parsedIP == nil {
		return false
	}

	// Check if IP is in the banned CIDR range
	return ipNet.Contains(parsedIP)
}
