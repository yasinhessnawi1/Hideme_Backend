// internal/utils/validation.go
package utils

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"strings"

	"github.com/go-playground/validator/v10"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

var (
	// validate is a singleton validator instance
	validate *validator.Validate
)

// InitValidator initializes the validator with custom validations
func InitValidator() {
	// Create a new validator instance
	validate = validator.New()

	// Register function to get json tag names instead of struct field names
	validate.RegisterTagNameFunc(func(fld reflect.StructField) string {
		name := strings.SplitN(fld.Tag.Get("json"), ",", 2)[0]
		if name == "-" {
			return ""
		}
		return name
	})

	// Register custom validations
	registerCustomValidations(validate)

	log.Info().Msg("Validator initialized")
}

// GetValidator returns the singleton validator instance
func GetValidator() *validator.Validate {
	if validate == nil {
		InitValidator()
	}
	return validate
}

// DecodeJSON decodes a JSON request body into the provided struct
// with improved error handling and size limits
func DecodeJSON(r *http.Request, v interface{}) error {
	// Limit the size of the request body to prevent DOS attacks
	r.Body = http.MaxBytesReader(nil, r.Body, constants.MaxRequestBodySize)

	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()

	if err := dec.Decode(v); err != nil {
		var syntaxError *json.SyntaxError
		var unmarshalTypeError *json.UnmarshalTypeError
		var invalidUnmarshalError *json.InvalidUnmarshalError

		switch {
		case err.Error() == "http: request body too large":
			return NewBadRequestError(constants.MsgRequestBodyTooLarge)

		case err == io.EOF:
			return NewBadRequestError(constants.MsgEmptyRequestBody)

		case err == io.ErrUnexpectedEOF:
			return NewBadRequestError(constants.MsgMalformedJSON)

		case strings.HasPrefix(err.Error(), "json: unknown field "):
			fieldName := strings.TrimPrefix(err.Error(), "json: unknown field ")
			return NewValidationError("unknown_field", fmt.Sprintf("Request body contains unknown field %s", fieldName))

		case errors.As(err, &syntaxError):
			return NewBadRequestError(fmt.Sprintf("Request body contains malformed JSON (at position %d)", syntaxError.Offset))

		case errors.As(err, &unmarshalTypeError):
			if unmarshalTypeError.Field != "" {
				return NewValidationError(unmarshalTypeError.Field, fmt.Sprintf("Must be a %s", unmarshalTypeError.Type.String()))
			}
			return NewBadRequestError(fmt.Sprintf("Request body contains incorrect JSON type (at position %d)", unmarshalTypeError.Offset))

		case errors.As(err, &invalidUnmarshalError):
			return NewInternalServerError(err)

		default:
			return NewBadRequestError(fmt.Sprintf("Error decoding JSON: %s", err.Error()))
		}
	}

	// Check for additional JSON data that would be ignored
	if dec.More() {
		return NewBadRequestError("Request body must only contain a single JSON object")
	}

	return nil
}

// ValidateStruct validates a struct using the validator
func ValidateStruct(v interface{}) error {
	if validate == nil {
		InitValidator()
	}

	err := validate.Struct(v)
	if err == nil {
		return nil
	}

	// Handle validation errors
	var validationErrors validator.ValidationErrors
	if errors.As(err, &validationErrors) {
		// If only one field has an error, return a specific field error
		if len(validationErrors) == 1 {
			e := validationErrors[0]
			fieldName := e.Field()
			errorMessage := getErrorMessage(e)
			return NewValidationError(fieldName, errorMessage)
		}

		// Create a validation error with details for all fields
		details := make(map[string]string)
		for _, e := range validationErrors {
			fieldName := e.Field()
			errorMessage := getErrorMessage(e)
			details[fieldName] = errorMessage
		}

		return NewValidationErrorWithDetails("Multiple validation errors", details)
	}

	// Handle other validation errors
	return NewBadRequestError(err.Error())
}

// DecodeAndValidate decodes a JSON request body and validates it
func DecodeAndValidate(r *http.Request, v interface{}) error {
	if err := DecodeJSON(r, v); err != nil {
		return err
	}
	return ValidateStruct(v)
}

// getErrorMessage returns a user-friendly error message for a validation error
func getErrorMessage(e validator.FieldError) string {
	switch e.Tag() {
	case "required":
		return "This field is required"
	case "email":
		return "Must be a valid email address"
	case "min":
		if e.Type().Kind() == reflect.String {
			return fmt.Sprintf("Must be at least %s characters long", e.Param())
		}
		return fmt.Sprintf("Must be at least %s", e.Param())
	case "max":
		if e.Type().Kind() == reflect.String {
			return fmt.Sprintf("Must be at most %s characters long", e.Param())
		}
		return fmt.Sprintf("Must be at most %s", e.Param())
	case "eqfield":
		return fmt.Sprintf("Must match the %s field", e.Param())
	case "oneof":
		allowedValues := strings.Replace(e.Param(), " ", ", ", -1)
		return fmt.Sprintf("Must be one of: %s", allowedValues)
	case "alphanum":
		return "Must contain only alphanumeric characters"
	// Add more custom messages for other validation tags
	default:
		return fmt.Sprintf("Failed validation on the '%s' tag", e.Tag())
	}
}

// registerCustomValidations adds custom validation functions to the validator
func registerCustomValidations(v *validator.Validate) {
	// Example custom validation: password strength
	if err := v.RegisterValidation("strong_password", validateStrongPassword); err != nil {
		log.Error().Err(err).Msg("Failed to register strong_password validation")
	}
}

// Custom validation function for password strength
func validateStrongPassword(fl validator.FieldLevel) bool {
	password := fl.Field().String()

	// Password strength criteria
	hasUpper := false
	hasLower := false
	hasNumber := false
	hasSpecial := false

	for _, char := range password {
		switch {
		case char >= 'A' && char <= 'Z':
			hasUpper = true
		case char >= 'a' && char <= 'z':
			hasLower = true
		case char >= '0' && char <= '9':
			hasNumber = true
		case strings.ContainsRune("!@#$%^&*()_+=-[]{}|;:,.<>?/", char):
			hasSpecial = true
		}
	}

	// Require at least 3 of the 4 criteria
	criteria := 0
	if hasUpper {
		criteria++
	}
	if hasLower {
		criteria++
	}
	if hasNumber {
		criteria++
	}
	if hasSpecial {
		criteria++
	}

	return criteria >= 3
}

// NewValidationErrorWithDetails creates a validation error with multiple field details
func NewValidationErrorWithDetails(message string, details map[string]string) *AppError {
	detailsMap := make(map[string]interface{})
	for k, v := range details {
		detailsMap[k] = v
	}

	return &AppError{
		Err:        ErrValidation,
		StatusCode: http.StatusBadRequest,
		Message:    message,
		Details:    detailsMap,
	}
}

// IsValidEmail checks if a string is a valid email address
func IsValidEmail(email string) bool {
	return GetValidator().Var(email, "email") == nil
}

// ValidateUsername validates a username
func ValidateUsername(username string) error {
	if len(username) < constants.MinUsernameLength {
		return NewValidationError(constants.ColumnUsername, fmt.Sprintf("Username must be at least %d characters long", constants.MinUsernameLength))
	}
	if len(username) > constants.MaxUsernameLength {
		return NewValidationError(constants.ColumnUsername, fmt.Sprintf("Username must be at most %d characters long", constants.MaxUsernameLength))
	}
	if err := GetValidator().Var(username, "alphanum"); err != nil {
		return NewValidationError(constants.ColumnUsername, "Username must contain only alphanumeric characters")
	}
	return nil
}

// ValidatePassword validates a password
func ValidatePassword(password string) error {
	if len(password) < constants.MinPasswordLength {
		return NewValidationError("password", fmt.Sprintf("Password must be at least %d characters long", constants.MinPasswordLength))
	}

	if err := GetValidator().Var(password, "strong_password"); err != nil {
		return NewValidationError("password", "Password must contain at least 3 of the following: uppercase letters, lowercase letters, numbers, and special characters")
	}

	return nil
}
