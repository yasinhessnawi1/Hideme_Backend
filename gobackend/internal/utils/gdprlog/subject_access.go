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

// LogEntry represents a parsed log entry for subject access purposes
type LogEntry struct {
	Timestamp time.Time              `json:"timestamp"`
	Level     string                 `json:"level"`
	Message   string                 `json:"message"`
	Fields    map[string]interface{} `json:"fields"`
	Source    string                 `json:"source"`
	Raw       string                 `json:"raw,omitempty"`
}

// SubjectIdentifiers contains different ways to identify a subject in logs
type SubjectIdentifiers struct {
	UserID    string   `json:"user_id,omitempty"`
	Username  string   `json:"username,omitempty"`
	Email     string   `json:"email,omitempty"`
	IDs       []string `json:"ids,omitempty"`      // Additional numeric IDs
	Keywords  []string `json:"keywords,omitempty"` // Additional search terms
	IPAddress string   `json:"ip_address,omitempty"`
}

// SubjectDataResult contains the results of a subject data search
type SubjectDataResult struct {
	SearchTime    time.Time   `json:"search_time"`
	Subject       string      `json:"subject"`
	TotalEntries  int         `json:"total_entries"`
	Entries       []*LogEntry `json:"entries"`
	SearchedFiles int         `json:"searched_files"`
	FromDate      time.Time   `json:"from_date"`
	ToDate        time.Time   `json:"to_date"`
}

// FindLogsForSubject searches logs for entries related to a specific data subject
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

// searchLogFile searches a single log file for entries related to a subject
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

// matchesAnyIdentifier does a quick string check to see if a line might be relevant
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

// matchesSubjectIdentifiers does a detailed check for subject identifiers in a parsed log entry
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

// matchesValue checks if a log value matches an identifier string
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

// parseLogEntry converts a raw log line and parsed JSON into a LogEntry
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

// DeleteLogsForSubject removes or redacts logs containing data for a specific subject
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

// redactEntriesFromFile redacts entries from a single log file
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

// redactPersonalData redacts personal information from a log entry
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

// contains checks if a string is in a slice
func contains(slice []string, str string) bool {
	for _, s := range slice {
		if s == str {
			return true
		}
	}
	return false
}

// ExportLogsForSubject exports all logs for a subject in a GDPR-compliant format
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

// getSubjectName returns a display name for the subject based on available identifiers
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
