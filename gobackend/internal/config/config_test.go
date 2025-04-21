package config

import (
	"os"
	"testing"
)

func TestLoad(t *testing.T) {
	// Create a temporary config file
	configPath := "config_test.yaml"
	configContent := `
app:
  environment: testing
  name: TestApp
  version: 1.0.0
server:
  host: 127.0.0.1
  port: 8080
  read_timeout: 5s
  write_timeout: 10s
database:
  host: localhost
  port: 3306
  name: test_db
  user: testuser
  password: testpass
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatalf("Failed to create test config file: %v", err)
	}
	defer os.Remove(configPath)

	// Load the configuration
	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	// Check the loaded values
	if cfg.App.Environment != "testing" {
		t.Errorf("Expected Environment = %s, got %s", "testing", cfg.App.Environment)
	}

	if cfg.App.Name != "TestApp" {
		t.Errorf("Expected Name = %s, got %s", "TestApp", cfg.App.Name)
	}

	if cfg.Server.Port != 8080 {
		t.Errorf("Expected Port = %d, got %d", 8080, cfg.Server.Port)
	}

	if cfg.Database.Host != "localhost" {
		t.Errorf("Expected Host = %s, got %s", "localhost", cfg.Database.Host)
	}
}

func TestLoadWithInvalidPath(t *testing.T) {

}

func TestGet(t *testing.T) {
	// Set up a test configuration
	origCfg := cfg
	defer func() { cfg = origCfg }() // Restore global config after test

	testCfg := &AppConfig{
		App: AppSettings{
			Name: "TestApp",
		},
	}

	// Set the global config
	cfg = testCfg

	// Get the config
	result := Get()

	// Check that it's the same instance
	if result != testCfg {
		t.Errorf("Get() = %v, want %v", result, testCfg)
	}
}

func TestDatabaseSettings_ConnectionString(t *testing.T) {
	tests := []struct {
		name     string
		settings DatabaseSettings
		want     string
	}{
		{
			name: "With password",
			settings: DatabaseSettings{
				Host:     "localhost",
				Port:     3306,
				Name:     "testdb",
				User:     "user",
				Password: "pass",
			},
			want: "user:pass@tcp(localhost:3306)/testdb?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
		},
		{
			name: "Without password",
			settings: DatabaseSettings{
				Host:     "localhost",
				Port:     3306,
				Name:     "testdb",
				User:     "user",
				Password: "",
			},
			want: "user@tcp(localhost:3306)/testdb?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			connStr := tt.settings.ConnectionString()
			if connStr != tt.want {
				t.Errorf("ConnectionString() = %v, want %v", connStr, tt.want)
			}
		})
	}
}

func TestServerSettings_ServerAddress(t *testing.T) {
	settings := ServerSettings{
		Host: "localhost",
		Port: 8080,
	}

	want := "localhost:8080"
	if got := settings.ServerAddress(); got != want {
		t.Errorf("ServerAddress() = %v, want %v", got, want)
	}
}

func TestAppSettings_Environment(t *testing.T) {
	tests := []struct {
		name         string
		environment  string
		isDev        bool
		isProduction bool
		isTesting    bool
	}{
		{
			name:         "Development",
			environment:  "development",
			isDev:        true,
			isProduction: false,
			isTesting:    false,
		},
		{
			name:         "Production",
			environment:  "production",
			isDev:        false,
			isProduction: true,
			isTesting:    false,
		},
		{
			name:         "Testing",
			environment:  "testing",
			isDev:        false,
			isProduction: false,
			isTesting:    true,
		},
		{
			name:         "Unknown (defaults to dev)",
			environment:  "unknown",
			isDev:        false,
			isProduction: false,
			isTesting:    false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			settings := AppSettings{
				Environment: tt.environment,
			}

			if got := settings.IsDevelopment(); got != tt.isDev {
				t.Errorf("IsDevelopment() = %v, want %v", got, tt.isDev)
			}

			if got := settings.IsProduction(); got != tt.isProduction {
				t.Errorf("IsProduction() = %v, want %v", got, tt.isProduction)
			}

			if got := settings.IsTesting(); got != tt.isTesting {
				t.Errorf("IsTesting() = %v, want %v", got, tt.isTesting)
			}
		})
	}
}

func TestSetDefaults(t *testing.T) {

}

func TestValidateConfig(t *testing.T) {
	tests := []struct {
		name      string
		config    *AppConfig
		shouldErr bool
	}{
		{
			name: "Valid config",
			config: &AppConfig{
				App: AppSettings{
					Environment: "development",
				},
				Database: DatabaseSettings{
					User: "testuser",
				},
				JWT: JWTSettings{
					Secret: "some-secret",
				},
				Logging: LoggingSettings{
					Level: "info",
				},
			},
			shouldErr: false,
		},
		{
			name: "Invalid environment",
			config: &AppConfig{
				App: AppSettings{
					Environment: "invalid",
				},
				Database: DatabaseSettings{
					User: "testuser",
				},
				JWT: JWTSettings{
					Secret: "some-secret",
				},
				Logging: LoggingSettings{
					Level: "info",
				},
			},
			shouldErr: false, // It will default to development with a warning
		},
		{
			name: "Production without JWT secret",
			config: &AppConfig{
				App: AppSettings{
					Environment: "production",
				},
				Database: DatabaseSettings{
					User: "testuser",
				},
				JWT: JWTSettings{
					Secret: "changeme", // This is not allowed in production
				},
				Logging: LoggingSettings{
					Level: "info",
				},
			},
			shouldErr: true,
		},
		{
			name: "Missing database user",
			config: &AppConfig{
				App: AppSettings{
					Environment: "development",
				},
				Database: DatabaseSettings{
					User: "", // Missing user
				},
				JWT: JWTSettings{
					Secret: "some-secret",
				},
				Logging: LoggingSettings{
					Level: "info",
				},
			},
			shouldErr: true,
		},
		{
			name: "Invalid log level",
			config: &AppConfig{
				App: AppSettings{
					Environment: "development",
				},
				Database: DatabaseSettings{
					User: "testuser",
				},
				JWT: JWTSettings{
					Secret: "some-secret",
				},
				Logging: LoggingSettings{
					Level: "invalid", // Invalid level
				},
			},
			shouldErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateConfig(tt.config)

			if (err != nil) != tt.shouldErr {
				t.Errorf("validateConfig() error = %v, shouldErr %v", err, tt.shouldErr)
			}
		})
	}
}
