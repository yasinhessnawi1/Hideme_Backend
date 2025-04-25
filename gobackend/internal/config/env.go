// Package config provides configuration management for the HideMe API Server.
// It includes loading configurations from YAML files, environment variables,
// and command-line arguments. The package supports structured configuration
// with validation and type conversion, making it easy to manage application settings.
package config

import (
	"fmt"
	"os"
	"reflect"
	"strconv"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
)

// LoadEnv loads environment variables into the config struct.
// It uses struct tags to determine which environment variables to look for
// and how to map them to the configuration fields.
//
// This function performs type-aware conversion from string environment variables
// to the appropriate Go types (int, bool, duration, etc.) based on the field type.
//
// Parameters:
//   - config: The configuration struct to populate from environment variables
//
// Returns:
//   - An error if any environment variable conversion fails
func LoadEnv(config *AppConfig) error {
	log.Debug().Msg("Loading environment variables")

	// Process each subsection of the configuration
	// This allows for a more organized approach to configuration loading

	// Process AppSettings
	if err := processStructEnv(&config.App); err != nil {
		return err
	}

	// Process DatabaseSettings
	if err := processStructEnv(&config.Database); err != nil {
		return err
	}

	// Process ServerSettings
	if err := processStructEnv(&config.Server); err != nil {
		return err
	}

	// Process JWTSettings
	if err := processStructEnv(&config.JWT); err != nil {
		return err
	}

	// Process APIKeySettings
	if err := processStructEnv(&config.APIKey); err != nil {
		return err
	}

	// Process LoggingSettings
	if err := processStructEnv(&config.Logging); err != nil {
		return err
	}

	// Process CORSSettings
	if err := processStructEnv(&config.CORS); err != nil {
		return err
	}

	// Process HashSettings
	if err := processStructEnv(&config.PasswordHash); err != nil {
		return err
	}

	// Process GDPRLoggingSettings
	if err := processStructEnv(&config.GDPRLogging); err != nil {
		return err
	}

	// Log some key environment variables for debugging purposes
	// Note that sensitive values are not logged here
	log.Debug().
		Str("APP_ENV", os.Getenv("APP_ENV")).
		Str("DB_USER", os.Getenv("DB_USER")).
		Str("DB_HOST", os.Getenv("DB_HOST")).
		Msg("Environment variables loaded")

	return nil
}

// processStructEnv processes environment variables for a struct using reflection.
// It looks for the "env" tag on struct fields to determine which environment
// variables to read, and then sets the corresponding field values.
//
// Parameters:
//   - s: A pointer to the struct to process
//
// Returns:
//   - An error if any environment variable parsing fails
func processStructEnv(s interface{}) error {
	val := reflect.ValueOf(s).Elem()
	typ := val.Type()

	// Iterate through each field in the struct
	for i := 0; i < typ.NumField(); i++ {
		field := typ.Field(i)
		fieldVal := val.Field(i)

		// Skip if not settable (e.g., unexported fields)
		if !fieldVal.CanSet() {
			continue
		}

		// Get the environment variable name from the tag
		envName := field.Tag.Get("env")
		if envName == "" {
			continue
		}

		// Get the environment variable value
		envValue, exists := os.LookupEnv(envName)
		if !exists {
			continue
		}

		// Set the field value based on its type
		// This handles different types appropriately
		switch fieldVal.Kind() {
		case reflect.String:
			fieldVal.SetString(envValue)

		case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
			if field.Type == reflect.TypeOf(time.Duration(0)) {
				// Special handling for time.Duration
				duration, err := time.ParseDuration(envValue)
				if err != nil {
					return fmt.Errorf("invalid duration for %s: %w", envName, err)
				}
				fieldVal.Set(reflect.ValueOf(duration))
			} else {
				// Regular integer types
				intValue, err := strconv.ParseInt(envValue, 10, 64)
				if err != nil {
					return fmt.Errorf("invalid integer for %s: %w", envName, err)
				}
				fieldVal.SetInt(intValue)
			}

		case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
			uintValue, err := strconv.ParseUint(envValue, 10, 64)
			if err != nil {
				return fmt.Errorf("invalid unsigned integer for %s: %w", envName, err)
			}
			fieldVal.SetUint(uintValue)

		case reflect.Bool:
			boolValue, err := strconv.ParseBool(envValue)
			if err != nil {
				return fmt.Errorf("invalid boolean for %s: %w", envName, err)
			}
			fieldVal.SetBool(boolValue)

		case reflect.Float32, reflect.Float64:
			floatValue, err := strconv.ParseFloat(envValue, 64)
			if err != nil {
				return fmt.Errorf("invalid float for %s: %w", envName, err)
			}
			fieldVal.SetFloat(floatValue)

		case reflect.Slice:
			// Handle slice types (only string slices supported for now)
			if fieldVal.Type().Elem().Kind() == reflect.String {
				// Split comma-separated list into slice
				values := strings.Split(envValue, ",")
				// Trim whitespace from each value
				for i, v := range values {
					values[i] = strings.TrimSpace(v)
				}
				fieldVal.Set(reflect.ValueOf(values))
			}

		default:
			// Skip unsupported types without error
			// This allows for future extension without breaking existing code
		}
	}

	return nil
}
