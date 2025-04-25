package gdprlog

import (
	"testing"
)

func TestIsSensitiveField(t *testing.T) {
	tests := []struct {
		name      string
		fieldName string
		value     interface{}
		want      bool
	}{
		{
			name:      "Password field",
			fieldName: "password",
			value:     "secret123",
			want:      true,
		},
		{
			name:      "Password with suffix",
			fieldName: "user_password",
			value:     "secret123",
			want:      true,
		},
		{
			name:      "Token field",
			fieldName: "auth_token",
			value:     "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
			want:      true,
		},
		{
			name:      "API key field",
			fieldName: "api_key",
			value:     "abcd1234",
			want:      true,
		},
		{
			name:      "Credit card field",
			fieldName: "payment_method",
			value:     "4111 1111 1111 1111", // Valid test credit card number
			want:      true,
		},
		{
			name:      "Non-sensitive field",
			fieldName: "username",
			value:     "johndoe",
			want:      false,
		},
		{
			name:      "Empty field name",
			fieldName: "",
			value:     "some value",
			want:      false,
		},
		{
			name:      "Non-string value",
			fieldName: "count",
			value:     123,
			want:      false,
		},
		{
			name:      "SSN field name",
			fieldName: "ssn",
			value:     "123-45-6789",
			want:      true,
		},
		{
			name:      "CVV field name",
			fieldName: "cvv",
			value:     "123",
			want:      true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := IsSensitiveField(tt.fieldName, tt.value); got != tt.want {
				t.Errorf("IsSensitiveField() = %v, want %v for fieldName=%s, value=%v", got, tt.want, tt.fieldName, tt.value)
			}
		})
	}
}

func TestIsPersonalField(t *testing.T) {
	tests := []struct {
		name      string
		fieldName string
		value     interface{}
		want      bool
	}{
		{
			name:      "Username field",
			fieldName: "username",
			value:     "johndoe",
			want:      true,
		},
		{
			name:      "Email field",
			fieldName: "email",
			value:     "john@example.com",
			want:      true,
		},
		{
			name:      "Email value without email field name",
			fieldName: "contact",
			value:     "john@example.com",
			want:      true,
		},
		{
			name:      "User ID field",
			fieldName: "user_id",
			value:     "12345",
			want:      true,
		},
		{
			name:      "Address field",
			fieldName: "address",
			value:     "123 Main St",
			want:      true,
		},
		{
			name:      "Phone field",
			fieldName: "phone",
			value:     "555-1234",
			want:      true,
		},
		{
			name:      "IP address field",
			fieldName: "ip_address",
			value:     "192.168.1.1",
			want:      true,
		},
		{
			name:      "Session ID field",
			fieldName: "session_id",
			value:     "abcd1234",
			want:      true,
		},
		{
			name:      "Non-personal field",
			fieldName: "status",
			value:     "active",
			want:      false,
		},
		{
			name:      "Empty field name",
			fieldName: "",
			value:     "some value",
			want:      false,
		},
		{
			name:      "Non-string value",
			fieldName: "count",
			value:     123,
			want:      false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := IsPersonalField(tt.fieldName, tt.value); got != tt.want {
				t.Errorf("IsPersonalField() = %v, want %v for fieldName=%s, value=%v", got, tt.want, tt.fieldName, tt.value)
			}
		})
	}
}

func TestIsEmailField(t *testing.T) {
	tests := []struct {
		name      string
		fieldName string
		value     interface{}
		want      bool
	}{
		{
			name:      "Email field name",
			fieldName: "email",
			value:     "test@example.com",
			want:      true,
		},
		{
			name:      "Email field with suffix",
			fieldName: "user_email",
			value:     "not-an-email",
			want:      true,
		},
		{
			name:      "Email value in non-email field",
			fieldName: "contact",
			value:     "test@example.com",
			want:      true,
		},
		{
			name:      "Non-email in non-email field",
			fieldName: "username",
			value:     "johndoe",
			want:      false,
		},
		{
			name:      "Empty field name with email value",
			fieldName: "",
			value:     "test@example.com",
			want:      true,
		},
		{
			name:      "Email field with integer value",
			fieldName: "email",
			value:     123,
			want:      true, // Field name contains 'email'
		},
		{
			name:      "Non-email field with integer value",
			fieldName: "count",
			value:     123,
			want:      false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := IsEmailField(tt.fieldName, tt.value); got != tt.want {
				t.Errorf("IsEmailField() = %v, want %v for fieldName=%s, value=%v", got, tt.want, tt.fieldName, tt.value)
			}
		})
	}
}

func TestCouldBeCreditCard(t *testing.T) {
	tests := []struct {
		name   string
		number string
		want   bool
	}{
		{
			name:   "Valid Visa",
			number: "4111111111111111", // Valid test credit card
			want:   true,
		},
		{
			name:   "Valid Mastercard",
			number: "5555555555554444", // Valid test credit card
			want:   true,
		},
		{
			name:   "Valid American Express",
			number: "378282246310005", // Valid test credit card
			want:   true,
		},
		{
			name:   "Invalid card number",
			number: "1234567890123456", // Invalid, fails Luhn check
			want:   false,
		},
		{
			name:   "Non-numeric",
			number: "41111111a1111111", // Contains non-numeric characters
			want:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := couldBeCreditCard(tt.number); got != tt.want {
				t.Errorf("couldBeCreditCard() = %v, want %v for number=%s", got, tt.want, tt.number)
			}
		})
	}
}

func TestContainsPersonalData(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  bool
	}{
		{
			name:  "Contains email",
			input: "Contact us at info@example.com for support",
			want:  true,
		},
		{
			name:  "Contains username pattern",
			input: "username: johndoe",
			want:  true,
		},
		{
			name:  "Contains user id pattern",
			input: "user_id: 12345",
			want:  true,
		},
		{
			name:  "Contains IP address mention",
			input: "ip_addr: 192.168.1.1",
			want:  true,
		},
		{
			name:  "No personal data",
			input: "This is a generic message with no personal information",
			want:  false,
		},
		{
			name:  "Very short text",
			input: "abcd",
			want:  false,
		},
		{
			name:  "Empty string",
			input: "",
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ContainsPersonalData(tt.input); got != tt.want {
				t.Errorf("ContainsPersonalData() = %v, want %v for input=%s", got, tt.want, tt.input)
			}
		})
	}
}

func TestContainsSensitiveData(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  bool
	}{
		{
			name:  "Contains password pattern",
			input: "password: secret123",
			want:  true,
		},
		{
			name:  "Contains auth token pattern",
			input: "auth_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
			want:  true,
		},
		{
			name:  "Contains SSN mention",
			input: "ssn: 123-45-6789",
			want:  true,
		},
		{
			name:  "No sensitive data",
			input: "This is a generic message with no sensitive information",
			want:  false,
		},
		{
			name:  "Very short text",
			input: "abcd",
			want:  false,
		},
		{
			name:  "Empty string",
			input: "",
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ContainsSensitiveData(tt.input); got != tt.want {
				t.Errorf("ContainsSensitiveData() = %v, want %v for input=%s", got, tt.want, tt.input)
			}
		})
	}
}

func TestToSafeString(t *testing.T) {
	tests := []struct {
		name  string
		value interface{}
		want  string
	}{
		{
			name:  "String value",
			value: "test string",
			want:  "test string",
		},
		{
			name:  "Integer value",
			value: 123,
			want:  "123",
		},
		{
			name:  "Boolean value",
			value: true,
			want:  "true",
		},
		{
			name:  "Nil value",
			value: nil,
			want:  "nil",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ToSafeString(tt.value); got != tt.want {
				t.Errorf("ToSafeString() = %v, want %v for value=%v", got, tt.want, tt.value)
			}
		})
	}
}
