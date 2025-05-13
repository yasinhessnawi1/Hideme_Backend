package utils

import (
	"bytes"
	"encoding/base64"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEncryptKey(t *testing.T) {
	t.Run("Successfully encrypt key", func(t *testing.T) {
		// Arrange
		key := "test-api-key-1234567890"
		encryptionKey := bytes.Repeat([]byte("a"), 32) // 32-byte encryption key

		// Act
		encryptedKey, err := EncryptKey(key, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.NotEmpty(t, encryptedKey)

		// Check if the result is a valid base64 string
		_, err = base64.StdEncoding.DecodeString(encryptedKey)
		assert.NoError(t, err)

		// Encrypted key should be different from the original
		assert.NotEqual(t, key, encryptedKey)
	})

	t.Run("Different keys produce different encryptions", func(t *testing.T) {
		// Arrange
		key1 := "test-api-key-1"
		key2 := "test-api-key-2"
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		encryptedKey1, err1 := EncryptKey(key1, encryptionKey)
		encryptedKey2, err2 := EncryptKey(key2, encryptionKey)

		// Assert
		assert.NoError(t, err1)
		assert.NoError(t, err2)
		assert.NotEqual(t, encryptedKey1, encryptedKey2, "Different plaintext keys should produce different encrypted keys")
	})

	t.Run("Different encryption keys produce different encryptions", func(t *testing.T) {
		// Arrange
		key := "test-api-key-1234567890"
		encryptionKey1 := bytes.Repeat([]byte("a"), 32)
		encryptionKey2 := bytes.Repeat([]byte("b"), 32)

		// Act
		encryptedKey1, err1 := EncryptKey(key, encryptionKey1)
		encryptedKey2, err2 := EncryptKey(key, encryptionKey2)

		// Assert
		assert.NoError(t, err1)
		assert.NoError(t, err2)
		assert.NotEqual(t, encryptedKey1, encryptedKey2, "Different encryption keys should produce different encrypted keys")
	})

	t.Run("Empty key can be encrypted", func(t *testing.T) {
		// Arrange
		key := ""
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		encryptedKey, err := EncryptKey(key, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.NotEmpty(t, encryptedKey)
	})

	t.Run("Very long key can be encrypted", func(t *testing.T) {
		// Arrange
		key := strings.Repeat("a", 10000) // 10KB string
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		encryptedKey, err := EncryptKey(key, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.NotEmpty(t, encryptedKey)
	})
}

func TestDecryptKey(t *testing.T) {
	t.Run("Successfully decrypt key", func(t *testing.T) {
		// Arrange
		originalKey := "test-api-key-1234567890"
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		encryptedKey, err := EncryptKey(originalKey, encryptionKey)
		require.NoError(t, err)

		// Act
		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, originalKey, decryptedKey)
	})

	t.Run("Error with invalid base64", func(t *testing.T) {
		// Arrange
		invalidBase64 := "not-valid-base64!"
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		decryptedKey, err := DecryptKey(invalidBase64, encryptionKey)

		// Assert
		assert.Error(t, err)
		assert.Empty(t, decryptedKey)
		assert.Contains(t, err.Error(), "failed to decode base64")
	})

	t.Run("Error with wrong encryption key", func(t *testing.T) {
		// Arrange
		originalKey := "test-api-key-1234567890"
		encryptionKey1 := bytes.Repeat([]byte("a"), 32)
		encryptionKey2 := bytes.Repeat([]byte("b"), 32)

		encryptedKey, err := EncryptKey(originalKey, encryptionKey1)
		require.NoError(t, err)

		// Act
		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey2)

		// Assert
		assert.Error(t, err)
		assert.Empty(t, decryptedKey)
		assert.Contains(t, err.Error(), "failed to decrypt")
	})

	t.Run("Error with ciphertext too short", func(t *testing.T) {
		// Arrange
		shortCiphertext := base64.StdEncoding.EncodeToString(bytes.Repeat([]byte("x"), 8))
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		decryptedKey, err := DecryptKey(shortCiphertext, encryptionKey)

		// Assert
		assert.Error(t, err)
		assert.Empty(t, decryptedKey)
		assert.Contains(t, err.Error(), "ciphertext too short")
	})

	t.Run("Successfully decrypt empty key", func(t *testing.T) {
		// Arrange
		originalKey := ""
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		encryptedKey, err := EncryptKey(originalKey, encryptionKey)
		require.NoError(t, err)

		// Act
		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, originalKey, decryptedKey)
	})

	t.Run("Successfully decrypt very long key", func(t *testing.T) {
		// Arrange
		originalKey := strings.Repeat("a", 10000) // 10KB string
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		encryptedKey, err := EncryptKey(originalKey, encryptionKey)
		require.NoError(t, err)

		// Act
		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, originalKey, decryptedKey)
	})
}

func TestEncryptionRoundTrip(t *testing.T) {
	t.Run("Encrypt and decrypt special characters", func(t *testing.T) {
		// Arrange
		originalKey := "!@#$%^&*()_+{}[]|:;'<>,.?/~`"
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		encryptedKey, err := EncryptKey(originalKey, encryptionKey)
		require.NoError(t, err)

		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, originalKey, decryptedKey)
	})

	t.Run("Encrypt and decrypt Unicode characters", func(t *testing.T) {
		// Arrange
		originalKey := "こんにちは世界 Привет мир 你好世界 مرحبا بالعالم"
		encryptionKey := bytes.Repeat([]byte("a"), 32)

		// Act
		encryptedKey, err := EncryptKey(originalKey, encryptionKey)
		require.NoError(t, err)

		decryptedKey, err := DecryptKey(encryptedKey, encryptionKey)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, originalKey, decryptedKey)
	})
}
