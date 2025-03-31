package utils

import (
	"fmt"
	"strings"

	"github.com/go-sql-driver/mysql"
)

// JoinStrings joins a slice of strings with the given separator
func JoinStrings(strs []string, sep string) string {
	return strings.Join(strs, sep)
}

// FormatInt64 formats an int64 as a string
func FormatInt64(i int64) string {
	return fmt.Sprintf("%d", i)
}

// Plural returns a string with the number and the plural form of the word if necessary
func Plural(count int, word string) string {
	if count == 1 {
		return fmt.Sprintf("%d %s", count, word)
	}
	return fmt.Sprintf("%d %ss", count, word)
}

// IsDuplicateKeyError checks if an error is a duplicate key error
func IsDuplicateKeyError(err error) bool {
	if mysqlErr, ok := err.(*mysql.MySQLError); ok {
		// MySQL error number 1062 is "Duplicate entry"
		return mysqlErr.Number == 1062
	}
	return false
}

// IsUniqueViolation checks if an error is a unique violation for a specific constraint
func IsUniqueViolation(err error, constraintName string) bool {
	if mysqlErr, ok := err.(*mysql.MySQLError); ok {
		// Check for unique violation and specific constraint
		return mysqlErr.Number == 1062 && strings.Contains(mysqlErr.Message, constraintName)
	}
	return false
}

// IsNotNullViolation checks if an error is a not-null violation
func IsNotNullViolation(err error) bool {
	if mysqlErr, ok := err.(*mysql.MySQLError); ok {
		// MySQL error number 1048 is "Column cannot be null"
		return mysqlErr.Number == 1048
	}
	return false
}

// IsForeignKeyViolation checks if an error is a foreign key violation
func IsForeignKeyViolation(err error) bool {
	if mysqlErr, ok := err.(*mysql.MySQLError); ok {
		// MySQL error number 1452 is "Cannot add or update a child row: a foreign key constraint fails"
		return mysqlErr.Number == 1452
	}
	return false
}

// TruncateString truncates a string to the given max length and adds ellipsis if necessary
func TruncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

// MaskEmail masks the user part of an email address, showing only the first and last character
func MaskEmail(email string) string {
	parts := strings.Split(email, "@")
	if len(parts) != 2 {
		return email
	}

	user := parts[0]
	domain := parts[1]

	if len(user) <= 2 {
		return email
	}

	masked := string(user[0]) + strings.Repeat("*", len(user)-2) + string(user[len(user)-1]) + "@" + domain
	return masked
}

// SanitizeKeys removes potentially sensitive fields from a map
func SanitizeKeys(data map[string]interface{}) map[string]interface{} {
	// List of keys to remove or mask
	sensitiveKeys := map[string]bool{
		"password":        true,
		"password_hash":   true,
		"salt":            true,
		"api_key":         true,
		"api_key_hash":    true,
		"token":           true,
		"secret":          true,
		"credit_card":     true,
		"ssn":             true,
		"social_security": true,
	}

	result := make(map[string]interface{})

	for k, v := range data {
		// Skip sensitive keys
		if sensitiveKeys[strings.ToLower(k)] {
			result[k] = "[REDACTED]"
			continue
		}

		// Handle nested maps
		if nestedMap, ok := v.(map[string]interface{}); ok {
			result[k] = SanitizeKeys(nestedMap)
			continue
		}

		// Handle nested map slices
		if nestedMapSlice, ok := v.([]map[string]interface{}); ok {
			sanitizedSlice := make([]map[string]interface{}, len(nestedMapSlice))
			for i, nestedMap := range nestedMapSlice {
				sanitizedSlice[i] = SanitizeKeys(nestedMap)
			}
			result[k] = sanitizedSlice
			continue
		}

		// Pass through all other values
		result[k] = v
	}

	return result
}

// ContainsString checks if a slice of strings contains a specific string
func ContainsString(slice []string, str string) bool {
	for _, item := range slice {
		if item == str {
			return true
		}
	}
	return false
}

// RemoveString removes all occurrences of a string from a slice
func RemoveString(slice []string, str string) []string {
	var result []string
	for _, item := range slice {
		if item != str {
			result = append(result, item)
		}
	}
	return result
}

func ParseStringToInt64(s string, defaultValue int64) int64 {
	if s == "" {
		return defaultValue
	}

	var result int64
	if _, err := fmt.Sscanf(s, "%d", &result); err != nil {
		return defaultValue
	}
	return result
}

// AddJWTMethod returns an extension of the JWT method name that helps with debugging
func AddJWTMethod(method string) string {
	return fmt.Sprintf("%s (algorithm)", method)
}
