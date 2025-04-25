// Package gdprlog provides GDPR-compliant logging functionalities.
//
// This package implements mechanisms for detecting, categorizing, and sanitizing
// personal and sensitive data in logs to meet GDPR compliance requirements.
// It includes pattern matching for common sensitive data, field detection, and
// sanitization utilities to create logs that respect data protection regulations.
package gdprlog

import (
	"fmt"
	"regexp"
	"strings"
)

// Regular expressions for detecting various types of personal and sensitive data
var (
	// emailPattern matches valid email address formats for detection and validation.
	emailPattern = regexp.MustCompile(`(?i)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`)

	// creditCardPattern matches common credit card number formats, accounting for
	// potential spaces or dashes between number groups.
	creditCardPattern = regexp.MustCompile(`(?i)(?:\d[ -]*?){13,16}`)

	// passwordPattern detects password-related field names and content.
	passwordPattern = regexp.MustCompile(`(?i)passw(or)?d|pwd`)

	// authPattern detects authentication-related field names and content,
	// such as tokens, API keys, and credentials.
	authPattern = regexp.MustCompile(`(?i)auth|token|secret|key|credential|jwt|bearer`)

	// personalDataIndicators contains patterns that identify common personal data fields.
	// These are used to detect personally identifiable information in logs.
	personalDataIndicators = []*regexp.Regexp{
		regexp.MustCompile(`(?i)\bname\b`),
		regexp.MustCompile(`(?i)\buser(name)?\b`),
		regexp.MustCompile(`(?i)\bemail\b`),
		regexp.MustCompile(`(?i)\bphone\b`),
		regexp.MustCompile(`(?i)\baddress\b`),
		regexp.MustCompile(`(?i)\bzip\b|\bpostal\b`),
		regexp.MustCompile(`(?i)\bcity\b`),
		regexp.MustCompile(`(?i)\bcountry\b`),
		regexp.MustCompile(`(?i)\bstate\b`),
		regexp.MustCompile(`(?i)\bip[_\s-]?addr`),
		regexp.MustCompile(`(?i)\buser[_\s-]?id\b`),
		regexp.MustCompile(`(?i)\bsession[_\s-]?id\b`),
	}

	// sensitiveDataIndicators contains patterns that identify sensitive data beyond
	// passwords and authentication tokens, such as financial and health information.
	sensitiveDataIndicators = []*regexp.Regexp{
		regexp.MustCompile(`(?i)\bcredit[_\s-]?card\b`),
		regexp.MustCompile(`(?i)\bcard[_\s-]?number\b`),
		regexp.MustCompile(`(?i)\bcvv\b`),
		regexp.MustCompile(`(?i)\bssn\b`),
		regexp.MustCompile(`(?i)\bsocial[_\s-]?security\b`),
		regexp.MustCompile(`(?i)\btax[_\s-]?id\b`),
		regexp.MustCompile(`(?i)\bpassport\b`),
		regexp.MustCompile(`(?i)\bdob\b`),
		regexp.MustCompile(`(?i)\bdate[_\s-]?of[_\s-]?birth\b`),
		regexp.MustCompile(`(?i)\bhealth\b`),
		regexp.MustCompile(`(?i)\bmedical\b`),
		regexp.MustCompile(`(?i)\binsurance\b`),
		regexp.MustCompile(`(?i)\bcertificate\b`),
		regexp.MustCompile(`(?i)\blicense\b`),
	}
)

// SensitiveFieldNames is a list of field names that commonly contain sensitive information.
// This list is used to identify fields that should be redacted or specially handled in logs.
var SensitiveFieldNames = []string{
	"password", "token", "key", "secret", "auth_token", "access_token",
	"refresh_token", "jwt", "api_key", "credit_card", "card_number",
	"cvv", "ssn", "social_security", "hash", "salt",
}

// PersonalFieldNames is a list of field names that commonly contain personal information.
// These fields identify individuals but are generally less sensitive than those in SensitiveFieldNames.
var PersonalFieldNames = []string{
	"user_id", "username", "email", "ip_address", "ip", "address",
	"phone", "name", "full_name", "first_name", "last_name", "zip_code",
	"postal_code", "city", "state", "country", "age", "gender", "dob",
	"date_of_birth", "session_id", "customer_id", "client_id",
}

// IsSensitiveField checks if a field and its value appears to contain sensitive data.
// It examines both the field name and its value against known patterns and lists of sensitive data.
//
// Parameters:
//   - fieldName: The name of the field to check
//   - value: The value of the field, which can be of any type
//
// Returns:
//   - bool: true if the field appears to contain sensitive data, false otherwise
func IsSensitiveField(fieldName string, value interface{}) bool {
	// Check field name against known sensitive fields
	lowerName := strings.ToLower(fieldName)
	for _, name := range SensitiveFieldNames {
		if strings.Contains(lowerName, name) {
			return true
		}
	}

	// Check for sensitive patterns in field name
	if passwordPattern.MatchString(lowerName) || authPattern.MatchString(lowerName) {
		return true
	}

	// Check string values for sensitive patterns
	if strValue, ok := value.(string); ok {
		// Skip very short strings or empty strings
		if len(strValue) < 3 {
			return false
		}

		// Credit card check with Luhn validation to reduce false positives
		if creditCardPattern.MatchString(strValue) {
			cleaned := strings.ReplaceAll(strings.ReplaceAll(strValue, " ", ""), "-", "")
			if len(cleaned) >= 13 && len(cleaned) <= 19 && couldBeCreditCard(cleaned) {
				return true
			}
		}

		// Check sensitive data indicators in the actual value
		for _, pattern := range sensitiveDataIndicators {
			if pattern.MatchString(strValue) {
				return true
			}
		}
	}

	return false
}

// IsPersonalField checks if a field and its value appears to contain personal data.
// It examines both the field name and its value against known patterns and lists of personal data.
//
// Parameters:
//   - fieldName: The name of the field to check
//   - value: The value of the field, which can be of any type
//
// Returns:
//   - bool: true if the field appears to contain personal data, false otherwise
func IsPersonalField(fieldName string, value interface{}) bool {
	// Check field name against known personal fields
	lowerName := strings.ToLower(fieldName)
	for _, name := range PersonalFieldNames {
		if strings.Contains(lowerName, name) {
			return true
		}
	}

	// Check for personal data patterns in field name
	for _, pattern := range personalDataIndicators {
		if pattern.MatchString(lowerName) {
			return true
		}
	}

	// For string values, check if it's an email
	if strValue, ok := value.(string); ok {
		if IsEmailField("", strValue) {
			return true
		}
	}

	return false
}

// IsEmailField checks if a field name or value appears to be an email address.
// It checks both the field name for "email" and the value against email regex patterns.
//
// Parameters:
//   - fieldName: The name of the field to check
//   - value: The value of the field, which can be of any type
//
// Returns:
//   - bool: true if the field appears to be an email, false otherwise
func IsEmailField(fieldName string, value interface{}) bool {
	// Check if field name contains "email"
	if strings.Contains(strings.ToLower(fieldName), "email") {
		return true
	}

	// Check if value is an email
	if strValue, ok := value.(string); ok {
		return emailPattern.MatchString(strValue)
	}

	return false
}

// couldBeCreditCard performs a basic validation check to see if a string could be a credit card number.
// It implements the Luhn algorithm to reduce false positives when detecting credit card numbers.
//
// Parameters:
//   - number: A string containing only digits to be validated
//
// Returns:
//   - bool: true if the number passes the Luhn check and could be a valid credit card, false otherwise
func couldBeCreditCard(number string) bool {
	// Basic Luhn algorithm check (used by credit cards)
	sum := 0
	alternate := false

	// Process from right to left
	for i := len(number) - 1; i >= 0; i-- {
		if number[i] < '0' || number[i] > '9' {
			// Not a digit
			return false
		}

		n := int(number[i] - '0')

		if alternate {
			n *= 2
			if n > 9 {
				n -= 9
			}
		}

		sum += n
		alternate = !alternate
	}

	// Valid CC numbers pass this check
	return sum%10 == 0
}

// ContainsPersonalData checks a string for personal data indicators.
// This is useful for analyzing arbitrary text fields or messages for potential personal data.
//
// Parameters:
//   - s: The string to check for personal data
//
// Returns:
//   - bool: true if the string appears to contain personal data, false otherwise
func ContainsPersonalData(s string) bool {
	// Skip very short strings
	if len(s) < 5 {
		return false
	}

	// Check for email patterns
	if emailPattern.MatchString(s) {
		return true
	}

	// Check for other personal data indicators
	for _, pattern := range personalDataIndicators {
		if pattern.MatchString(s) {
			return true
		}
	}

	return false
}

// ContainsSensitiveData checks a string for sensitive data indicators.
// This is useful for analyzing arbitrary text fields or messages for potential sensitive data.
//
// Parameters:
//   - s: The string to check for sensitive data
//
// Returns:
//   - bool: true if the string appears to contain sensitive data, false otherwise
func ContainsSensitiveData(s string) bool {
	// Skip very short strings
	if len(s) < 5 {
		return false
	}

	// Check for password and auth indicators
	if passwordPattern.MatchString(s) || authPattern.MatchString(s) {
		return true
	}

	// Check for credit card patterns with Luhn validation
	if creditCardPattern.MatchString(s) {
		cleaned := strings.ReplaceAll(strings.ReplaceAll(s, " ", ""), "-", "")
		if len(cleaned) >= 13 && len(cleaned) <= 19 && couldBeCreditCard(cleaned) {
			return true
		}
	}

	// Check for other sensitive data indicators
	for _, pattern := range sensitiveDataIndicators {
		if pattern.MatchString(s) {
			return true
		}
	}

	return false
}

// ToSafeString converts a value to a string safely for logging purposes.
// It handles nil values and provides consistent string representation.
//
// Parameters:
//   - value: The value to convert to a string, which can be of any type or nil
//
// Returns:
//   - string: A string representation of the value that is safe for logging
func ToSafeString(value interface{}) string {
	if value == nil {
		return "nil"
	}

	return fmt.Sprintf("%v", value)
}
