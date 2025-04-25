// Package gdprlog provides GDPR-compliant logging functionalities.
//
// This file implements subject access request handling for the GDPR logging system.
// It provides functions to find, export, and delete logs related to a specific data
// subject, supporting the GDPR rights of access, portability, and erasure. These
// functions allow organizations to respond to data subject requests while maintaining
// the integrity and security of their logging system.
package gdprlog

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
)

// LogEntry represents a parsed log entry for subject access purposes.
// It contains both the structured data of the log entry and metadata about its source.
type LogEntry struct {
	// Timestamp is the time when the log entry was created
	Timestamp time.Time `json:"timestamp"`
	// Level is the log level (debug, info, warn, error, etc.)
	Level string `json:"level"`
	// Message is the log message text
	Message string `json:"message"`
	// Fields contains the structured data associated with the log entry
	Fields map[string]interface{} `json:"fields"`
	// Source indicates which log category (standard, personal, sensitive) the entry came from
	Source string `json:"source"`
	// Raw contains the original unparsed log entry text
	Raw string `json:"raw,omitempty"`
}

// SubjectIdentifiers contains different ways to identify a subject in logs.
// It provides multiple ways to match a data subject, as the subject may be
// represented differently across different parts of the system.
type SubjectIdentifiers struct {
	// UserID is the primary identifier for a user
	UserID string `json:"user_id,omitempty"`
	// Username is the user's login name
	Username string `json:"username,omitempty"`
	// Email is the user's email address
	Email string `json:"email,omitempty"`
	// IDs contains additional numeric identifiers for the user
	IDs []string `json:"ids,omitempty"`
	// Keywords contains additional search terms related to the user
	Keywords []string `json:"keywords,omitempty"`
	// IPAddress is the user's IP address
	IPAddress string `json:"ip_address,omitempty"`
}

// SubjectDataResult contains the results of a subject data search.
// It provides comprehensive information about the search process and results.
type SubjectDataResult struct {
	// SearchTime is when the search was performed
	SearchTime time.Time `json:"search_time"`
	// Subject is a human-readable identifier for the data subject
	Subject string `json:"subject"`
	// TotalEntries is the number of log entries found
	TotalEntries int `json:"total_entries"`
	// Entries contains the actual log entries found
	Entries []*LogEntry `json:"entries"`
	// SearchedFiles is the number of files examined during the search
	SearchedFiles int `json:"searched_files"`
	// FromDate is the start of the date range searched
	FromDate time.Time `json:"from_date"`
	// ToDate is the end of the date range searched
	ToDate time.Time `json:"to_date"`
}

// FindLogsForSubject searches logs for entries related to a specific data subject.
// It supports the GDPR right of access by allowing an organization to find all
// data related to a specific individual.
//
// Parameters:
//   - ctx: Context for cancellation and timeout
//   - identifiers: Various ways to identify the subject in logs
//   - fromDate: Start of the date range to search
//   - toDate: End of the date range to search
//
// Returns:
//   - *SubjectDataResult: Results of the search, including found log entries
//   - error: An error if the search fails, nil otherwise
func (gl *GDPRLogger) FindLogsForSubject(ctx context.Context, identifiers SubjectIdentifiers, fromDate, toDate time.Time) (*SubjectDataResult, error) {
	result := &SubjectDataResult{
		SearchTime: time.Now(),
		Subject:    getSubjectName(identifiers),
		FromDate:   fromDate,
		ToDate:     toDate,
		Entries:    make([]*LogEntry, 0),
	}

	// Define log directories to search
	logDirs := []struct {
		path  string
		label string
	}{
		{gl.config.PersonalLogPath, "personal"},
		{gl.config.SensitiveLogPath, "sensitive"},
		// Standard logs might contain sanitized personal data, which is still relevant
		{gl.config.StandardLogPath, "standard"},
	}

	// Search each directory
	filesSearched := 0
	for _, dir := range logDirs {
		err := filepath.Walk(dir.path, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return nil // Skip files we can't access and continue
			}

			// Skip directories
			if info.IsDir() {
				return nil
			}

			// Skip non-log files
			if !strings.HasSuffix(strings.ToLower(info.Name()), ".log") {
				return nil
			}

			// Check if file's modification time falls within our date range
			// Log files can't contain data from before they were created
			if info.ModTime().Before(fromDate) {
				return nil
			}

			// Process this log file
			fileEntries, err := gl.searchLogFile(path, dir.label, identifiers)
			if err != nil {
				log.Warn().
					Err(err).
					Str("file", path).
					Msg("Error searching log file")
				return nil // Continue with other files
			}

			// Add found entries to our result
			result.Entries = append(result.Entries, fileEntries...)
			filesSearched++

			// Check if context is done (for long searches)
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
				return nil
			}
		})

		if err != nil {
			if err == context.Canceled {
				log.Info().Msg("Log search was canceled")
				break
			}
			log.Warn().
				Err(err).
				Str("directory", dir.path).
				Msg("Error walking directory")
			// Continue with next directory
		}
	}

	// Update result stats
	result.SearchedFiles = filesSearched
	result.TotalEntries = len(result.Entries)

	// Filter by date range now that we have parsed entries
	var filteredEntries []*LogEntry
	for _, entry := range result.Entries {
		if (entry.Timestamp.After(fromDate) || entry.Timestamp.Equal(fromDate)) &&
			(entry.Timestamp.Before(toDate) || entry.Timestamp.Equal(toDate)) {
			filteredEntries = append(filteredEntries, entry)
		}
	}

	result.Entries = filteredEntries
	result.TotalEntries = len(filteredEntries)

	return result, nil
}

// searchLogFile searches a single log file for entries related to a subject.
// It performs an initial quick string search before doing more detailed parsing
// to optimize performance on large log files.
//
// Parameters:
//   - filePath: Path to the log file to search
//   - fileLabel: Category label of the log file (standard, personal, sensitive)
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - []*LogEntry: Log entries that match the subject identifiers
//   - error: An error if the search fails, nil otherwise
func (gl *GDPRLogger) searchLogFile(filePath, fileLabel string, identifiers SubjectIdentifiers) ([]*LogEntry, error) {
	var entries []*LogEntry

	// Open the file
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open file %s: %w", filePath, err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNum := 0

	// Process each line in the file
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()

		// Skip empty lines
		if len(strings.TrimSpace(line)) == 0 {
			continue
		}

		// Check if line matches any subject identifier before attempting to parse
		if !matchesAnyIdentifier(line, identifiers) {
			continue
		}

		// Parse the JSON log entry
		var rawEntry map[string]interface{}
		if err := json.Unmarshal([]byte(line), &rawEntry); err != nil {
			// Not valid JSON or not a log entry we can parse
			continue
		}

		// Now do a more detailed check with structured data
		if matchesSubjectIdentifiers(rawEntry, identifiers) {
			entry := parseLogEntry(line, rawEntry, fileLabel)
			entries = append(entries, entry)
		}
	}

	if err := scanner.Err(); err != nil {
		return entries, fmt.Errorf("error reading file %s: %w", filePath, err)
	}

	return entries, nil
}

// matchesAnyIdentifier does a quick string check to see if a line might be relevant.
// This is an optimization to avoid parsing every log line as JSON when most
// lines won't be relevant to the search.
//
// Parameters:
//   - line: The raw log line text
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - bool: true if the line contains any of the identifiers, false otherwise
func matchesAnyIdentifier(line string, identifiers SubjectIdentifiers) bool {
	// Quick check for user ID as a string
	if identifiers.UserID != "" && strings.Contains(line, identifiers.UserID) {
		return true
	}

	// Check username if available
	if identifiers.Username != "" && strings.Contains(line, identifiers.Username) {
		return true
	}

	// Check email if available
	if identifiers.Email != "" && strings.Contains(line, identifiers.Email) {
		return true
	}

	// Check for IP address
	if identifiers.IPAddress != "" && strings.Contains(line, identifiers.IPAddress) {
		return true
	}

	// Check additional IDs
	for _, id := range identifiers.IDs {
		if id != "" && strings.Contains(line, id) {
			return true
		}
	}

	// Check keywords
	for _, keyword := range identifiers.Keywords {
		if keyword != "" && strings.Contains(line, keyword) {
			return true
		}
	}

	return false
}

// matchesSubjectIdentifiers does a detailed check for subject identifiers in a parsed log entry.
// It examines the structured data of the log entry to find matches to the subject identifiers.
//
// Parameters:
//   - entry: The parsed log entry as a map
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - bool: true if the entry matches any of the identifiers, false otherwise
func matchesSubjectIdentifiers(entry map[string]interface{}, identifiers SubjectIdentifiers) bool {
	// Check user_id or user id variants
	if identifiers.UserID != "" {
		// Direct user_id match
		if userID, ok := entry["user_id"]; ok {
			if matchesValue(userID, identifiers.UserID) {
				return true
			}
		}

		// Check for user_id in fields
		if fields, ok := entry["fields"].(map[string]interface{}); ok {
			if userID, ok := fields["user_id"]; ok {
				if matchesValue(userID, identifiers.UserID) {
					return true
				}
			}
		}
	}

	// Check username
	if identifiers.Username != "" {
		// Direct username match
		if username, ok := entry["username"]; ok {
			if matchesValue(username, identifiers.Username) {
				return true
			}
		}

		// Check for username in fields
		if fields, ok := entry["fields"].(map[string]interface{}); ok {
			if username, ok := fields["username"]; ok {
				if matchesValue(username, identifiers.Username) {
					return true
				}
			}
		}
	}

	// Check email
	if identifiers.Email != "" {
		// Direct email match
		if email, ok := entry["email"]; ok {
			if matchesValue(email, identifiers.Email) {
				return true
			}
		}

		// Check for email in fields
		if fields, ok := entry["fields"].(map[string]interface{}); ok {
			if email, ok := fields["email"]; ok {
				if matchesValue(email, identifiers.Email) {
					return true
				}
			}
		}
	}

	// Check IP address
	if identifiers.IPAddress != "" {
		// Direct match
		if ip, ok := entry["remote_addr"]; ok {
			if matchesValue(ip, identifiers.IPAddress) {
				return true
			}
		}
		if ip, ok := entry["ip"]; ok {
			if matchesValue(ip, identifiers.IPAddress) {
				return true
			}
		}

		// Check in fields
		if fields, ok := entry["fields"].(map[string]interface{}); ok {
			if ip, ok := fields["remote_addr"]; ok {
				if matchesValue(ip, identifiers.IPAddress) {
					return true
				}
			}
			if ip, ok := fields["ip"]; ok {
				if matchesValue(ip, identifiers.IPAddress) {
					return true
				}
			}
		}
	}

	// Check for any additional IDs
	for _, id := range identifiers.IDs {
		if id == "" {
			continue
		}

		// Look for this ID in any field - use underscore for unused key
		for _, value := range entry {
			if matchesValue(value, id) {
				return true
			}
		}

		// Check in fields
		if fields, ok := entry["fields"].(map[string]interface{}); ok {
			for _, value := range fields {
				if matchesValue(value, id) {
					return true
				}
			}
		}
	}

	// Check for keywords in the whole entry
	for _, keyword := range identifiers.Keywords {
		if keyword == "" {
			continue
		}

		// Check message for keyword
		if msg, ok := entry["message"].(string); ok {
			if strings.Contains(strings.ToLower(msg), strings.ToLower(keyword)) {
				return true
			}
		}

		// Look for keyword in raw values
		entryJSON, err := json.Marshal(entry)
		if err == nil && strings.Contains(strings.ToLower(string(entryJSON)), strings.ToLower(keyword)) {
			return true
		}
	}

	return false
}

// matchesValue checks if a log value matches an identifier string.
// It handles direct matches and also attempts to match potentially masked or redacted values.
//
// Parameters:
//   - value: The value from the log entry, which can be of any type
//   - identifier: The identifier string to match against
//
// Returns:
//   - bool: true if the value matches the identifier, false otherwise
func matchesValue(value interface{}, identifier string) bool {
	if value == nil {
		return false
	}

	// Convert to string for consistent comparison
	valueStr := fmt.Sprintf("%v", value)

	// Check for exact match
	if valueStr == identifier {
		return true
	}

	// Check for masked/redacted values that might still contain partial identifiers
	if strings.Contains(valueStr, "[") && strings.Contains(valueStr, "]") {
		// This is likely a masked value, try to match with the unmasked identifier
		// For example, "j***e" might be "jane"
		if len(valueStr) >= 2 && len(identifier) >= 2 {
			// Check if first and last characters match
			if (valueStr[0] == identifier[0] && valueStr[len(valueStr)-1] == identifier[len(identifier)-1]) ||
				strings.Contains(valueStr, identifier[:2]) ||
				strings.Contains(valueStr, identifier[len(identifier)-2:]) {
				return true
			}
		}
	}

	return false
}

// parseLogEntry converts a raw log line and parsed JSON into a LogEntry.
// It extracts and formats the relevant fields into a structured LogEntry object.
//
// Parameters:
//   - rawLine: The raw log line text
//   - parsed: The parsed JSON data from the log line
//   - source: The source category of the log (standard, personal, sensitive)
//
// Returns:
//   - *LogEntry: A structured representation of the log entry
func parseLogEntry(rawLine string, parsed map[string]interface{}, source string) *LogEntry {
	entry := &LogEntry{
		Fields: make(map[string]interface{}),
		Source: source,
		Raw:    rawLine,
	}

	// Extract timestamp
	if ts, ok := parsed["time"].(string); ok {
		if t, err := time.Parse(time.RFC3339, ts); err == nil {
			entry.Timestamp = t
		} else {
			entry.Timestamp = time.Now() // Fallback
		}
	}

	// Extract level
	if level, ok := parsed["level"].(string); ok {
		entry.Level = level
	}

	// Extract message
	if msg, ok := parsed["message"].(string); ok {
		entry.Message = msg
	}

	// Copy all other fields
	for k, v := range parsed {
		if k != "time" && k != "level" && k != "message" {
			entry.Fields[k] = v
		}
	}

	return entry
}

// DeleteLogsForSubject removes or redacts logs containing data for a specific subject.
// This supports the GDPR right to erasure by allowing removal of a data subject's
// personal data from logs.
//
// Parameters:
//   - ctx: Context for cancellation and timeout
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - int: The number of log entries processed
//   - error: An error if the deletion fails, nil otherwise
func (gl *GDPRLogger) DeleteLogsForSubject(ctx context.Context, identifiers SubjectIdentifiers) (int, error) {
	// First, find all logs for this subject
	// Use a long time range to ensure we catch all entries
	startDate := time.Now().AddDate(-10, 0, 0) // 10 years ago
	endDate := time.Now().AddDate(1, 0, 0)     // 1 year in the future

	result, err := gl.FindLogsForSubject(ctx, identifiers, startDate, endDate)
	if err != nil {
		return 0, fmt.Errorf("failed to find logs for subject: %w", err)
	}

	if result.TotalEntries == 0 {
		return 0, nil // No entries to delete
	}

	// Group entries by file to minimize file operations
	entriesByFile := make(map[string][]*LogEntry)
	for _, entry := range result.Entries {
		if entry.Raw != "" {
			key := fmt.Sprintf("%s:%s", entry.Source, entry.Raw)
			entriesByFile[key] = append(entriesByFile[key], entry)
		}
	}

	// Now process each file
	totalProcessed := 0
	for fileKey := range entriesByFile {
		parts := strings.SplitN(fileKey, ":", 2)
		if len(parts) != 2 {
			continue
		}

		sourceType := parts[0]
		rawEntry := parts[1]

		// Determine which log directory to look in
		var logDir string
		switch sourceType {
		case "personal":
			logDir = gl.config.PersonalLogPath
		case "sensitive":
			logDir = gl.config.SensitiveLogPath
		case "standard":
			logDir = gl.config.StandardLogPath
		default:
			continue
		}

		// Find files in the directory
		files, err := filepath.Glob(filepath.Join(logDir, "*.log"))
		if err != nil {
			log.Error().
				Err(err).
				Str("dir", logDir).
				Msg("Failed to find log files")
			continue
		}

		// Process each file
		for _, file := range files {
			processed, err := gl.redactEntriesFromFile(file, rawEntry, identifiers)
			if err != nil {
				log.Error().
					Err(err).
					Str("file", file).
					Msg("Failed to redact entries")
				continue
			}
			totalProcessed += processed
		}
	}

	return totalProcessed, nil
}

// redactEntriesFromFile redacts entries from a single log file.
// It creates a temporary file with redacted entries and then replaces
// the original file, ensuring atomicity and preventing data loss.
//
// Parameters:
//   - filePath: Path to the log file to process
//   - rawEntryContent: Raw text to match against log entries
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - int: The number of log entries redacted
//   - error: An error if redaction fails, nil otherwise
func (gl *GDPRLogger) redactEntriesFromFile(filePath, rawEntryContent string, identifiers SubjectIdentifiers) (int, error) {
	// Create a temporary file
	tmpFile, err := os.CreateTemp(filepath.Dir(filePath), "redacted-*.log")
	if err != nil {
		return 0, fmt.Errorf("failed to create temp file: %w", err)
	}
	defer tmpFile.Close()

	// Open the original file
	origFile, err := os.Open(filePath)
	if err != nil {
		return 0, fmt.Errorf("failed to open file: %w", err)
	}
	defer origFile.Close()

	reader := bufio.NewScanner(origFile)
	writer := bufio.NewWriter(tmpFile)

	entriesRedacted := 0
	lineNum := 0

	// Process each line
	for reader.Scan() {
		lineNum++
		line := reader.Text()

		// Check if this line matches the raw entry content or identifiers
		if strings.Contains(line, rawEntryContent) || matchesAnyIdentifier(line, identifiers) {
			// Parse the JSON
			var entry map[string]interface{}
			if err := json.Unmarshal([]byte(line), &entry); err != nil {
				// Not valid JSON or not a log entry we can parse
				// Keep the line as is
				if _, writeErr := fmt.Fprintln(writer, line); writeErr != nil {
					return entriesRedacted, fmt.Errorf("failed to write to temp file: %w", writeErr)
				}
				continue
			}

			// Verify it matches our subject
			if matchesSubjectIdentifiers(entry, identifiers) {
				// Redact personal information
				redactedEntry := redactPersonalData(entry, identifiers)

				// Convert back to JSON
				redactedJSON, err := json.Marshal(redactedEntry)
				if err != nil {
					// If we can't marshal, keep the original line
					if _, writeErr := fmt.Fprintln(writer, line); writeErr != nil {
						return entriesRedacted, fmt.Errorf("failed to write to temp file: %w", writeErr)
					}
					continue
				}

				// Write the redacted entry
				if _, writeErr := fmt.Fprintln(writer, string(redactedJSON)); writeErr != nil {
					return entriesRedacted, fmt.Errorf("failed to write to temp file: %w", writeErr)
				}
				entriesRedacted++
			} else {
				// No match, keep the original line
				if _, writeErr := fmt.Fprintln(writer, line); writeErr != nil {
					return entriesRedacted, fmt.Errorf("failed to write to temp file: %w", writeErr)
				}
			}
		} else {
			// No match, keep the original line
			if _, writeErr := fmt.Fprintln(writer, line); writeErr != nil {
				return entriesRedacted, fmt.Errorf("failed to write to temp file: %w", writeErr)
			}
		}
	}

	if err := reader.Err(); err != nil {
		return entriesRedacted, fmt.Errorf("error reading file: %w", err)
	}

	// Flush the writer
	if err := writer.Flush(); err != nil {
		return entriesRedacted, fmt.Errorf("error writing to temp file: %w", err)
	}

	// Close both files
	if err := origFile.Close(); err != nil {
		return entriesRedacted, fmt.Errorf("error closing original file: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		return entriesRedacted, fmt.Errorf("error closing temp file: %w", err)
	}

	// Replace the original file with the redacted version
	if err := os.Rename(tmpFile.Name(), filePath); err != nil {
		return entriesRedacted, fmt.Errorf("error replacing original file: %w", err)
	}

	return entriesRedacted, nil
}

// redactPersonalData redacts personal information from a log entry.
// It replaces personal identifiers with a redaction marker while
// preserving the structure of the log entry.
//
// Parameters:
//   - entry: The log entry to redact as a map
//   - identifiers: Various ways to identify the subject in logs
//
// Returns:
//   - map[string]interface{}: The redacted log entry
func redactPersonalData(entry map[string]interface{}, identifiers SubjectIdentifiers) map[string]interface{} {
	// Make a copy of the entry
	redacted := make(map[string]interface{})
	for k, v := range entry {
		redacted[k] = v
	}

	// Fields that might contain personal data
	personalFields := []string{
		"user_id", "username", "email", "name", "address", "phone", "ip", "remote_addr",
	}

	// Redact matching fields directly in the entry
	for _, field := range personalFields {
		if v, ok := redacted[field]; ok {
			if matchesValue(v, identifiers.UserID) ||
				matchesValue(v, identifiers.Username) ||
				matchesValue(v, identifiers.Email) ||
				matchesValue(v, identifiers.IPAddress) {
				redacted[field] = "[REDACTED-GDPR]"
			}
		}
	}

	// Also check in nested fields
	if fields, ok := redacted["fields"].(map[string]interface{}); ok {
		redactedFields := make(map[string]interface{})
		for k, v := range fields {
			if contains(personalFields, k) {
				if matchesValue(v, identifiers.UserID) ||
					matchesValue(v, identifiers.Username) ||
					matchesValue(v, identifiers.Email) ||
					matchesValue(v, identifiers.IPAddress) {
					redactedFields[k] = "[REDACTED-GDPR]"
				} else {
					redactedFields[k] = v
				}
			} else {
				redactedFields[k] = v
			}
		}
		redacted["fields"] = redactedFields
	}

	return redacted
}

// contains checks if a string is in a slice.
// This is a utility function for checking if a field name is in a list of personal fields.
//
// Parameters:
//   - slice: The slice of strings to search in
//   - str: The string to search for
//
// Returns:
//   - bool: true if the string is in the slice, false otherwise
func contains(slice []string, str string) bool {
	for _, s := range slice {
		if s == str {
			return true
		}
	}
	return false
}

// ExportLogsForSubject exports all logs for a subject in a GDPR-compliant format.
// This supports the GDPR right to data portability by providing all data about
// a subject in a structured, machine-readable format.
//
// Parameters:
//   - ctx: Context for cancellation and timeout
//   - identifiers: Various ways to identify the subject in logs
//   - writer: Writer to output the exported logs to
//
// Returns:
//   - error: An error if export fails, nil otherwise
func (gl *GDPRLogger) ExportLogsForSubject(ctx context.Context, identifiers SubjectIdentifiers, writer io.Writer) error {
	// Find logs for the subject
	startDate := time.Now().AddDate(-10, 0, 0) // 10 years ago
	endDate := time.Now().AddDate(1, 0, 0)     // 1 year in the future

	result, err := gl.FindLogsForSubject(ctx, identifiers, startDate, endDate)
	if err != nil {
		return fmt.Errorf("failed to find logs for subject: %w", err)
	}

	// Write the result as JSON
	encoder := json.NewEncoder(writer)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(result); err != nil {
		return fmt.Errorf("failed to encode result: %w", err)
	}

	return nil
}

// getSubjectName returns a display name for the subject based on available identifiers.
// It chooses the most specific and user-friendly identifier available.
//
// Parameters:
//   - identifiers: Various ways to identify the subject
//
// Returns:
//   - string: A human-readable name for the subject
func getSubjectName(identifiers SubjectIdentifiers) string {
	if identifiers.Username != "" {
		return identifiers.Username
	}
	if identifiers.Email != "" {
		return identifiers.Email
	}
	if identifiers.UserID != "" {
		return fmt.Sprintf("User ID: %s", identifiers.UserID)
	}
	if identifiers.IPAddress != "" {
		return fmt.Sprintf("IP: %s", identifiers.IPAddress)
	}
	if len(identifiers.IDs) > 0 {
		return fmt.Sprintf("ID: %s", identifiers.IDs[0])
	}
	return "Unknown Subject"
}
