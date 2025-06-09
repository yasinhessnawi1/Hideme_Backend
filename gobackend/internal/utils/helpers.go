// Package utils provides utility functions and helpers for common operations
// used throughout the application. It includes string manipulation, error checking,
// data sanitization, and slice operations that simplify repeated tasks.
//
// This package follows Go's idioms for error handling and uses Go's standard
// library patterns where appropriate. Functions in this package are designed
// to be simple, self-contained, and have minimal side effects.
package utils

import (
	"fmt"
	"strings"

	"github.com/go-sql-driver/mysql"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// JoinStrings joins a slice of strings with the given separator.
// It's a convenience wrapper around strings.Join.
//
// Parameters:
//   - strs: the slice of strings to join
//   - sep: the separator to insert between elements
//
// Returns:
//   - a single string with all elements concatenated with the separator
func JoinStrings(strs []string, sep string) string {
	return strings.Join(strs, sep)
}

// FormatInt64 formats an int64 as a string.
// It's a type-safe wrapper around fmt.Sprintf.
//
// Parameters:
//   - i: the int64 value to format
//
// Returns:
//   - the string representation of the int64 value
func FormatInt64(i int64) string {
	return fmt.Sprintf("%d", i)
}

// Plural returns a string with the number and the plural form of the word if necessary.
// It handles the simple English pluralization case where adding 's' is sufficient.
//
// Parameters:
//   - count: the count to determine if singular or plural form is needed
//   - word: the base word in singular form
//
// Returns:
//   - a formatted string with the count and appropriate word form
func Plural(count int, word string) string {
	if count == 1 {
		return fmt.Sprintf("%d %s", count, word)
	}
	return fmt.Sprintf("%d %ss", count, word)
}

// IsDuplicateKeyError checks if an error is a MySQL duplicate key error.
// This is useful for handling unique constraint violations.
//
// Parameters:
//   - err: the error to check
//
// Returns:
//   - true if the error is a MySQL duplicate key error (code 1062), false otherwise
func IsDuplicateKeyError(err error) bool {
	if mysqlErr, ok := err.(*mysql.MySQLError); ok {
		// MySQL error number 1062 is "Duplicate entry"
		return mysqlErr.Number == 1062
	}
	return false
}

// TruncateString truncates a string to the given maximum length and adds ellipsis if necessary.
// This is useful for display or logging purposes where long strings need to be shortened.
//
// Parameters:
//   - s: the string to truncate
//   - maxLen: the maximum length of the resulting string (including ellipsis if added)
//
// Returns:
//   - the truncated string, with ellipsis appended if truncation occurred
func TruncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

// MaskEmail masks the user part of an email address, showing only the first and last character.
// This is useful for privacy and GDPR compliance when displaying or logging email addresses.
//
// For example: "user@example.com" becomes "u***r@example.com"
//
// Parameters:
//   - email: the email address to mask
//
// Returns:
//   - the masked email address, or the original string if it's not a valid email format
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

// SanitizeKeys removes potentially sensitive fields from a map.
// It recursively traverses through maps and slices of maps to sanitize nested structures.
// This is critical for security when logging data structures that might contain sensitive information.
//
// Parameters:
//   - data: the map to sanitize
//
// Returns:
//   - a new map with sensitive values redacted
func SanitizeKeys(data map[string]interface{}) map[string]interface{} {
	// List of keys to remove or mask
	sensitiveKeys := map[string]bool{
		constants.ColumnPasswordHash: true,
		constants.ColumnSalt:         true,
		constants.ColumnAPIKeyHash:   true,
		"password":                   true,
		"api_key":                    true,
		"token":                      true,
		"secret":                     true,
		"credit_card":                true,
		"ssn":                        true,
		"social_security":            true,
	}

	result := make(map[string]interface{})

	for k, v := range data {
		// Skip sensitive keys
		if sensitiveKeys[strings.ToLower(k)] {
			result[k] = constants.LogRedactedValue
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

// ContainsString checks if a slice of strings contains a specific string.
//
// Parameters:
//   - slice: the slice of strings to search
//   - str: the string to look for
//
// Returns:
//   - true if the string is found in the slice, false otherwise
func ContainsString(slice []string, str string) bool {
	for _, item := range slice {
		if item == str {
			return true
		}
	}
	return false
}

// RemoveString removes all occurrences of a string from a slice.
// This function creates a new slice rather than modifying the original.
//
// Parameters:
//   - slice: the original slice of strings
//   - str: the string to remove
//
// Returns:
//   - a new slice with all occurrences of str removed
func RemoveString(slice []string, str string) []string {
	var result []string
	for _, item := range slice {
		if item != str {
			result = append(result, item)
		}
	}
	return result
}
