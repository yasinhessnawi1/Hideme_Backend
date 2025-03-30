package config

import (
	"os"
	"testing"
	"time"
)

func TestLoadEnv(t *testing.T) {
	// Set environment variables for testing
	os.Setenv("APP_ENV", "test-env")
	os.Setenv("APP_NAME", "test-app")
	os.Setenv("SERVER_PORT", "9090")
	os.Setenv("DB_HOST", "test-db-host")
	os.Setenv("JWT_EXPIRY", "30m")
	os.Setenv("API_KEY_EXPIRY", "720h")
	os.Setenv("ALLOWED_ORIGINS", "https://example.com,https://api.example.com")
	os.Setenv("CORS_ALLOW_CREDENTIALS", "true")
	os.Setenv("HASH_ITERATIONS", "2")

	// Clean up after the test
	defer func() {
		os.Unsetenv("APP_ENV")
		os.Unsetenv("APP_NAME")
		os.Unsetenv("SERVER_PORT")
		os.Unsetenv("DB_HOST")
		os.Unsetenv("JWT_EXPIRY")
		os.Unsetenv("API_KEY_EXPIRY")
		os.Unsetenv("ALLOWED_ORIGINS")
		os.Unsetenv("CORS_ALLOW_CREDENTIALS")
		os.Unsetenv("HASH_ITERATIONS")
	}()

	// Create config
	config := &AppConfig{}

	// Load environment variables
	err := LoadEnv(config)
	if err != nil {
		t.Fatalf("LoadEnv() error = %v", err)
	}

	// Check that environment variables were loaded
	if config.App.Environment != "test-env" {
		t.Errorf("Expected App.Environment = %s, got %s", "test-env", config.App.Environment)
	}

	if config.App.Name != "test-app" {
		t.Errorf("Expected App.Name = %s, got %s", "test-app", config.App.Name)
	}

	if config.Server.Port != 9090 {
		t.Errorf("Expected Server.Port = %d, got %d", 9090, config.Server.Port)
	}

	if config.Database.Host != "test-db-host" {
		t.Errorf("Expected Database.Host = %s, got %s", "test-db-host", config.Database.Host)
	}

	if config.JWT.Expiry != 30*time.Minute {
		t.Errorf("Expected JWT.Expiry = %v, got %v", 30*time.Minute, config.JWT.Expiry)
	}

	if config.APIKey.DefaultExpiry != 720*time.Hour {
		t.Errorf("Expected APIKey.DefaultExpiry = %v, got %v", 720*time.Hour, config.APIKey.DefaultExpiry)
	}

	if len(config.CORS.AllowedOrigins) != 2 ||
		config.CORS.AllowedOrigins[0] != "https://example.com" ||
		config.CORS.AllowedOrigins[1] != "https://api.example.com" {
		t.Errorf("Expected CORS.AllowedOrigins = %v, got %v",
			[]string{"https://example.com", "https://api.example.com"},
			config.CORS.AllowedOrigins)
	}

	if !config.CORS.AllowCredentials {
		t.Errorf("Expected CORS.AllowCredentials = %v, got %v", true, config.CORS.AllowCredentials)
	}

	if config.PasswordHash.Iterations != 2 {
		t.Errorf("Expected PasswordHash.Iterations = %d, got %d", 2, config.PasswordHash.Iterations)
	}
}

func TestProcessStructEnv(t *testing.T) {
	// Define a test struct
	type TestStruct struct {
		StringField string        `env:"TEST_STRING"`
		IntField    int           `env:"TEST_INT"`
		BoolField   bool          `env:"TEST_BOOL"`
		DurField    time.Duration `env:"TEST_DURATION"`
		FloatField  float64       `env:"TEST_FLOAT"`
		StrSlice    []string      `env:"TEST_SLICE"`
		NoEnvTag    string
	}

	// Set environment variables
	os.Setenv("TEST_STRING", "test-value")
	os.Setenv("TEST_INT", "42")
	os.Setenv("TEST_BOOL", "true")
	os.Setenv("TEST_DURATION", "15m")
	os.Setenv("TEST_FLOAT", "3.14")
	os.Setenv("TEST_SLICE", "item1,item2,item3")

	// Clean up
	defer func() {
		os.Unsetenv("TEST_STRING")
		os.Unsetenv("TEST_INT")
		os.Unsetenv("TEST_BOOL")
		os.Unsetenv("TEST_DURATION")
		os.Unsetenv("TEST_FLOAT")
		os.Unsetenv("TEST_SLICE")
	}()

	// Create struct
	testStruct := &TestStruct{}

	// Process environment variables
	err := processStructEnv(testStruct)
	if err != nil {
		t.Fatalf("processStructEnv() error = %v", err)
	}

	// Check values
	if testStruct.StringField != "test-value" {
		t.Errorf("Expected StringField = %s, got %s", "test-value", testStruct.StringField)
	}

	if testStruct.IntField != 42 {
		t.Errorf("Expected IntField = %d, got %d", 42, testStruct.IntField)
	}

	if !testStruct.BoolField {
		t.Errorf("Expected BoolField = %v, got %v", true, testStruct.BoolField)
	}

	if testStruct.DurField != 15*time.Minute {
		t.Errorf("Expected DurField = %v, got %v", 15*time.Minute, testStruct.DurField)
	}

	if testStruct.FloatField != 3.14 {
		t.Errorf("Expected FloatField = %f, got %f", 3.14, testStruct.FloatField)
	}

	expectedSlice := []string{"item1", "item2", "item3"}
	if len(testStruct.StrSlice) != len(expectedSlice) {
		t.Errorf("Expected StrSlice length = %d, got %d", len(expectedSlice), len(testStruct.StrSlice))
	} else {
		for i, item := range expectedSlice {
			if testStruct.StrSlice[i] != item {
				t.Errorf("Expected StrSlice[%d] = %s, got %s", i, item, testStruct.StrSlice[i])
			}
		}
	}

	// Field without env tag should be unchanged
	if testStruct.NoEnvTag != "" {
		t.Errorf("Expected NoEnvTag to be empty, got %s", testStruct.NoEnvTag)
	}
}

func TestProcessStructEnvErrors(t *testing.T) {
	// Test invalid values for different types
	tests := []struct {
		name        string
		envName     string
		envValue    string
		fieldType   string
		shouldError bool
	}{
		{
			name:        "Invalid int",
			envName:     "TEST_INT",
			envValue:    "not-an-int",
			fieldType:   "IntField",
			shouldError: true,
		},
		{
			name:        "Invalid bool",
			envName:     "TEST_BOOL",
			envValue:    "not-a-bool",
			fieldType:   "BoolField",
			shouldError: true,
		},
		{
			name:        "Invalid duration",
			envName:     "TEST_DURATION",
			envValue:    "not-a-duration",
			fieldType:   "DurField",
			shouldError: true,
		},
		{
			name:        "Invalid float",
			envName:     "TEST_FLOAT",
			envValue:    "not-a-float",
			fieldType:   "FloatField",
			shouldError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Set up test struct based on field type
			var testStruct interface{}
			switch tt.fieldType {
			case "IntField":
				testStruct = &struct {
					IntField int `env:"TEST_INT"`
				}{}
			case "BoolField":
				testStruct = &struct {
					BoolField bool `env:"TEST_BOOL"`
				}{}
			case "DurField":
				testStruct = &struct {
					DurField time.Duration `env:"TEST_DURATION"`
				}{}
			case "FloatField":
				testStruct = &struct {
					FloatField float64 `env:"TEST_FLOAT"`
				}{}
			}

			// Set environment variable
			os.Setenv(tt.envName, tt.envValue)
			defer os.Unsetenv(tt.envName)

			// Process environment variables
			err := processStructEnv(testStruct)

			// Check error
			if (err != nil) != tt.shouldError {
				t.Errorf("processStructEnv() error = %v, shouldError %v", err, tt.shouldError)
			}
		})
	}
}
