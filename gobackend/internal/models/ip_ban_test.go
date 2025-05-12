package models

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestNewIPBan(t *testing.T) {
	t.Run("Create with all fields", func(t *testing.T) {
		// Arrange
		ipAddress := "192.168.1.1"
		reason := "Suspicious activity"
		expireTime := time.Now().Add(24 * time.Hour)
		creator := "admin"

		// Act
		ban := NewIPBan(ipAddress, reason, &expireTime, creator)

		// Assert
		assert.Equal(t, ipAddress, ban.IPAddress)
		assert.Equal(t, reason, ban.Reason)
		assert.Equal(t, expireTime.Truncate(time.Second), ban.ExpiresAt.Truncate(time.Second))
		assert.Equal(t, creator, ban.CreatedBy)
		assert.NotZero(t, ban.CreatedAt)
		assert.Zero(t, ban.ID) // ID should be zero until saved
	})

	t.Run("Create permanent ban", func(t *testing.T) {
		// Arrange
		ipAddress := "10.0.0.1"
		reason := "Persistent threat"
		creator := "system"

		// Act - no expiry time for permanent ban
		ban := NewIPBan(ipAddress, reason, nil, creator)

		// Assert
		assert.Equal(t, ipAddress, ban.IPAddress)
		assert.Equal(t, reason, ban.Reason)
		assert.Nil(t, ban.ExpiresAt)
		assert.Equal(t, creator, ban.CreatedBy)
	})

	t.Run("Create with CIDR notation", func(t *testing.T) {
		// Arrange
		ipAddress := "192.168.0.0/24"
		reason := "Network ban"
		creator := "admin"

		// Act
		ban := NewIPBan(ipAddress, reason, nil, creator)

		// Assert
		assert.Equal(t, ipAddress, ban.IPAddress)
	})

	t.Run("Create with empty reason", func(t *testing.T) {
		// Arrange
		ipAddress := "192.168.1.1"
		reason := ""
		creator := "admin"

		// Act
		ban := NewIPBan(ipAddress, reason, nil, creator)

		// Assert
		assert.Equal(t, ipAddress, ban.IPAddress)
		assert.Empty(t, ban.Reason)
	})

	t.Run("Create with empty creator", func(t *testing.T) {
		// Arrange
		ipAddress := "192.168.1.1"
		reason := "Some reason"
		creator := ""

		// Act
		ban := NewIPBan(ipAddress, reason, nil, creator)

		// Assert
		assert.Equal(t, ipAddress, ban.IPAddress)
		assert.Empty(t, ban.CreatedBy)
	})
}

func TestIPBan_IsExpired(t *testing.T) {
	t.Run("Permanent ban never expires", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.1.1", "Persistent threat", nil, "admin")

		// Act
		isExpired := ban.IsExpired()

		// Assert
		assert.False(t, isExpired)
	})

	t.Run("Future expiry is not expired", func(t *testing.T) {
		// Arrange
		futureTime := time.Now().Add(1 * time.Hour)
		ban := NewIPBan("192.168.1.1", "Temporary ban", &futureTime, "admin")

		// Act
		isExpired := ban.IsExpired()

		// Assert
		assert.False(t, isExpired)
	})

	t.Run("Past expiry is expired", func(t *testing.T) {
		// Arrange
		pastTime := time.Now().Add(-1 * time.Hour)
		ban := NewIPBan("192.168.1.1", "Expired ban", &pastTime, "admin")

		// Act
		isExpired := ban.IsExpired()

		// Assert
		assert.True(t, isExpired)
	})

	t.Run("Exact current time is considered expired", func(t *testing.T) {
		// Arrange
		now := time.Now()
		ban := NewIPBan("192.168.1.1", "Just expired", &now, "admin")

		// Let a small amount of time pass to ensure we're after the expiry
		time.Sleep(1 * time.Millisecond)

		// Act
		isExpired := ban.IsExpired()

		// Assert
		assert.True(t, isExpired)
	})
}

func TestIPBan_MatchesIP(t *testing.T) {
	t.Run("Exact IP match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.1.1", "Test ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("192.168.1.1")

		// Assert
		assert.True(t, matches)
	})

	t.Run("Different IP doesn't match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.1.1", "Test ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("192.168.1.2")

		// Assert
		assert.False(t, matches)
	})

	t.Run("IP in CIDR range matches", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.0.0/24", "Network ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("192.168.0.100")

		// Assert
		assert.True(t, matches)
	})

	t.Run("IP outside CIDR range doesn't match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.0.0/24", "Network ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("192.169.0.1")

		// Assert
		assert.False(t, matches)
	})

	t.Run("Invalid IP in ban doesn't cause panic", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("invalid-ip", "Bad IP", nil, "admin")

		// Act
		matches := ban.MatchesIP("192.168.1.1")

		// Assert
		assert.False(t, matches)
	})

	t.Run("Invalid IP to check doesn't cause panic", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("192.168.1.1", "Test ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("invalid-ip")

		// Assert
		assert.False(t, matches)
	})

	t.Run("IPv6 address exact match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("2001:db8::1", "IPv6 ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("2001:db8::1")

		// Assert
		assert.True(t, matches)
	})

	t.Run("IPv6 CIDR match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("2001:db8::/32", "IPv6 network ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("2001:db8:1234::1")

		// Assert
		assert.True(t, matches)
	})

	t.Run("IPv6 outside CIDR doesn't match", func(t *testing.T) {
		// Arrange
		ban := NewIPBan("2001:db8::/32", "IPv6 network ban", nil, "admin")

		// Act
		matches := ban.MatchesIP("2001:db9::1")

		// Assert
		assert.False(t, matches)
	})
}
