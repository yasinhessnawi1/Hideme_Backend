// Package gdprlog provides GDPR-compliant logging functionalities.
//
// This file implements log rotation and retention policies for the GDPR logging system.
// It ensures logs are properly rotated, old logs are deleted according to retention
// policies, and different categories of logs (standard, personal, sensitive) are managed
// with appropriate retention periods in compliance with data minimization principles.
package gdprlog

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// LogRetentionConfig defines retention settings for different log types.
// Each log category has its own retention period in days, reflecting the
// different requirements for storing data of varying sensitivity levels.
type LogRetentionConfig struct {
	// StandardLogRetentionDays is the number of days to retain standard logs.
	StandardLogRetentionDays int
	// PersonalDataRetentionDays is the number of days to retain logs containing personal data.
	PersonalDataRetentionDays int
	// SensitiveDataRetentionDays is the number of days to retain logs containing sensitive data.
	SensitiveDataRetentionDays int
}

// SetupLogRotation configures log rotation for different log categories.
// It starts a background goroutine for handling log rotation and creates
// a logrotate configuration file for system-managed rotation as a fallback.
//
// Returns:
//   - error: An error if log rotation setup fails, nil otherwise
func (gl *GDPRLogger) SetupLogRotation() error {
	// Set up cron-like job for log rotation
	go gl.rotationWorker()

	// Create logrotate configuration file for system-managed rotation as well
	return gl.createLogrotateConfig()
}

// rotationWorker periodically checks and rotates logs based on retention policy.
// This function runs in the background as a goroutine, performing an initial
// rotation on startup and then checking daily for logs that need rotation or deletion.
func (gl *GDPRLogger) rotationWorker() {
	// Run initial rotation to clean up old files
	err := gl.rotateAllLogs()
	if err != nil {
		log.Error().Err(err).Msg("Failed to rotate logs on startup")
	}

	// Set up ticker for daily checks
	ticker := time.NewTicker(24 * time.Hour)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := gl.rotateAllLogs(); err != nil {
				log.Error().Err(err).Msg("Failed to rotate logs")
			}
		}
	}
}

// rotateAllLogs applies rotation to all log files.
// It handles each log category separately, applying the appropriate retention policy.
//
// Returns:
//   - error: An error if log rotation fails for any category, nil otherwise
func (gl *GDPRLogger) rotateAllLogs() error {
	// First rotate standard logs
	if err := gl.rotateLogs(gl.config.StandardLogPath, gl.config.StandardLogRetentionDays); err != nil {
		return fmt.Errorf("failed to rotate standard logs: %w", err)
	}

	// Then rotate personal logs
	if err := gl.rotateLogs(gl.config.PersonalLogPath, gl.config.PersonalDataRetentionDays); err != nil {
		return fmt.Errorf("failed to rotate personal logs: %w", err)
	}

	// Finally rotate sensitive logs
	if err := gl.rotateLogs(gl.config.SensitiveLogPath, gl.config.SensitiveDataRetentionDays); err != nil {
		return fmt.Errorf("failed to rotate sensitive logs: %w", err)
	}

	// Log successful rotation
	log.Info().
		Int("standard_retention_days", gl.config.StandardLogRetentionDays).
		Int("personal_retention_days", gl.config.PersonalDataRetentionDays).
		Int("sensitive_retention_days", gl.config.SensitiveDataRetentionDays).
		Msg("Log rotation completed")

	return nil
}

// rotateLogs rotates logs in a specific directory based on retention days.
// It renames active log files with timestamps and deletes old rotated logs
// that exceed the retention period.
//
// Parameters:
//   - dirPath: The directory containing logs to rotate
//   - retentionDays: The number of days to retain logs
//
// Returns:
//   - error: An error if log rotation fails, nil otherwise
func (gl *GDPRLogger) rotateLogs(dirPath string, retentionDays int) error {
	// Check if directory exists
	if _, err := os.Stat(dirPath); os.IsNotExist(err) {
		// Directory doesn't exist, nothing to rotate
		return nil
	}

	// Get current time for comparison
	now := time.Now()
	cutoffTime := now.Add(-time.Duration(retentionDays) * 24 * time.Hour)

	// Read directory entries
	entries, err := os.ReadDir(dirPath)
	if err != nil {
		return fmt.Errorf("failed to read directory %s: %w", dirPath, err)
	}

	// Process each file
	for _, entry := range entries {
		if entry.IsDir() {
			continue // Skip subdirectories
		}

		fileInfo, err := entry.Info()
		if err != nil {
			log.Warn().
				Err(err).
				Str("file", entry.Name()).
				Msg("Failed to get file info, skipping")
			continue
		}

		// Check file age against retention policy
		if fileInfo.ModTime().Before(cutoffTime) {
			filePath := filepath.Join(dirPath, fileInfo.Name())

			// Check if it's an active log file
			if isActiveLogFile(fileInfo.Name()) {
				// For active files, rotate instead of delete
				if err := rotateActiveLogFile(filePath); err != nil {
					log.Warn().
						Err(err).
						Str("file", filePath).
						Msg("Failed to rotate active log file")
				}
			} else {
				// Delete old rotated files
				if err := os.Remove(filePath); err != nil {
					log.Warn().
						Err(err).
						Str("file", filePath).
						Msg("Failed to delete expired log file")
				} else {
					log.Debug().
						Str("file", filePath).
						Msg("Deleted expired log file")
				}
			}
		}
	}

	return nil
}

// isActiveLogFile checks if a file is an actively written log file.
// Active log files are the primary log files without timestamps in their names.
//
// Parameters:
//   - fileName: The name of the file to check
//
// Returns:
//   - bool: true if the file is an active log file, false otherwise
func isActiveLogFile(fileName string) bool {
	// Primary log files don't have dates in their names
	return fileName == "standard.log" ||
		fileName == "personal.log" ||
		fileName == "sensitive.log"
}

// rotateActiveLogFile rotates an active log file by renaming it with a timestamp.
// This preserves the log content while creating a new empty file for future logs.
//
// Parameters:
//   - filePath: The path to the active log file
//
// Returns:
//   - error: An error if rotation fails, nil otherwise
func rotateActiveLogFile(filePath string) error {
	// Get file info to check if it's empty
	info, err := os.Stat(filePath)
	if err != nil {
		return fmt.Errorf("failed to get file info: %w", err)
	}

	// Don't rotate empty files
	if info.Size() == 0 {
		return nil
	}

	// Create new filename with timestamp
	timestamp := time.Now().Format("20060102-150405")
	dir, file := filepath.Split(filePath)
	ext := filepath.Ext(file)
	baseName := strings.TrimSuffix(file, ext)
	newPath := filepath.Join(dir, fmt.Sprintf("%s.%s%s", baseName, timestamp, ext))

	// Rename file to include timestamp
	if err := os.Rename(filePath, newPath); err != nil {
		return fmt.Errorf("failed to rename log file: %w", err)
	}

	// Create a new empty file with original name
	newFile, err := os.Create(filePath)
	if err != nil {
		return fmt.Errorf("failed to create new log file: %w", err)
	}
	defer newFile.Close()

	// Set proper permissions
	if err := os.Chmod(filePath, info.Mode()); err != nil {
		return fmt.Errorf("failed to set permissions on new log file: %w", err)
	}

	log.Info().
		Str("old_path", filePath).
		Str("new_path", newPath).
		Msg("Rotated log file")

	return nil
}

// createLogrotateConfig creates a logrotate configuration file for system-managed rotation.
// This provides a fallback rotation mechanism on Linux systems with logrotate installed.
//
// Returns:
//   - error: An error if configuration creation fails, nil otherwise
func (gl *GDPRLogger) createLogrotateConfig() error {
	// Skip if we're not on Linux or permissions might be an issue
	if !isLinuxSystem() {
		return nil
	}

	// Define paths for config
	configDir := "/etc/logrotate.d"
	configPath := filepath.Join(configDir, "hideme")

	// Check if we have permission to create the config
	if _, err := os.Stat(configDir); err != nil {
		// Can't access /etc/logrotate.d, probably not root
		// Just print a message suggesting manual setup
		log.Warn().Msg("Unable to create logrotate configuration automatically. Consider setting up manual logrotate.")
		return nil
	}

	// Create logrotate configuration
	config := fmt.Sprintf(`# HideMe GDPR-compliant logging rotation configuration
# Standard logs (no personal data)
%s/*.log {
    daily
    rotate 7
    missingok
    notifempty
    compress
    delaycompress
    create 0644 root root
    maxage %d
}

# Personal data logs
%s/*.log {
    daily
    rotate 5
    missingok
    notifempty
    compress
    delaycompress
    create 0600 root root
    maxage %d
}

# Sensitive data logs
%s/*.log {
    daily
    rotate 3
    missingok
    notifempty
    compress
    delaycompress
    create 0600 root root
    maxage %d
}
`,
		gl.config.StandardLogPath,
		gl.config.StandardLogRetentionDays,
		gl.config.PersonalLogPath,
		gl.config.PersonalDataRetentionDays,
		gl.config.SensitiveLogPath,
		gl.config.SensitiveDataRetentionDays,
	)

	// Try to write the config file
	err := os.WriteFile(configPath, []byte(config), 0644)
	if err != nil {
		log.Warn().
			Err(err).
			Str("config_path", configPath).
			Msg("Failed to create logrotate configuration. Consider setting up manual logrotate.")
		return nil
	}

	log.Info().
		Str("config_path", configPath).
		Msg("Created logrotate configuration")

	return nil
}

// isLinuxSystem checks if the current system is Linux.
// This is used to determine whether to attempt creating logrotate configurations.
//
// Returns:
//   - bool: true if the system is Linux, false otherwise
func isLinuxSystem() bool {
	return os.Getenv("OS") != "Windows_NT" && os.Getenv("GOOS") != "windows"
}

// CleanupLogs immediately deletes all logs beyond retention period.
// This can be called explicitly to force log cleanup outside the normal rotation schedule.
//
// Returns:
//   - error: An error if cleanup fails, nil otherwise
func (gl *GDPRLogger) CleanupLogs() error {
	return gl.rotateAllLogs()
}

// GetLogRetentionConfig returns the current log retention configuration.
// This allows retrieving the current retention settings for all log categories.
//
// Returns:
//   - LogRetentionConfig: The current log retention configuration
func (gl *GDPRLogger) GetLogRetentionConfig() LogRetentionConfig {
	return LogRetentionConfig{
		StandardLogRetentionDays:   gl.config.StandardLogRetentionDays,
		PersonalDataRetentionDays:  gl.config.PersonalDataRetentionDays,
		SensitiveDataRetentionDays: gl.config.SensitiveDataRetentionDays,
	}
}

// UpdateLogRetentionConfig updates the log retention configuration.
// It also updates the logrotate configuration and immediately applies
// the new settings to rotate logs.
//
// Parameters:
//   - cfg: The new GDPR logging settings to apply
func (gl *GDPRLogger) UpdateLogRetentionConfig(cfg *config.GDPRLoggingSettings) {
	gl.config.StandardLogRetentionDays = cfg.StandardLogRetentionDays
	gl.config.PersonalDataRetentionDays = cfg.PersonalDataRetentionDays
	gl.config.SensitiveDataRetentionDays = cfg.SensitiveDataRetentionDays

	// Update logrotate config
	_ = gl.createLogrotateConfig()

	// Immediately apply rotation with new settings
	_ = gl.rotateAllLogs()
}
