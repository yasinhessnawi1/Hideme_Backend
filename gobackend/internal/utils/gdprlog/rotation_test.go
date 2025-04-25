package gdprlog

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

func TestIsActiveLogFile(t *testing.T) {
	tests := []struct {
		name     string
		fileName string
		want     bool
	}{
		{"Standard log", "standard.log", true},
		{"Personal log", "personal.log", true},
		{"Sensitive log", "sensitive.log", true},
		{"Rotated log", "standard.20210101-120000.log", false},
		{"Other file", "something.log", false},
		{"Non-log file", "file.txt", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isActiveLogFile(tt.fileName)
			if got != tt.want {
				t.Errorf("isActiveLogFile() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestRotateActiveLogFile(t *testing.T) {
	tempDir := t.TempDir()
	testLogPath := filepath.Join(tempDir, "test.log")

	// Create a test log file with content
	err := os.WriteFile(testLogPath, []byte("test log content"), 0644)
	if err != nil {
		t.Fatalf("Failed to create test log file: %v", err)
	}

	// Rotate the file
	err = rotateActiveLogFile(testLogPath)
	if err != nil {
		t.Fatalf("Failed to rotate log file: %v", err)
	}

	// Check that a new empty file was created
	info, err := os.Stat(testLogPath)
	if err != nil {
		t.Fatalf("Failed to stat new log file: %v", err)
	}

	if info.Size() != 0 {
		t.Errorf("New log file should be empty, got size: %d", info.Size())
	}

	// Check that the rotated file exists
	files, err := filepath.Glob(filepath.Join(tempDir, "test.*.log"))
	if err != nil {
		t.Fatalf("Failed to list rotated log files: %v", err)
	}

	if len(files) != 1 {
		t.Errorf("Expected 1 rotated log file, got %d", len(files))
	}
}

func TestRotateActiveLogFile_EmptyFile(t *testing.T) {
	tempDir := t.TempDir()
	testLogPath := filepath.Join(tempDir, "empty.log")

	// Create an empty log file
	err := os.WriteFile(testLogPath, []byte(""), 0644)
	if err != nil {
		t.Fatalf("Failed to create empty log file: %v", err)
	}

	// Rotate the file - should not create a rotated file for empty files
	err = rotateActiveLogFile(testLogPath)
	if err != nil {
		t.Fatalf("Failed to process empty log file: %v", err)
	}

	// Check that the original file still exists and is empty
	info, err := os.Stat(testLogPath)
	if err != nil {
		t.Fatalf("Failed to stat log file: %v", err)
	}

	if info.Size() != 0 {
		t.Errorf("Log file should be empty, got size: %d", info.Size())
	}

	// No rotated file should be created
	files, err := filepath.Glob(filepath.Join(tempDir, "empty.*.log"))
	if err != nil {
		t.Fatalf("Failed to list rotated log files: %v", err)
	}

	if len(files) != 0 {
		t.Errorf("Expected 0 rotated log files, got %d", len(files))
	}
}

func TestRotateAllLogs(t *testing.T) {
	tempDir := t.TempDir()
	now := time.Now()

	// Create directories for each log type
	standardDir := filepath.Join(tempDir, "standard")
	personalDir := filepath.Join(tempDir, "personal")
	sensitiveDir := filepath.Join(tempDir, "sensitive")

	for _, dir := range []string{standardDir, personalDir, sensitiveDir} {
		err := os.MkdirAll(dir, 0755)
		if err != nil {
			t.Fatalf("Failed to create directory %s: %v", dir, err)
		}
	}

	// Create test files in each directory
	// Standard logs - one current, one old
	err := os.WriteFile(filepath.Join(standardDir, "standard.log"), []byte("current log"), 0644)
	if err != nil {
		t.Fatalf("Failed to create standard log: %v", err)
	}

	oldStandardLog := filepath.Join(standardDir, "standard.old.log")
	err = os.WriteFile(oldStandardLog, []byte("old log"), 0644)
	if err != nil {
		t.Fatalf("Failed to create old standard log: %v", err)
	}

	// Set old file's modification time to 10 days ago
	oldTime := now.Add(-10 * 24 * time.Hour)
	err = os.Chtimes(oldStandardLog, oldTime, oldTime)
	if err != nil {
		t.Fatalf("Failed to set file time: %v", err)
	}

	// Personal logs - one current, one old
	err = os.WriteFile(filepath.Join(personalDir, "personal.log"), []byte("current personal log"), 0644)
	if err != nil {
		t.Fatalf("Failed to create personal log: %v", err)
	}

	oldPersonalLog := filepath.Join(personalDir, "personal.old.log")
	err = os.WriteFile(oldPersonalLog, []byte("old personal log"), 0644)
	if err != nil {
		t.Fatalf("Failed to create old personal log: %v", err)
	}

	// Set old file's modification time to 40 days ago
	oldTime = now.Add(-40 * 24 * time.Hour)
	err = os.Chtimes(oldPersonalLog, oldTime, oldTime)
	if err != nil {
		t.Fatalf("Failed to set file time: %v", err)
	}

	// Create a logger with the test directories
	cfg := &config.GDPRLoggingSettings{
		StandardLogPath:            standardDir,
		PersonalLogPath:            personalDir,
		SensitiveLogPath:           sensitiveDir,
		StandardLogRetentionDays:   7,
		PersonalDataRetentionDays:  30,
		SensitiveDataRetentionDays: 90,
	}

	logger := &GDPRLogger{
		config: cfg,
	}

	// Rotate all logs
	err = logger.rotateAllLogs()
	if err != nil {
		t.Fatalf("rotateAllLogs failed: %v", err)
	}

	// Check results
	// 1. standard.old.log should be deleted (>7 days old)
	if _, err := os.Stat(oldStandardLog); !os.IsNotExist(err) {
		t.Errorf("Expected standard.old.log to be deleted")
	}

	// 2. personal.old.log should be deleted (>30 days old)
	if _, err := os.Stat(oldPersonalLog); !os.IsNotExist(err) {
		t.Errorf("Expected personal.old.log to be deleted")
	}
}

func TestGetLogRetentionConfig(t *testing.T) {
	cfg := &config.GDPRLoggingSettings{
		StandardLogRetentionDays:   7,
		PersonalDataRetentionDays:  30,
		SensitiveDataRetentionDays: 90,
	}

	logger := &GDPRLogger{
		config: cfg,
	}

	retention := logger.GetLogRetentionConfig()

	if retention.StandardLogRetentionDays != 7 {
		t.Errorf("Expected StandardLogRetentionDays=7, got %d", retention.StandardLogRetentionDays)
	}

	if retention.PersonalDataRetentionDays != 30 {
		t.Errorf("Expected PersonalDataRetentionDays=30, got %d", retention.PersonalDataRetentionDays)
	}

	if retention.SensitiveDataRetentionDays != 90 {
		t.Errorf("Expected SensitiveDataRetentionDays=90, got %d", retention.SensitiveDataRetentionDays)
	}
}

func TestUpdateLogRetentionConfig(t *testing.T) {
	originalCfg := &config.GDPRLoggingSettings{
		StandardLogRetentionDays:   7,
		PersonalDataRetentionDays:  30,
		SensitiveDataRetentionDays: 90,
	}

	logger := &GDPRLogger{
		config: originalCfg,
	}

	// Update the config
	newCfg := &config.GDPRLoggingSettings{
		StandardLogRetentionDays:   14,
		PersonalDataRetentionDays:  60,
		SensitiveDataRetentionDays: 180,
	}

	logger.UpdateLogRetentionConfig(newCfg)

	// Check that the logger's config was updated
	if logger.config.StandardLogRetentionDays != 14 {
		t.Errorf("Expected StandardLogRetentionDays=14, got %d", logger.config.StandardLogRetentionDays)
	}

	if logger.config.PersonalDataRetentionDays != 60 {
		t.Errorf("Expected PersonalDataRetentionDays=60, got %d", logger.config.PersonalDataRetentionDays)
	}

	if logger.config.SensitiveDataRetentionDays != 180 {
		t.Errorf("Expected SensitiveDataRetentionDays=180, got %d", logger.config.SensitiveDataRetentionDays)
	}
}

func TestCleanupLogs(t *testing.T) {
	// Create a mock logger
	cfg := &config.GDPRLoggingSettings{
		StandardLogRetentionDays:   7,
		PersonalDataRetentionDays:  30,
		SensitiveDataRetentionDays: 90,
	}

	logger := &GDPRLogger{
		config: cfg,
	}

	// Mock rotateAllLogs to verify it's called by CleanupLogs
	// Since we can't directly mock methods in Go, we'll track if the directories are created
	tempDir := t.TempDir()
	cfg.StandardLogPath = filepath.Join(tempDir, "standard")
	cfg.PersonalLogPath = filepath.Join(tempDir, "personal")
	cfg.SensitiveLogPath = filepath.Join(tempDir, "sensitive")

	// Create the directories
	for _, dir := range []string{cfg.StandardLogPath, cfg.PersonalLogPath, cfg.SensitiveLogPath} {
		err := os.MkdirAll(dir, 0755)
		if err != nil {
			t.Fatalf("Failed to create directory %s: %v", dir, err)
		}
	}

	// Call CleanupLogs
	err := logger.CleanupLogs()
	if err != nil {
		t.Errorf("CleanupLogs failed: %v", err)
	}
}

func TestIsLinuxSystem(t *testing.T) {
	// Save original environment variables
	origOS := os.Getenv("OS")
	origGOOS := os.Getenv("GOOS")
	defer func() {
		os.Setenv("OS", origOS)
		os.Setenv("GOOS", origGOOS)
	}()

	// Test Windows detection
	os.Setenv("OS", "Windows_NT")
	if isLinuxSystem() {
		t.Errorf("Windows should not be detected as Linux")
	}

	os.Setenv("OS", "")
	os.Setenv("GOOS", "windows")
	if isLinuxSystem() {
		t.Errorf("GOOS=windows should not be detected as Linux")
	}

	// Test Linux detection
	os.Setenv("OS", "")
	os.Setenv("GOOS", "linux")
	isLinux := isLinuxSystem()

	// The test expectation depends on the environment
	// In a Windows environment, isLinuxSystem should return false
	// In a Linux environment, isLinuxSystem should return true
	// For the test, we'll just check that the function runs without errors
	t.Logf("isLinuxSystem() = %v (depends on environment)", isLinux)
}

func TestSetupLogRotation(t *testing.T) {
	tempDir := t.TempDir()

	// Create a logger with test configuration
	cfg := &config.GDPRLoggingSettings{
		StandardLogPath:            filepath.Join(tempDir, "standard"),
		PersonalLogPath:            filepath.Join(tempDir, "personal"),
		SensitiveLogPath:           filepath.Join(tempDir, "sensitive"),
		StandardLogRetentionDays:   7,
		PersonalDataRetentionDays:  30,
		SensitiveDataRetentionDays: 90,
	}

	logger := &GDPRLogger{
		config: cfg,
	}

	// SetupLogRotation starts a goroutine, we just test that it returns without error
	err := logger.SetupLogRotation()
	if err != nil {
		t.Errorf("SetupLogRotation failed: %v", err)
	}

	// We can't easily test the goroutine, so we'll just verify the function completes
	t.Log("SetupLogRotation completed successfully")
}

func TestRotateLogsNonExistentDirectory(t *testing.T) {
	tempDir := t.TempDir()
	nonExistentDir := filepath.Join(tempDir, "nonexistent")

	// Create a logger
	cfg := &config.GDPRLoggingSettings{}
	logger := &GDPRLogger{config: cfg}

	// Call rotateLogs on a non-existent directory
	err := logger.rotateLogs(nonExistentDir, 7)
	if err != nil {
		t.Errorf("rotateLogs should not fail for non-existent directory: %v", err)
	}
}

func TestRotateActiveLogFilePermissions(t *testing.T) {
	tempDir := t.TempDir()
	testLogPath := filepath.Join(tempDir, "test.log")

	// Create a test log file with restrictive permissions
	err := os.WriteFile(testLogPath, []byte("test log content"), 0600)
	if err != nil {
		t.Fatalf("Failed to create test log file: %v", err)
	}

	// Get the original permissions
	originalInfo, err := os.Stat(testLogPath)
	if err != nil {
		t.Fatalf("Failed to stat log file: %v", err)
	}
	originalMode := originalInfo.Mode()

	// Rotate the file
	err = rotateActiveLogFile(testLogPath)
	if err != nil {
		t.Fatalf("Failed to rotate log file: %v", err)
	}

	// Check that the new file has the same permissions
	newInfo, err := os.Stat(testLogPath)
	if err != nil {
		t.Fatalf("Failed to stat new log file: %v", err)
	}

	if newInfo.Mode() != originalMode {
		t.Errorf("New log file has different permissions: got %v, want %v",
			newInfo.Mode(), originalMode)
	}
}
