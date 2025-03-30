package utils_test

import (
	"errors"
	"reflect"
	"testing"

	"github.com/go-sql-driver/mysql"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

func TestJoinStrings(t *testing.T) {
	tests := []struct {
		name string
		strs []string
		sep  string
		want string
	}{
		{
			name: "Simple join",
			strs: []string{"a", "b", "c"},
			sep:  ",",
			want: "a,b,c",
		},
		{
			name: "Empty strings",
			strs: []string{"", "", ""},
			sep:  ",",
			want: ",,",
		},
		{
			name: "Empty separator",
			strs: []string{"a", "b", "c"},
			sep:  "",
			want: "abc",
		},
		{
			name: "Empty slice",
			strs: []string{},
			sep:  ",",
			want: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.JoinStrings(tt.strs, tt.sep); got != tt.want {
				t.Errorf("JoinStrings() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestFormatInt64(t *testing.T) {
	tests := []struct {
		name string
		i    int64
		want string
	}{
		{
			name: "Positive number",
			i:    42,
			want: "42",
		},
		{
			name: "Zero",
			i:    0,
			want: "0",
		},
		{
			name: "Negative number",
			i:    -123,
			want: "-123",
		},
		{
			name: "Large number",
			i:    9223372036854775807, // max int64
			want: "9223372036854775807",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.FormatInt64(tt.i); got != tt.want {
				t.Errorf("FormatInt64() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestPlural(t *testing.T) {
	tests := []struct {
		name  string
		count int
		word  string
		want  string
	}{
		{
			name:  "Single",
			count: 1,
			word:  "item",
			want:  "1 item",
		},
		{
			name:  "Multiple",
			count: 2,
			word:  "item",
			want:  "2 items",
		},
		{
			name:  "Zero",
			count: 0,
			word:  "item",
			want:  "0 items",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.Plural(tt.count, tt.word); got != tt.want {
				t.Errorf("Plural() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestIsDuplicateKeyError(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "Duplicate key error",
			err:  &mysql.MySQLError{Number: 1062, Message: "Duplicate entry"},
			want: true,
		},
		{
			name: "Other MySQL error",
			err:  &mysql.MySQLError{Number: 1054, Message: "Unknown column"},
			want: false,
		},
		{
			name: "Non-MySQL error",
			err:  errors.New("standard error"),
			want: false,
		},
		{
			name: "Nil error",
			err:  nil,
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.IsDuplicateKeyError(tt.err); got != tt.want {
				t.Errorf("IsDuplicateKeyError() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestTruncateString(t *testing.T) {
	tests := []struct {
		name   string
		s      string
		maxLen int
		want   string
	}{
		{
			name:   "No truncation needed",
			s:      "Hello",
			maxLen: 10,
			want:   "Hello",
		},
		{
			name:   "Truncation needed",
			s:      "Hello, world!",
			maxLen: 8,
			want:   "Hello...",
		},
		{
			name:   "Exact length",
			s:      "Hello",
			maxLen: 5,
			want:   "Hello",
		},
		{
			name:   "Empty string",
			s:      "",
			maxLen: 5,
			want:   "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.TruncateString(tt.s, tt.maxLen); got != tt.want {
				t.Errorf("TruncateString() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestMaskEmail(t *testing.T) {
	tests := []struct {
		name  string
		email string
		want  string
	}{
		{
			name:  "Short username",
			email: "ab@example.com",
			want:  "ab@example.com", // Too short to mask
		},
		{
			name:  "One character username",
			email: "a@example.com",
			want:  "a@example.com", // Too short to mask
		},
		{
			name:  "Invalid email format",
			email: "invalid-email",
			want:  "invalid-email", // Invalid format, return as is
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.MaskEmail(tt.email); got != tt.want {
				t.Errorf("MaskEmail() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestSanitizeKeys(t *testing.T) {
	tests := []struct {
		name string
		data map[string]interface{}
		want map[string]interface{}
	}{
		{
			name: "Contains sensitive keys",
			data: map[string]interface{}{
				"user":          "John",
				"password":      "secret123",
				"api_key":       "abcdef",
				"email":         "john@example.com",
				"password_hash": "hashedpassword",
			},
			want: map[string]interface{}{
				"user":          "John",
				"password":      "[REDACTED]",
				"api_key":       "[REDACTED]",
				"email":         "john@example.com",
				"password_hash": "[REDACTED]",
			},
		},
		{
			name: "No sensitive keys",
			data: map[string]interface{}{
				"user":  "John",
				"email": "john@example.com",
			},
			want: map[string]interface{}{
				"user":  "John",
				"email": "john@example.com",
			},
		},
		{
			name: "Contains nested map",
			data: map[string]interface{}{
				"user": "John",
				"credentials": map[string]interface{}{
					"password": "secret123",
					"token":    "abcdef",
				},
			},
			want: map[string]interface{}{
				"user": "John",
				"credentials": map[string]interface{}{
					"password": "[REDACTED]",
					"token":    "[REDACTED]",
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := utils.SanitizeKeys(tt.data)
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("SanitizeKeys() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestContainsString(t *testing.T) {
	tests := []struct {
		name  string
		slice []string
		str   string
		want  bool
	}{
		{
			name:  "String is in slice",
			slice: []string{"a", "b", "c"},
			str:   "b",
			want:  true,
		},
		{
			name:  "String is not in slice",
			slice: []string{"a", "b", "c"},
			str:   "d",
			want:  false,
		},
		{
			name:  "Empty slice",
			slice: []string{},
			str:   "a",
			want:  false,
		},
		{
			name:  "Empty string",
			slice: []string{"a", "b", "c"},
			str:   "",
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.ContainsString(tt.slice, tt.str); got != tt.want {
				t.Errorf("ContainsString() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestRemoveString(t *testing.T) {
	tests := []struct {
		name  string
		slice []string
		str   string
		want  []string
	}{
		{
			name:  "Remove existing string",
			slice: []string{"a", "b", "c"},
			str:   "b",
			want:  []string{"a", "c"},
		},
		{
			name:  "Remove non-existent string",
			slice: []string{"a", "b", "c"},
			str:   "d",
			want:  []string{"a", "b", "c"},
		},
		{
			name:  "Remove multiple occurrences",
			slice: []string{"a", "b", "a", "c"},
			str:   "a",
			want:  []string{"b", "c"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := utils.RemoveString(tt.slice, tt.str)
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("RemoveString() = %v, want %v", got, tt.want)
			}
		})
	}
}
